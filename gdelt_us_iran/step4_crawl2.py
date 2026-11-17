import os
import re
import time
from typing import Dict, Any

import pandas as pd
import trafilatura
from readability import Document
from playwright.sync_api import sync_playwright


INPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/event_A_candidates_expanded.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_expanded.csv"

# 最多抓多少篇；None 表示不限制
MAX_ARTICLES = 10000

# 单页超时毫秒
PLAYWRIGHT_TIMEOUT = 30000

# 每抓完一条是否强制 flush
SAVE_EVERY = 1


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_with_trafilatura(url: str) -> Dict[str, Any]:
    result = {
        "success": False,
        "method": "trafilatura",
        "title": "",
        "text": "",
        "raw_html": "",
        "error": "",
    }
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            result["error"] = "fetch_url_failed"
            return result

        result["raw_html"] = downloaded

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            output_format="txt",
        )

        if text and len(text.strip()) > 200:
            result["success"] = True
            result["text"] = clean_text(text)
            return result

        result["error"] = "extract_too_short"
        return result
    except Exception as e:
        result["error"] = f"trafilatura_error: {e}"
        return result


def extract_with_readability(html: str) -> str:
    try:
        doc = Document(html)
        summary_html = doc.summary()
        extracted = trafilatura.extract(
            summary_html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            output_format="txt",
        )
        return clean_text(extracted or "")
    except Exception:
        return ""


def extract_with_playwright(url: str, browser) -> Dict[str, Any]:
    result = {
        "success": False,
        "method": "playwright",
        "title": "",
        "text": "",
        "raw_html": "",
        "error": "",
    }

    page = None
    try:
        page = browser.new_page()
        page.set_default_timeout(PLAYWRIGHT_TIMEOUT)

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        page.evaluate(
            """
            () => {
                window.scrollTo(0, document.body.scrollHeight * 0.5);
            }
            """
        )
        page.wait_for_timeout(1500)

        html = page.content()
        title = page.title()

        result["raw_html"] = html
        result["title"] = title or ""

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            output_format="txt",
        )

        if not text or len(text.strip()) < 200:
            text = extract_with_readability(html)

        text = clean_text(text or "")

        if len(text) > 200:
            result["success"] = True
            result["text"] = text
        else:
            result["error"] = "playwright_extract_too_short"

        return result

    except Exception as e:
        result["error"] = f"playwright_error: {e}"
        return result
    finally:
        if page:
            page.close()


def fetch_one(url: str, browser) -> Dict[str, Any]:
    http_result = extract_with_trafilatura(url)
    if http_result["success"]:
        return http_result

    pw_result = extract_with_playwright(url, browser)
    if pw_result["success"]:
        return pw_result

    return {
        "success": False,
        "method": "failed",
        "title": pw_result.get("title", "") or http_result.get("title", ""),
        "text": "",
        "raw_html": "",
        "error": f"http={http_result.get('error', '')}; pw={pw_result.get('error', '')}",
    }


def load_done_set(output_csv: str):
    """
    读取已完成的输出文件，支持断点续爬。
    优先按 article_id 去重；没有的话退化为 url。
    """
    done_article_ids = set()
    done_urls = set()

    if not os.path.exists(output_csv):
        return done_article_ids, done_urls

    try:
        old_df = pd.read_csv(output_csv, low_memory=False)

        if "article_id" in old_df.columns:
            done_article_ids = set(
                old_df["article_id"].dropna().astype(str).str.strip().tolist()
            )
        if "url" in old_df.columns:
            done_urls = set(
                old_df["url"].dropna().astype(str).str.strip().tolist()
            )

        print(f"Loaded existing output: {output_csv}")
        print(f"Existing rows: {len(old_df)}")
        print(f"Done article_ids: {len(done_article_ids)}")
        print(f"Done urls: {len(done_urls)}")

    except Exception as e:
        print(f"Warning: failed to read existing output file: {e}")

    return done_article_ids, done_urls


def append_row_to_csv(row_dict: Dict[str, Any], output_csv: str):
    """
    每条结果立刻追加保存。
    """
    row_df = pd.DataFrame([row_dict])

    file_exists = os.path.exists(output_csv)
    row_df.to_csv(
        output_csv,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


def main():
    df = pd.read_csv(INPUT_CSV, low_memory=False)

    if "url" not in df.columns:
        raise ValueError("Input CSV must contain a 'url' column.")

    df = df.dropna(subset=["url"]).copy()
    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.startswith("http")].copy()

    if "article_id" not in df.columns:
        df["article_id"] = [f"row_{i}" for i in range(1, len(df) + 1)]
    else:
        df["article_id"] = df["article_id"].astype(str).str.strip()

    if MAX_ARTICLES is not None:
        df = df.head(MAX_ARTICLES).copy()

    done_article_ids, done_urls = load_done_set(OUTPUT_CSV)

    # 跳过已完成的
    before_filter = len(df)
    df = df[
        (~df["article_id"].isin(done_article_ids)) &
        (~df["url"].isin(done_urls))
    ].copy()

    print(f"Total candidates: {before_filter}")
    print(f"Remaining to crawl: {len(df)}")

    if len(df) == 0:
        print("Nothing to do. All rows already crawled.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        total = len(df)
        saved_count = 0

        for i, row in enumerate(df.itertuples(index=False), start=1):
            url = getattr(row, "url")
            article_id = getattr(row, "article_id", f"row_{i}")

            print(f"[{i}/{total}] Fetching: {url}")

            try:
                fetched = fetch_one(url, browser)

                text = fetched["text"]
                word_count = len(text.split()) if text else 0

                out_row = {
                    "article_id": article_id,
                    "url": url,
                    "domain": getattr(row, "domain", ""),
                    "country_group": getattr(row, "country_group", ""),
                    "title": fetched.get("title", ""),
                    "text": text,
                    "word_count": word_count,
                    "success": fetched["success"],
                    "method": fetched["method"],
                    "error": fetched["error"],
                }

                append_row_to_csv(out_row, OUTPUT_CSV)
                saved_count += 1

                # 内存里的 done 集合也同步更新，防止本次运行中重复
                done_article_ids.add(str(article_id))
                done_urls.add(str(url))

                print(
                    f"  -> saved | success={fetched['success']} "
                    f"| method={fetched['method']} | words={word_count}"
                )

            except Exception as e:
                # 就算主流程异常，也把错误记下来，便于续爬
                out_row = {
                    "article_id": article_id,
                    "url": url,
                    "domain": getattr(row, "domain", ""),
                    "country_group": getattr(row, "country_group", ""),
                    "title": "",
                    "text": "",
                    "word_count": 0,
                    "success": False,
                    "method": "exception",
                    "error": f"main_loop_error: {e}",
                }
                append_row_to_csv(out_row, OUTPUT_CSV)
                saved_count += 1

                done_article_ids.add(str(article_id))
                done_urls.add(str(url))

                print(f"  -> saved exception row: {e}")

            time.sleep(1.0)

        browser.close()

    print(f"\nFinished. Newly saved rows: {saved_count}")
    print(f"Output file: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
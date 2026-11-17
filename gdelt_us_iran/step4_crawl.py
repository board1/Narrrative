import os
import re
import time
from typing import Optional, Dict, Any

import pandas as pd
import trafilatura
from readability import Document
from playwright.sync_api import sync_playwright


INPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/event_A_candidates_expanded.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_expanded.csv"

# 最多抓多少篇，先小规模试
MAX_ARTICLES = min(10000,len(pd.read_csv(INPUT_CSV, low_memory=False)))

# 单页超时毫秒
PLAYWRIGHT_TIMEOUT = 30000


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_with_trafilatura(url: str) -> Dict[str, Any]:
    """
    先不用浏览器，直接请求页面并提正文。
    """
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
    """
    对已有 HTML 再做一次正文提取。
    """
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
    """
    浏览器渲染后抓正文。
    """
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

        # 尝试滚动一下，触发懒加载
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

        # 先用 trafilatura 提
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            output_format="txt",
        )

        if not text or len(text.strip()) < 200:
            # 再试 readability
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
    """
    总流程：HTTP 优先，失败再 Playwright。
    """
    http_result = extract_with_trafilatura(url)
    if http_result["success"]:
        return http_result

    pw_result = extract_with_playwright(url, browser)
    if pw_result["success"]:
        return pw_result

    # 都失败时，把更完整的报错带回
    return {
        "success": False,
        "method": "failed",
        "title": pw_result.get("title", "") or http_result.get("title", ""),
        "text": "",
        "raw_html": "",
        "error": f"http={http_result.get('error', '')}; pw={pw_result.get('error', '')}",
    }


def main():
    df = pd.read_csv(INPUT_CSV, low_memory=False)

    if "url" not in df.columns:
        raise ValueError("Input CSV must contain a 'url' column.")

    df = df.dropna(subset=["url"]).copy()
    df["url"] = df["url"].astype(str)
    df = df[df["url"].str.startswith("http")].copy()

    if MAX_ARTICLES:
        df = df.head(MAX_ARTICLES).copy()

    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        total = len(df)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            url = getattr(row, "url")
            article_id = getattr(row, "article_id", f"row_{i}")

            print(f"[{i}/{total}] Fetching: {url}")

            fetched = fetch_one(url, browser)

            text = fetched["text"]
            word_count = len(text.split()) if text else 0

            rows.append({
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
            })

            # 轻微限速，避免太猛
            time.sleep(1.0)

        browser.close()

    out_df = pd.DataFrame(rows)
    out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\nSaved to: {OUTPUT_CSV}")
    print(out_df["success"].value_counts(dropna=False))
    print(out_df["method"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
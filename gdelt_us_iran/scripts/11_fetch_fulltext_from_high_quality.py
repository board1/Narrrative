import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import requests
import trafilatura
from newspaper import Article
from tqdm import tqdm

IN_FILE = Path("data/us_iran_candidates_high_quality.jsonl")
OUT_FILE = Path("data/us_iran_fulltext.jsonl")
LOG_FILE = Path("logs/fetch_fulltext_from_high_quality.log")

OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

HTTP_TIMEOUT = 40
MAX_RETRIES = 3
SLEEP_SECONDS = 1.5
MIN_WORDS = 120


def log(msg: str):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def download_html(url: str):
    """
    下载 HTML。失败时返回 None。
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                url,
                headers=HEADERS,
                timeout=HTTP_TIMEOUT,
                allow_redirects=True,
            )

            # 成功
            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                if "text/html" in content_type or content_type == "":
                    return r.text
                return None

            # 常见限制
            if r.status_code in (403, 404, 429, 500, 502, 503, 504):
                wait = attempt * 3
                log(f"[retry] {r.status_code} url={url} wait={wait}s")
                time.sleep(wait)
                continue

            return None

        except requests.RequestException as e:
            wait = attempt * 3
            log(f"[error] {type(e).__name__} url={url} wait={wait}s")
            time.sleep(wait)

    return None


def extract_with_trafilatura(html: str, url: str):
    """
    用 trafilatura 从 HTML 中抽正文和元数据
    """
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            output_format="json",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if not extracted:
            return None

        obj = json.loads(extracted)
        text = (obj.get("text") or "").strip()
        if len(text.split()) < MIN_WORDS:
            return None

        return {
            "title": obj.get("title"),
            "text": text,
            "author": obj.get("author"),
            "date": obj.get("date"),
            "hostname": obj.get("hostname"),
            "sitename": obj.get("sitename"),
            "language": obj.get("language"),
            "fetch_method": "trafilatura",
        }
    except Exception:
        return None


def extract_with_newspaper(url: str):
    """
    用 newspaper4k 作为备用抽取器
    """
    try:
        art = Article(url)
        art.download()
        art.parse()

        text = (art.text or "").strip()
        if len(text.split()) < MIN_WORDS:
            return None

        return {
            "title": art.title,
            "text": text,
            "author": art.authors,
            "date": art.publish_date.isoformat() if art.publish_date else None,
            "hostname": urlparse(url).netloc.lower(),
            "sitename": None,
            "language": art.meta_lang,
            "top_image": art.top_image,
            "canonical_url": art.canonical_link,
            "fetch_method": "newspaper4k",
        }
    except Exception:
        return None


def process_one(item: dict):
    """
    处理一条高质量候选记录
    """
    url = item.get("article_url")
    if not url:
        return {
            "article_url": None,
            "fetch_status": "missing_url",
        }

    html = download_html(url)
    if html:
        tf = extract_with_trafilatura(html, url)
        if tf:
            tf["article_url"] = url
            tf["source"] = item.get("source")
            tf["source_domain_input"] = item.get("source_domain")
            tf["publish_time_input"] = item.get("publish_time")
            tf["themes"] = item.get("themes")
            tf["tone"] = item.get("tone")
            tf["page_type"] = item.get("page_type")
            tf["quality_flag"] = item.get("quality_flag")
            tf["title_input"] = item.get("title")
            tf["text_hash"] = sha256_text(tf["text"])
            tf["word_count"] = len(tf["text"].split())
            tf["fetch_status"] = "success"
            return tf

    np_res = extract_with_newspaper(url)
    if np_res:
        np_res["article_url"] = url
        np_res["source"] = item.get("source")
        np_res["source_domain_input"] = item.get("source_domain")
        np_res["publish_time_input"] = item.get("publish_time")
        np_res["themes"] = item.get("themes")
        np_res["tone"] = item.get("tone")
        np_res["page_type"] = item.get("page_type")
        np_res["quality_flag"] = item.get("quality_flag")
        np_res["title_input"] = item.get("title")
        np_res["text_hash"] = sha256_text(np_res["text"])
        np_res["word_count"] = len(np_res["text"].split())
        np_res["fetch_status"] = "success"
        return np_res

    return {
        "article_url": url,
        "source": item.get("source"),
        "source_domain_input": item.get("source_domain"),
        "publish_time_input": item.get("publish_time"),
        "themes": item.get("themes"),
        "tone": item.get("tone"),
        "page_type": item.get("page_type"),
        "quality_flag": item.get("quality_flag"),
        "title_input": item.get("title"),
        "fetch_status": "failed",
    }


def main():
    rows = []
    with open(IN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    log(f"loaded {len(rows)} records from {IN_FILE}")

    success = 0
    failed = 0

    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for item in tqdm(rows, desc="fetching fulltext"):
            result = process_one(item)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")

            if result.get("fetch_status") == "success":
                success += 1
            else:
                failed += 1

            time.sleep(SLEEP_SECONDS)

    log(f"done. success={success}, failed={failed}, saved={OUT_FILE}")


if __name__ == "__main__":
    main()
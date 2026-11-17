"""
新闻爬虫 — 从 crawl_10k.csv 读取 URL，并发抓取 + trafilatura 正文提取。
- 异步并发，默认 10 workers
- JSON 文件断点续爬（progress.json）
- JSONL 输出（每行一篇）
"""
import asyncio
import json
import random
import time
import argparse
import hashlib
from pathlib import Path

import aiohttp
import pandas as pd
import trafilatura
from bs4 import BeautifulSoup

# =========================
# 默认路径
# =========================
DEFAULT_INPUT = "data/gdelt_events_v3/crawl_10k.csv"
DEFAULT_OUT_DIR = "data/gdelt_events_v3/crawled_articles"

# =========================
# 爬取参数
# =========================
DEFAULT_CONCURRENCY = 10
DEFAULT_TIMEOUT = 30  # 秒
DEFAULT_RETRIES = 2
DEFAULT_DELAY = 0.5  # 每个 worker 请求间隔（秒）

# 反反爬：User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
]


def load_progress(progress_path: Path):
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    if progress_path.exists():
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress_path: Path, progress: dict):
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def seed_progress(progress: dict, df):
    """将 CSV 中的 URL 写入 progress dict"""
    added = 0
    for _, row in df.iterrows():
        url = str(row["url"])
        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash not in progress:
            progress[url_hash] = {
                "event_id": row["event_id"],
                "day": str(row.get("day", "")),
                "country_group": row["country_group_final"],
                "domain_norm": row["domain_norm"],
                "url": url,
                "status": "pending",
                "status_code": 0,
                "error": "",
                "text_len": 0,
            }
            added += 1
    return added


def get_pending(progress: dict):
    """获取待爬 URL"""
    return [
        (h, p["url"], p["domain_norm"])
        for h, p in progress.items()
        if p["status"] in ("pending", "failed")
    ]


async def fetch_one(session, sem, url_hash, url, domain, timeout, retries):
    """抓取单篇 + trafilatura 提取"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }

    async with sem:
        for attempt in range(retries + 1):
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    status = resp.status
                    if status == 200:
                        html = await resp.text()

                        # trafilatura 提取正文
                        extracted = trafilatura.extract(
                            html,
                            include_comments=False,
                            include_tables=False,
                            no_fallback=False,
                            favor_precision=True,
                        )

                        # BeautifulSoup 提取标题
                        title = ""
                        try:
                            soup = BeautifulSoup(html, "lxml")
                            if soup.title:
                                title = soup.title.get_text(strip=True)
                        except Exception:
                            pass

                        if extracted and len(extracted.strip()) > 100:
                            return {
                                "url_hash": url_hash,
                                "status": "success",
                                "status_code": status,
                                "title": title,
                                "text": extracted.strip(),
                                "text_len": len(extracted.strip()),
                                "error": None,
                            }

                        # 正文太短
                        return {
                            "url_hash": url_hash,
                            "status": "short",
                            "status_code": status,
                            "title": title,
                            "text": extracted.strip() if extracted else "",
                            "text_len": len(extracted.strip()) if extracted else 0,
                            "error": "text too short or empty",
                        }

                    elif status in (403, 429, 451):
                        return {
                            "url_hash": url_hash,
                            "status": "blocked",
                            "status_code": status,
                            "title": "", "text": "", "text_len": 0,
                            "error": f"HTTP {status}",
                        }
                    elif status in (404, 410):
                        return {
                            "url_hash": url_hash,
                            "status": "dead",
                            "status_code": status,
                            "title": "", "text": "", "text_len": 0,
                            "error": f"HTTP {status}",
                        }
                    else:
                        if attempt < retries:
                            await asyncio.sleep(2)
                            continue
                        return {
                            "url_hash": url_hash,
                            "status": "failed",
                            "status_code": status,
                            "title": "", "text": "", "text_len": 0,
                            "error": f"HTTP {status}",
                        }

            except asyncio.TimeoutError:
                if attempt < retries:
                    await asyncio.sleep(2)
                    continue
                return {"url_hash": url_hash, "status": "timeout", "status_code": 0,
                        "title": "", "text": "", "text_len": 0, "error": "timeout"}

            except aiohttp.ClientError as e:
                if attempt < retries:
                    await asyncio.sleep(2)
                    continue
                return {"url_hash": url_hash, "status": "failed", "status_code": 0,
                        "title": "", "text": "", "text_len": 0, "error": str(e)[:200]}

            except Exception as e:
                return {"url_hash": url_hash, "status": "failed", "status_code": 0,
                        "title": "", "text": "", "text_len": 0, "error": str(e)[:200]}

        return {"url_hash": url_hash, "status": "failed", "status_code": 0,
                "title": "", "text": "", "text_len": 0, "error": "max retries"}


def save_result(progress: dict, result, fetch_time, jsonl_fh, progress_path):
    """更新 progress + 写入 JSONL"""
    uh = result["url_hash"]
    if uh in progress:
        progress[uh]["status"] = result["status"]
        progress[uh]["status_code"] = result["status_code"]
        progress[uh]["error"] = result.get("error", "")
        progress[uh]["text_len"] = result["text_len"]

    # 成功写入 JSONL
    if result["status"] == "success" and jsonl_fh:
        meta = progress.get(uh, {})
        record = {
            "event_id": meta.get("event_id", ""),
            "day": meta.get("day", ""),
            "country_group": meta.get("country_group", ""),
            "domain_norm": meta.get("domain_norm", ""),
            "url": meta.get("url", ""),
            "title": result["title"],
            "text": result["text"],
            "text_len": result["text_len"],
        }
        jsonl_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        jsonl_fh.flush()

    # 定期保存 progress
    if len([p for p in progress.values() if p["status"] not in ("pending", "failed")]) % 50 == 0:
        save_progress(progress_path, progress)


async def crawl(progress: dict, progress_path: Path, concurrency, timeout, retries, delay, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "articles.jsonl"
    jsonl_fh = open(str(jsonl_path), "a", encoding="utf-8")

    pending = get_pending(progress)
    total = len(pending)
    if total == 0:
        print("No pending URLs.")
        jsonl_fh.close()
        return

    print(f"Pending URLs: {total}")

    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=2, force_close=True)
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    done = 0
    success = 0
    counts = {"short": 0, "blocked": 0, "dead": 0, "failed": 0, "timeout": 0}
    start = time.time()

    async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
        tasks = []
        for url_hash, url, domain in pending:
            tasks.append(asyncio.create_task(
                fetch_one(session, sem, url_hash, url, domain, timeout, retries)
            ))

        for task in asyncio.as_completed(tasks):
            t0 = time.time()
            result = await task
            ft = round(time.time() - t0, 2)

            save_result(progress, result, ft, jsonl_fh, progress_path)

            done += 1
            st = result["status"]
            if st == "success":
                success += 1
            else:
                counts[st] = counts.get(st, 0) + 1

            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            if done % 50 == 0 or done == total:
                print(f"[{done}/{total}] {rate:.1f} URLs/s | "
                      f"OK={success} short={counts.get('short',0)} blocked={counts.get('blocked',0)} "
                      f"dead={counts.get('dead',0)} fail={counts.get('failed',0)+counts.get('timeout',0)} | "
                      f"elapsed={elapsed:.0f}s")

            await asyncio.sleep(delay)

    save_progress(progress_path, progress)
    jsonl_fh.close()

    print(f"\n=== DONE ===")
    print(f"Total: {done}, Success: {success} ({100*success/done:.1f}%)")
    for k, v in counts.items():
        if v:
            print(f"  {k}: {v}")
    print(f"JSONL output: {jsonl_path}")


def print_stats(progress):
    from collections import Counter
    cnt = Counter(p["status"] for p in progress.values())
    print("\n[Progress Stats]")
    for status, c in cnt.most_common():
        print(f"  {status}: {c}")


async def main():
    parser = argparse.ArgumentParser(description="新闻爬虫 — 异步并发 + trafilatura 正文提取")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--out_dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--stats", action="store_true", help="只打印统计")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    progress_path = out_dir / "progress.json"

    progress = load_progress(progress_path)

    if args.stats:
        print_stats(progress)
        return

    # 加载 CSV 写入 progress
    print(f"Loading {args.input} ...")
    df = pd.read_csv(args.input, low_memory=False)
    added = seed_progress(progress, df)
    print(f"New URLs added to progress: {added}")
    save_progress(progress_path, progress)

    print_stats(progress)

    await crawl(progress, progress_path, args.concurrency, args.timeout,
                args.retries, args.delay, out_dir)

    print_stats(progress)


if __name__ == "__main__":
    asyncio.run(main())

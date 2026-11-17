# scripts/01_fetch_gdelt_urls_stable.py

import json
import time
import random
import requests
from datetime import datetime, timedelta
from pathlib import Path

QUERY = '''
("United States" OR US OR America OR Washington OR Pentagon)
AND
(Iran OR Iranian OR Tehran OR IRGC)
'''

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

MAX_RECORDS = 100           # 先降到100
REQUEST_SLEEP_SECONDS = 25  # 每个窗口之间至少25秒
HTTP_TIMEOUT = 60
MAX_RETRIES = 3             # 单窗口最多重试3次

OUT_DIR = Path("data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_FILE = OUT_DIR / "gdelt_us_iran_urls.jsonl"
FAILED_FILE = OUT_DIR / "gdelt_failed_windows.jsonl"
LOG_FILE = Path("logs/fetch_gdelt_urls.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def day_bounds(day: datetime):
    start_dt = datetime(day.year, day.month, day.day, 0, 0, 0)
    end_dt = datetime(day.year, day.month, day.day, 23, 59, 59)
    return start_dt, end_dt


def fetch_one_window(start_dt: datetime, end_dt: datetime):
    params = {
        "query": QUERY,
        "mode": "ArtList",
        "maxrecords": MAX_RECORDS,
        "format": "json",
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
        "sort": "DateDesc",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(GDELT_DOC_URL, params=params, timeout=HTTP_TIMEOUT)

            if r.status_code == 200:
                return r.json(), None

            if r.status_code == 429:
                # 指数退避 + 抖动
                wait = min(60 * attempt, 180) + random.uniform(3, 10)
                log(
                    f"429 rate limit. attempt={attempt} "
                    f"wait={wait:.1f}s window={params['startdatetime']}~{params['enddatetime']}"
                )
                time.sleep(wait)
                continue

            return None, f"HTTP_{r.status_code}"

        except requests.RequestException as e:
            wait = min(20 * attempt, 60) + random.uniform(1, 5)
            log(
                f"request error={type(e).__name__} attempt={attempt} "
                f"wait={wait:.1f}s window={params['startdatetime']}~{params['enddatetime']}"
            )
            time.sleep(wait)

    return None, "MAX_RETRIES_EXCEEDED"


def main():
    # 先从最近7天测试，稳定后再扩大
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=7)

    all_items = {}

    current_date = start_date
    log(f"start fetching. date range={start_date} ~ {end_date}")

    while current_date < end_date:
        day = datetime.combine(current_date, datetime.min.time())
        start_dt, end_dt = day_bounds(day)

        log(f"fetch window: {start_dt} -> {end_dt}")
        data, err = fetch_one_window(start_dt, end_dt)

        if data and "articles" in data:
            articles = data.get("articles", [])
            for a in articles:
                url = a.get("url")
                if not url:
                    continue
                all_items[url] = {
                    "url": url,
                    "title": a.get("title"),
                    "seendate": a.get("seendate"),
                    "socialimage": a.get("socialimage"),
                    "domain": a.get("domain"),
                    "language": a.get("language"),
                    "sourcecountry": a.get("sourcecountry"),
                    "query": QUERY.strip(),
                }
            log(f"got {len(articles)} articles; dedup total={len(all_items)}")
        else:
            log(f"failed window: {start_dt} -> {end_dt}, error={err}")
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
                    "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
                    "error": err,
                }, ensure_ascii=False) + "\n")

        current_date += timedelta(days=1)

        # 窗口之间再等一会儿
        sleep_time = REQUEST_SLEEP_SECONDS + random.uniform(2, 8)
        log(f"sleep {sleep_time:.1f}s before next window")
        time.sleep(sleep_time)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for item in all_items.values():
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    log(f"done. saved={len(all_items)} file={OUT_FILE}")


if __name__ == "__main__":
    main()
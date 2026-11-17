#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
01_collect_gkg_files.py

Download and parse GDELT GKG files, filter US–Iran related articles.

Usage:
python 01_collect_gkg_files.py \
    --start 2026-01-01 \
    --end 2026-01-03 \
    --output data/interim/gkg_articles_raw.jsonl
"""

import argparse
import csv
import gzip
import io
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from tqdm import tqdm


BASE_URL = "http://data.gdeltproject.org/gdeltv2"


# ======================
# 参数
# ======================
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sleep", type=float, default=0.5)
    return parser.parse_args()


# ======================
# 时间生成（15分钟粒度）
# ======================
def generate_timestamps(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    cur = start
    while cur < end:
        yield cur.strftime("%Y%m%d%H%M%S")
        cur += timedelta(minutes=15)


# ======================
# 下载 GKG 文件
# ======================
def download_gkg(ts):
    url = f"{BASE_URL}/{ts}.gkg.csv.gz"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        return gzip.decompress(resp.content)
    except Exception:
        return None


# ======================
# 判断是否 US–Iran 相关
# ======================
def is_relevant(text):
    text = text.lower()

    if "iran" not in text:
        return False

    us_terms = ["united states", "us", "america", "washington"]
    conflict_terms = [
        "strike", "attack", "missile", "retaliation",
        "nuclear", "sanction", "israel", "gulf"
    ]

    has_us = any(t in text for t in us_terms)
    has_conflict = any(t in text for t in conflict_terms)

    return has_us or has_conflict


# ======================
# 主流程
# ======================
def main():
    args = parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    timestamps = list(generate_timestamps(args.start, args.end))

    seen_urls = set()
    total = 0
    kept = 0

    with output_path.open("w", encoding="utf-8") as fout:

        for ts in tqdm(timestamps):

            data = download_gkg(ts)
            if data is None:
                continue

            text_stream = io.StringIO(data.decode("utf-8", errors="ignore"))
            reader = csv.reader(text_stream, delimiter='\t')

            for row in reader:
                total += 1

                try:
                    url = row[4]
                    source = row[3]
                    date = row[1]
                    themes = row[7]
                    locations = row[9]
                    persons = row[10]
                    orgs = row[11]
                    tone = row[15]
                except Exception:
                    continue

                if not url or url in seen_urls:
                    continue

                # 用多个字段拼文本判断相关性
                text = " ".join([themes, locations, persons, orgs])

                if not is_relevant(text):
                    continue

                seen_urls.add(url)

                item = {
                    "url": url,
                    "source": source,
                    "date": date,
                    "themes": themes,
                    "locations": locations,
                    "persons": persons,
                    "organizations": orgs,
                    "tone": tone,
                    "gkg_timestamp": ts
                }

                fout.write(json.dumps(item, ensure_ascii=False) + "\n")
                kept += 1

            time.sleep(args.sleep)

    print("\n=== DONE ===")
    print(f"total rows: {total}")
    print(f"kept: {kept}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
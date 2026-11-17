#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
02_parse_filter_gkg_local.py

Parse local GDELT GKG files (.gkg.csv and .gkg.csv.zip), filter US–Iran related records,
and write JSONL output.

Usage examples:

python 02_parse_filter_gkg_local.py \
    --inputs /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/gkg_csv \
             /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/gkg_zips \
    --output /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_raw.jsonl

python 02_parse_filter_gkg_local.py \
    --inputs /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/gkg_csv/20260311000000.gkg.csv \
             /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/gkg_zips/20260317234500.gkg.csv.zip \
    --output /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_raw.jsonl \
    --keep-raw
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import re
import zipfile
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
from urllib.parse import urlparse


def increase_csv_field_limit():
    max_int = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_int)
            break
        except OverflowError:
            max_int = max_int // 10

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="One or more local files or directories containing .gkg.csv / .gkg.csv.zip",
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw_row in output")
    parser.add_argument("--sample", type=int, default=0, help="Only process first N files for debugging")
    parser.add_argument("--min-cols", type=int, default=7, help="Skip rows with fewer than this many columns")
    return parser.parse_args()


def discover_files(inputs: List[str]) -> List[Path]:
    files: List[Path] = []

    for item in inputs:
        p = Path(item)
        if not p.exists():
            print(f"[WARN] path not found: {p}")
            continue

        if p.is_file():
            if p.name.endswith(".gkg.csv") or p.name.endswith(".gkg.csv.zip"):
                files.append(p)
            else:
                print(f"[WARN] unsupported file suffix, skipped: {p}")
        else:
            files.extend(sorted(p.rglob("*.gkg.csv")))
            files.extend(sorted(p.rglob("*.gkg.csv.zip")))

    # 去重
    uniq = []
    seen = set()
    for f in files:
        s = str(f.resolve())
        if s not in seen:
            uniq.append(f)
            seen.add(s)

    return sorted(uniq)


def read_text_from_file(path: Path) -> Optional[str]:
    try:
        if path.name.endswith(".zip"):
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if not names:
                    return None
                # 默认读 zip 里的第一个文件
                with zf.open(names[0]) as f:
                    return f.read().decode("utf-8", errors="ignore")
        else:
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] failed to read {path}: {e}")
        return None


def iter_rows(text: str) -> Iterator[List[str]]:
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    for row in reader:
        yield row


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def first_url_in_row(row: List[str]) -> str:
    for cell in row:
        c = cell.strip()
        if c.startswith("http://") or c.startswith("https://"):
            return c
    return ""


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower().strip()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def looks_like_tone(cell: str) -> bool:
    # V2Tone 常见形式类似多个逗号分隔数字
    parts = [p.strip() for p in cell.split(",")]
    if len(parts) < 6:
        return False
    for p in parts[:6]:
        if not re.fullmatch(r"-?\d+(\.\d+)?", p):
            return False
    return True


def first_tone_in_row(row: List[str]) -> str:
    for cell in row:
        cell = cell.strip()
        if looks_like_tone(cell):
            return cell
    return ""


def parse_gkg_timestamp_from_filename(path: Path) -> str:
    m = re.search(r"(\d{14})\.gkg\.csv(?:\.zip)?$", path.name)
    return m.group(1) if m else ""


def is_relevant(title_text: str) -> bool:
    t = f" {title_text.lower()} "

    if "iran" not in t:
        return False

    us_terms = [
        " united states ", " u.s. ", " us ", " america ", " american ", " washington "
    ]
    conflict_terms = [
        " strike ", " attack ", " missile ", " retaliation ", " retaliat ",
        " nuclear ", " sanction ", " israel ", " gulf ", " proxy ",
        " military ", " bomb ", " drone ", " airstrike ", " escalation ",
        " ceasefire ", " navy ", " troops ", " armed ", " conflict "
    ]

    has_us = any(term in t for term in us_terms)
    has_conflict = any(term in t for term in conflict_terms)

    return has_us or has_conflict


def safe_get(row: List[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


def row_to_record(row: List[str], source_file: Path, keep_raw: bool = False) -> dict:
    # 前几列按 GKG 常见结构保守取值
    date = safe_get(row, 0)
    numarts = safe_get(row, 1)
    counts = safe_get(row, 2)
    themes = safe_get(row, 3)
    locations = safe_get(row, 4)
    persons = safe_get(row, 5)
    organizations = safe_get(row, 6)
    enhanced_themes = safe_get(row, 7)

    url = first_url_in_row(row)
    tone = first_tone_in_row(row)
    domain = extract_domain(url)

    filter_text = normalize_space(
        " ".join([counts, themes, locations, persons, organizations, enhanced_themes, domain, url])
    )

    rec = {
        "date": date,
        "numarts": numarts,
        "counts": counts,
        "themes": themes,
        "locations": locations,
        "persons": persons,
        "organizations": organizations,
        "enhanced_themes": enhanced_themes,
        "url": url,
        "domain": domain,
        "tone": tone,
        "gkg_timestamp": parse_gkg_timestamp_from_filename(source_file),
        "source_file": str(source_file),
    }

    if keep_raw:
        rec["raw_row"] = row

    rec["_filter_text"] = filter_text
    return rec


def main():
    increase_csv_field_limit()
    args = parse_args()

    input_files = discover_files(args.inputs)
    if args.sample > 0:
        input_files = input_files[:args.sample]

    if not input_files:
        print("[ERROR] no input files found")
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_rows = 0
    skipped_short_rows = 0
    kept_rows = 0
    duplicate_urls = 0
    parse_failures = 0

    seen_urls = set()

    with output_path.open("w", encoding="utf-8") as fout:
        for file_path in input_files:
            total_files += 1
            text = read_text_from_file(file_path)
            if text is None:
                parse_failures += 1
                continue

            for row in iter_rows(text):
                total_rows += 1

                if len(row) < args.min_cols:
                    skipped_short_rows += 1
                    continue

                rec = row_to_record(row, file_path, keep_raw=args.keep_raw)
                filter_text = rec.pop("_filter_text", "")

                if not is_relevant(filter_text):
                    continue

                url = rec.get("url", "")
                if url:
                    if url in seen_urls:
                        duplicate_urls += 1
                        continue
                    seen_urls.add(url)

                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept_rows += 1

    print("\n=== DONE ===")
    print(f"files_processed: {total_files}")
    print(f"rows_total: {total_rows}")
    print(f"rows_skipped_short: {skipped_short_rows}")
    print(f"rows_kept: {kept_rows}")
    print(f"duplicate_urls_skipped: {duplicate_urls}")
    print(f"parse_failures: {parse_failures}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
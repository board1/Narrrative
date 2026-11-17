#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
03_clean_candidate_set.py

Input:
    gkg_articles_raw.jsonl

Output:
    gkg_articles_clean.jsonl
    gkg_articles_drop.jsonl

Usage:
python 03_clean_candidate_set.py \
  --input /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_raw.jsonl \
  --outdir /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse


SOCIAL_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "weibo.com"
}

BAD_URL_PATTERNS = [
    "/video/", "/videos/", "/gallery/", "/galleries/", "/photo/", "/photos/",
    "/tag/", "/tags/", "/topic/", "/topics/", "/podcast/", "/audio/"
]

US_TERMS = [
    "united states", "u.s.", " us ", " america ", " american ", " washington ",
    "pentagon", "white house"
]

CONFLICT_TERMS = [
    "strike", "attack", "missile", "retaliation", "retaliat",
    "nuclear", "sanction", "sanctions", "bomb", "drone", "airstrike",
    "military", "troops", "navy", "armed", "conflict", "escalation",
    "ceasefire", "proxy", "gulf", "defense", "self-defense"
]

ISRAEL_TERMS = [
    "israel", "israeli", "idf"
]

IRAN_TERMS = [
    "iran", "iranian", "tehran", "irgc", "revolutionary guards"
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input raw JSONL")
    parser.add_argument("--outdir", required=True, help="Output directory")
    return parser.parse_args()


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                print(f"[WARN] bad json line {line_no}: {e}")


def norm(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return f" {text.strip()} "


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def get_domain(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower().strip()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def get_path(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).path.lower()
    except Exception:
        return ""


def build_text(record: dict) -> str:
    parts = [
        record.get("counts", ""),
        record.get("themes", ""),
        record.get("enhanced_themes", ""),
        record.get("persons", ""),
        record.get("organizations", ""),
        record.get("locations", ""),
        record.get("domain", ""),
        record.get("url", ""),
    ]
    return norm(" ".join(parts))


def clean_record(record: dict) -> dict:
    url = (record.get("url") or "").strip()
    domain = (record.get("domain") or "").strip()

    if not domain and url:
        domain = get_domain(url)

    cleaned = {
        "url": url,
        "domain": domain,
        "date": record.get("date", ""),
        "gkg_timestamp": record.get("gkg_timestamp", ""),
        "source_file": record.get("source_file", ""),
        "counts": record.get("counts", ""),
        "themes": record.get("themes", ""),
        "enhanced_themes": record.get("enhanced_themes", ""),
        "persons": record.get("persons", ""),
        "organizations": record.get("organizations", ""),
        "locations": record.get("locations", ""),
        "tone": record.get("tone", ""),
    }
    return cleaned


def decide(record: dict) -> tuple[bool, str]:
    url = record["url"]
    domain = record["domain"]
    path = get_path(url)

    if not url:
        return False, "missing_url"
    if not domain:
        return False, "missing_domain"
    if domain in SOCIAL_DOMAINS:
        return False, "social_domain"
    if any(p in path for p in BAD_URL_PATTERNS):
        return False, "bad_url_pattern"

    text = build_text(record)

    if not has_any(text, IRAN_TERMS):
        return False, "missing_iran"

    has_us = has_any(text, US_TERMS)
    has_conflict = has_any(text, CONFLICT_TERMS)
    has_israel = has_any(text, ISRAEL_TERMS)

    if has_us:
        return True, "iran+us"
    if has_conflict:
        return True, "iran+conflict"
    if has_israel:
        return True, "iran+israel"

    return False, "weak_relevance"


def main():
    args = parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    clean_path = outdir / "gkg_articles_clean.jsonl"
    drop_path = outdir / "gkg_articles_drop.jsonl"

    total = 0
    kept = 0
    dropped = 0
    dup = 0

    seen_urls = set()

    with clean_path.open("w", encoding="utf-8") as f_clean, \
         drop_path.open("w", encoding="utf-8") as f_drop:

        for obj in load_jsonl(input_path):
            total += 1
            rec = clean_record(obj)

            url = rec["url"]
            if url in seen_urls:
                rec["drop_reason"] = "duplicate_url"
                f_drop.write(json.dumps(rec, ensure_ascii=False) + "\n")
                dropped += 1
                dup += 1
                continue

            keep, reason = decide(rec)

            if keep:
                rec["candidate_reason"] = reason
                f_clean.write(json.dumps(rec, ensure_ascii=False) + "\n")
                kept += 1
                seen_urls.add(url)
            else:
                rec["drop_reason"] = reason
                f_drop.write(json.dumps(rec, ensure_ascii=False) + "\n")
                dropped += 1
                if url:
                    seen_urls.add(url)

    print("\n=== DONE ===")
    print(f"total: {total}")
    print(f"kept: {kept}")
    print(f"dropped: {dropped}")
    print(f"duplicate_dropped: {dup}")
    print(f"clean: {clean_path}")
    print(f"drop: {drop_path}")


if __name__ == "__main__":
    main()
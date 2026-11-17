#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
05_basic_analysis.py

Input:
    gkg_articles_dedup.jsonl

Outputs:
    domain_counts.csv
    candidate_reason_counts.csv
    theme_counts.csv
    tone_summary.json
    tone_by_reason.csv
    tone_by_domain_top.csv

Usage:
python 05_basic_analysis.py \
  --input /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_dedup.jsonl \
  --outdir /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/analysis
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input deduplicated JSONL")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--top-domains", type=int, default=30, help="How many top domains to export")
    parser.add_argument("--top-themes", type=int, default=100, help="How many top themes to export")
    parser.add_argument("--min-domain-count", type=int, default=3, help="Min count for domain tone stats")
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
                print(f"[WARN] bad json at line {line_no}: {e}")


def parse_tone_first(tone: str):
    """
    GKG tone looks like:
    -6.82080924855491,1.15606936416185,7.97687861271676,...

    We only use the first value for a simple baseline.
    """
    if not tone:
        return None
    try:
        first = tone.split(",")[0].strip()
        return float(first)
    except Exception:
        return None


def split_themes(enhanced_themes: str):
    if not enhanced_themes:
        return []
    return [t.strip() for t in enhanced_themes.strip(";").split(";") if t.strip()]


def write_csv(path: Path, header: list[str], rows: list[list]):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def safe_mean(values):
    return statistics.mean(values) if values else None


def safe_median(values):
    return statistics.median(values) if values else None


def main():
    args = parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    domain_counter = Counter()
    reason_counter = Counter()
    theme_counter = Counter()

    tones_all = []
    tones_by_reason = defaultdict(list)
    tones_by_domain = defaultdict(list)

    total = 0
    tone_valid = 0

    for obj in load_jsonl(input_path):
        total += 1

        domain = (obj.get("domain") or "").strip()
        reason = (obj.get("candidate_reason") or "").strip()
        enhanced_themes = obj.get("enhanced_themes", "")
        tone_str = obj.get("tone", "")

        if domain:
            domain_counter[domain] += 1
        if reason:
            reason_counter[reason] += 1

        for th in split_themes(enhanced_themes):
            theme_counter[th] += 1

        tone_val = parse_tone_first(tone_str)
        if tone_val is not None:
            tone_valid += 1
            tones_all.append(tone_val)
            if reason:
                tones_by_reason[reason].append(tone_val)
            if domain:
                tones_by_domain[domain].append(tone_val)

    # 1) domain counts
    domain_rows = [[d, c] for d, c in domain_counter.most_common(args.top_domains)]
    write_csv(outdir / "domain_counts.csv", ["domain", "count"], domain_rows)

    # 2) candidate reason counts
    reason_rows = [[r, c] for r, c in reason_counter.most_common()]
    write_csv(outdir / "candidate_reason_counts.csv", ["candidate_reason", "count"], reason_rows)

    # 3) top themes
    theme_rows = [[t, c] for t, c in theme_counter.most_common(args.top_themes)]
    write_csv(outdir / "theme_counts.csv", ["theme", "count"], theme_rows)

    # 4) tone summary
    tone_summary = {
        "total_records": total,
        "tone_valid_count": tone_valid,
        "tone_valid_ratio": (tone_valid / total) if total else 0.0,
        "tone_mean": safe_mean(tones_all),
        "tone_median": safe_median(tones_all),
        "tone_min": min(tones_all) if tones_all else None,
        "tone_max": max(tones_all) if tones_all else None,
    }
    with (outdir / "tone_summary.json").open("w", encoding="utf-8") as f:
        json.dump(tone_summary, f, ensure_ascii=False, indent=2)

    # 5) tone by candidate reason
    tone_reason_rows = []
    for reason, vals in sorted(tones_by_reason.items(), key=lambda x: (-len(x[1]), x[0])):
        tone_reason_rows.append([
            reason,
            len(vals),
            safe_mean(vals),
            safe_median(vals),
            min(vals) if vals else None,
            max(vals) if vals else None,
        ])
    write_csv(
        outdir / "tone_by_reason.csv",
        ["candidate_reason", "count", "tone_mean", "tone_median", "tone_min", "tone_max"],
        tone_reason_rows,
    )

    # 6) tone by top domains
    tone_domain_rows = []
    for domain, count in domain_counter.most_common():
        vals = tones_by_domain.get(domain, [])
        if len(vals) < args.min_domain_count:
            continue
        tone_domain_rows.append([
            domain,
            len(vals),
            safe_mean(vals),
            safe_median(vals),
            min(vals) if vals else None,
            max(vals) if vals else None,
        ])
    write_csv(
        outdir / "tone_by_domain_top.csv",
        ["domain", "count", "tone_mean", "tone_median", "tone_min", "tone_max"],
        tone_domain_rows,
    )

    # print summary
    print("\n=== BASIC ANALYSIS DONE ===")
    print(f"input_total: {total}")
    print(f"tone_valid: {tone_valid} ({tone_valid / total:.2%})" if total else "tone_valid: 0")
    print(f"top_domain_1: {domain_counter.most_common(1)[0] if domain_counter else None}")
    print(f"top_reason: {reason_counter.most_common(3)}")
    print(f"top_themes: {theme_counter.most_common(10)}")
    print(f"tone_mean: {tone_summary['tone_mean']}")
    print(f"tone_median: {tone_summary['tone_median']}")
    print(f"outputs_dir: {outdir}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
04_dedup_articles.py

目标：
1. 去掉跨站转载
2. 同一内容只保留更像“原始发布站”的版本
3. 输出保留结果 + 被删除结果 + 重复簇信息

Usage:
python 04_dedup_articles.py \
  --input /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_clean.jsonl \
  --outdir /data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


# 明显门户/聚合/转载站，优先删除
AGGREGATOR_DOMAINS = {
    "yahoo.com",
    "aol.com",
    "msn.com",
    "digitaljournal.com",
    "newsbreak.com",
    "ground.news",
    "flipboard.com",
}

# 常见本地电视台/地方站同步稿模式，可继续补
LOCAL_TV_HINTS = [
    "tv.com", "newsnow.com", "13newsnow.com", "10tv.com", "kvue.com",
    "wxyz.com", "wcpo.com", "fox13now.com", "kxlh.com", "kztv10.com"
]

# URL 中常见文章路径提示
ARTICLE_HINTS = [
    "/article/",
    "/articles/",
    "/news/",
    "/world/",
    "/middle-east/",
    "/politics/",
    "/story/",
]

# 这些通常不是原发新闻正文
BAD_PATH_HINTS = [
    "/video/",
    "/videos/",
    "/gallery/",
    "/photos/",
    "/photo/",
    "/tag/",
    "/tags/",
    "/topic/",
    "/topics/",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input JSONL")
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
                print(f"[WARN] bad json at line {line_no}: {e}")


def write_jsonl(path: Path, items):
    with path.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


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


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9; ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_theme_tokens(text: str) -> list[str]:
    """
    enhanced_themes 一般是 ; 分隔，拿它做内容签名最稳。
    """
    if not text:
        return []
    text = text.strip().strip(";")
    parts = [p.strip().lower() for p in text.split(";") if p.strip()]
    # 去掉明显没啥区分度的 theme
    stop = {
        "armedconflict",
        "epu_cats_national_security",
        "tax_ethnicity",
        "tax_fncact",
        "leader",
        "crisislex_crisislexrec",
        "manmade_disaster_implied",
    }
    parts = [p for p in parts if p not in stop]
    return sorted(set(parts))


def content_signature(item: dict) -> str:
    """
    用更稳定的“内容级签名”聚类，不按 URL。
    主要依赖：
    - enhanced_themes
    - persons
    - organizations
    - tone 前几项
    """
    themes = normalize_theme_tokens(item.get("enhanced_themes", ""))
    persons = normalize_text(item.get("persons", ""))[:300]
    orgs = normalize_text(item.get("organizations", ""))[:300]

    tone = item.get("tone", "")
    tone_head = ",".join(tone.split(",")[:3]) if tone else ""

    key = "||".join([
        ";".join(themes[:20]),
        persons,
        orgs,
        tone_head,
    ])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def seems_local_tv(domain: str) -> bool:
    d = domain.lower()
    return any(h in d for h in LOCAL_TV_HINTS)


def score_originality(item: dict) -> tuple[int, list[str]]:
    """
    分数越高，越优先保留
    """
    url = item.get("url", "") or ""
    domain = item.get("domain", "") or get_domain(url)
    path = get_path(url)

    score = 0
    reasons = []

    # 基础
    if url:
        score += 2
        reasons.append("has_url")
    if domain:
        score += 2
        reasons.append("has_domain")

    # 明显聚合/转载站降权
    if domain in AGGREGATOR_DOMAINS:
        score -= 8
        reasons.append("aggregator_domain")

    # 本地电视台同步稿通常降权
    if seems_local_tv(domain):
        score -= 4
        reasons.append("local_tv_like")

    # 文章页加分
    if any(h in path for h in ARTICLE_HINTS):
        score += 2
        reasons.append("article_like_path")

    # 非正文页降权
    if any(h in path for h in BAD_PATH_HINTS):
        score -= 6
        reasons.append("bad_path_hint")

    # 路径越长越像具体文章
    path_len = len(path)
    if path_len > 40:
        score += 1
        reasons.append("long_path")

    # 主题信息更丰富，优先保留
    enhanced_themes = item.get("enhanced_themes", "") or ""
    if len(enhanced_themes) > 120:
        score += 2
        reasons.append("rich_enhanced_themes")
    elif len(enhanced_themes) > 60:
        score += 1
        reasons.append("some_enhanced_themes")

    # persons / organizations 有内容加分
    if item.get("persons", ""):
        score += 1
        reasons.append("has_persons")
    if item.get("organizations", ""):
        score += 1
        reasons.append("has_organizations")

    return score, reasons


def choose_best(items: list[dict]) -> tuple[dict, list[dict], dict]:
    """
    从一组重复内容里选最优保留项
    """
    scored = []
    for it in items:
        score, reasons = score_originality(it)
        scored.append((score, reasons, it))

    # 先按分数，再按 domain 字典序稳定排序
    scored.sort(key=lambda x: (x[0], x[2].get("domain", "")), reverse=True)

    best_score, best_reasons, best_item = scored[0]

    removed = []
    for score, reasons, it in scored[1:]:
        out = dict(it)
        out["duplicate_of"] = best_item.get("url", "")
        out["duplicate_group_size"] = len(items)
        out["duplicate_remove_reason"] = "syndicated_or_lower_priority_copy"
        out["originality_score"] = score
        out["originality_reasons"] = reasons
        removed.append(out)

    kept = dict(best_item)
    kept["duplicate_group_size"] = len(items)
    kept["originality_score"] = best_score
    kept["originality_reasons"] = best_reasons

    group_info = {
        "group_size": len(items),
        "kept_url": kept.get("url", ""),
        "kept_domain": kept.get("domain", ""),
        "members": [
            {
                "url": it.get("url", ""),
                "domain": it.get("domain", ""),
                "score": score_originality(it)[0],
            }
            for it in items
        ]
    }

    return kept, removed, group_info


def main():
    args = parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    dedup_path = outdir / "gkg_articles_dedup.jsonl"
    removed_path = outdir / "gkg_articles_removed_duplicates.jsonl"
    groups_path = outdir / "gkg_articles_duplicate_groups.jsonl"

    items = list(load_jsonl(input_path))
    total = len(items)

    # 先按内容签名聚类
    groups = defaultdict(list)
    for item in items:
        sig = content_signature(item)
        groups[sig].append(item)

    kept_all = []
    removed_all = []
    group_infos = []

    duplicate_groups = 0
    removed_count = 0

    for sig, members in groups.items():
        if len(members) == 1:
            one = dict(members[0])
            score, reasons = score_originality(one)
            one["duplicate_group_size"] = 1
            one["originality_score"] = score
            one["originality_reasons"] = reasons
            kept_all.append(one)
        else:
            duplicate_groups += 1
            kept, removed, group_info = choose_best(members)
            kept_all.append(kept)
            removed_all.extend(removed)
            group_infos.append(group_info)
            removed_count += len(removed)

    write_jsonl(dedup_path, kept_all)
    write_jsonl(removed_path, removed_all)
    write_jsonl(groups_path, group_infos)

    print("\n=== DONE ===")
    print(f"input_total: {total}")
    print(f"output_kept: {len(kept_all)}")
    print(f"removed_duplicates: {removed_count}")
    print(f"duplicate_groups: {duplicate_groups}")
    print(f"dedup_output: {dedup_path}")
    print(f"removed_output: {removed_path}")
    print(f"groups_output: {groups_path}")


if __name__ == "__main__":
    main()
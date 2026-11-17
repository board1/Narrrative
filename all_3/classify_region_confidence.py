"""
对 region 分配的置信度进行打分，分离「可确定」和「不确定」的数据。
输入: data/gdelt_events_v3/known_refined_url_pool.csv
输出: data/gdelt_events_v3/high_confidence.csv 和 data/gdelt_events_v3/low_confidence.csv
"""
import csv
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse

csv.field_size_limit(sys.maxsize)
import pandas as pd

# 从 v3 pipeline 导入规则，避免双份维护
sys.path.insert(0, str(Path(__file__).parent))
from refine_and_sample_url_pool_v3 import DOMAIN_REGION_RULES, GENERIC_TLDS, TLD_TO_REGION

# 美国机构专用 TLD
US_INSTITUTIONAL_TLDS = {"edu", "gov", "mil", "us"}


def extract_tld(domain):
    parts = domain.rsplit(".", 1)
    return parts[1].lower() if len(parts) == 2 else ""


def classify_confidence(row):
    """
    返回 (confidence, source)
    confidence: high / low
    source: 字符串描述来源
    """
    domain = str(row.get("domain_norm", "")).lower().strip()
    tld = extract_tld(domain)

    # 1. DOMAIN_REGION_RULES 精确匹配 -> HIGH
    if domain in DOMAIN_REGION_RULES:
        return "high", f"domain_rules:{DOMAIN_REGION_RULES[domain]}"

    # 2. 地理明确的 ccTLD -> HIGH
    if tld and tld not in GENERIC_TLDS and tld in TLD_TO_REGION:
        return "high", f"geographic_cctld:{tld}"

    # 3. 美国机构 TLD（.edu, .gov, .mil, .us）-> HIGH
    if tld in US_INSTITUTIONAL_TLDS:
        return "high", f"us_institutional_tld:{tld}"

    # 4. 通用 TLD → US（不确定但有合理推断）-> LOW
    region = str(row.get("country_group_final", ""))
    cc = str(row.get("url_country_code", "")).strip()

    if tld and (tld in GENERIC_TLDS or tld not in TLD_TO_REGION):
        # 如果 url_country_code 也指向 US，稍微可靠一点
        if cc == "US":
            return "low", f"generic_tld_us_supported:{tld}"
        else:
            return "low", f"generic_tld_us_heuristic:{tld}"

    # 5. 其他兜底 -> LOW
    return "low", "fallback"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/gdelt_events_v3/known_refined_url_pool.csv")
    parser.add_argument("--out_dir", default="data/gdelt_events_v3")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input, low_memory=False)
    print(f"Loaded {len(df)} rows from {args.input}")

    # 确保 domain_norm 列存在
    if "domain_norm" not in df.columns:
        raise ValueError("缺少 domain_norm 列，请确保输入来自 v3 pipeline")

    # 逐行分类置信度
    results = df.apply(classify_confidence, axis=1, result_type="expand")
    df["confidence"] = results[0]
    df["source"] = results[1]

    # 分拆
    high = df[df["confidence"] == "high"].copy()
    low = df[df["confidence"] == "low"].copy()

    print(f"\nHigh confidence: {len(high)} ({100*len(high)/len(df):.1f}%)")
    print(f"Low confidence:  {len(low)} ({100*len(low)/len(df):.1f}%)")

    # 统计来源分布
    print("\nHigh confidence sources:")
    for src, cnt in high["source"].value_counts().head(20).items():
        print(f"  {src}: {cnt}")

    print("\nLow confidence sources:")
    for src, cnt in low["source"].value_counts().head(20).items():
        print(f"  {src}: {cnt}")

    # 统计各 event 下各 region 的 high/low 分布
    print("\n=== Per event/region high-confidence coverage ===")
    for event_id in sorted(df["event_id"].unique()):
        sub = df[df["event_id"] == event_id]
        for region in sorted(sub["country_group_final"].unique()):
            rsub = sub[sub["country_group_final"] == region]
            h = (rsub["confidence"] == "high").sum()
            total = len(rsub)
            if total > 0 and h < total:
                print(f"  [{event_id}] [{region}]: high={h}/{total} ({100*h/total:.0f}%) — LOW={total-h} need review")

    # 输出
    keep_cols = [c for c in df.columns]

    high_out = out_dir / "high_confidence.csv"
    low_out = out_dir / "low_confidence.csv"
    source_stats_out = out_dir / "confidence_source_stats.csv"

    high[keep_cols].to_csv(high_out, index=False, encoding="utf-8-sig")
    low[keep_cols].to_csv(low_out, index=False, encoding="utf-8-sig")
    print(f"\nSaved high confidence: {high_out}")
    print(f"Saved low confidence:  {low_out}")

    # 统计 low confidence 中按 domain 去重后输出（供人工审核或 LLM 标注）
    low_domains = low[["domain_norm", "country_group_final", "source"]].drop_duplicates()
    low_domains_out = out_dir / "low_confidence_domains_for_review.csv"
    low_domains.to_csv(low_domains_out, index=False, encoding="utf-8-sig")
    print(f"Saved low confidence domains for review: {low_domains_out} ({len(low_domains)} unique domains)")

    # 统计
    source_stats = df["source"].value_counts().reset_index()
    source_stats.columns = ["source", "count"]
    source_stats["confidence"] = source_stats["source"].apply(
        lambda s: "high" if s.startswith(("domain_rules", "geographic_", "us_institutional")) else "low"
    )
    source_stats.to_csv(source_stats_out, index=False, encoding="utf-8-sig")

    print("\nDone.")


if __name__ == "__main__":
    main()

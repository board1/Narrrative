import re
import random
import argparse
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


# =========================
# 默认路径
# =========================
DEFAULT_INPUT = "data/gdelt_events/all_events_url_pool.csv"
DEFAULT_OUT_DIR = "data/gdelt_events"


# =========================
# 采样参数
# =========================
TARGET_PER_EVENT = 6000          # 每个事件最多保留多少条用于爬虫
TARGET_PER_COUNTRY = 800         # 每个事件内每个国家/地区最多多少条
MAX_PER_DOMAIN_PER_EVENT = 120   # 每个事件内单一domain最多多少条
MIN_PER_COUNTRY_KEEP = 50        # 少于这个数量的国家/地区也保留，但统计中标记


# =========================
# 需要过滤的低质量/聚合/广告/金融行情类站点
# 可根据结果继续扩展
# =========================
BAD_DOMAIN_KEYWORDS = [
    "yahoo.",
    "aol.",
    "msn.",
    "bing.",
    "google.",
    "apple.news",
    "flipboard.",
    "newsbreak.",
    "ground.news",

    "prnewswire.",
    "globenewswire.",
    "businesswire.",
    "accesswire.",
    "einpresswire.",
    "newsfilecorp.",
    "openpr.",
    "einnews.",

    "marketscreener.",
    "streetinsider.",
    "finanznachrichten.",
    "tmcnet.",
    "seekingalpha.",
    "benzinga.",
    "zacks.",
    "morningstar.",
    "marketwatch.",
    "investing.com",

    "iheart.",
    "radio.",
    "podcast",
    "youtube.",
    "tiktok.",
    "facebook.",
    "twitter.",
    "x.com",
    "instagram.",
    "reddit.",

    "bignewsnetwork.",
    "middleeaststar.",
    "arabherald.",
    "menafn.",
]

BAD_URL_PATTERNS = [
    r"/video/",
    r"/videos/",
    r"/podcast",
    r"/live/",
    r"/photos/",
    r"/gallery/",
    r"/slideshow/",
    r"/press-release",
    r"/press_releases",
    r"/sponsored",
    r"/advertorial",
]


# =========================
# Domain -> 国家/地区规则
# 先规则识别，Unknown 后续再交给 LLM
# =========================
DOMAIN_REGION_RULES = {
    # US
    "cnn.com": "US",
    "foxnews.com": "US",
    "nytimes.com": "US",
    "washingtonpost.com": "US",
    "wsj.com": "US",
    "usatoday.com": "US",
    "nbcnews.com": "US",
    "abcnews.go.com": "US",
    "cbsnews.com": "US",
    "npr.org": "US",
    "apnews.com": "US",
    "reuters.com": "Global",
    "bloomberg.com": "US",
    "politico.com": "US",
    "thehill.com": "US",
    "time.com": "US",
    "newsweek.com": "US",

    # UK / Europe
    "bbc.com": "Europe",
    "bbc.co.uk": "Europe",
    "theguardian.com": "Europe",
    "independent.co.uk": "Europe",
    "telegraph.co.uk": "Europe",
    "dailymail.co.uk": "Europe",
    "ft.com": "Europe",
    "dw.com": "Europe",
    "france24.com": "Europe",
    "euronews.com": "Europe",
    "lemonde.fr": "Europe",
    "spiegel.de": "Europe",
    "politico.eu": "Europe",

    # Israel
    "timesofisrael.com": "Israel",
    "jpost.com": "Israel",
    "haaretz.com": "Israel",
    "ynetnews.com": "Israel",
    "israelhayom.com": "Israel",

    # Iran
    "tehrantimes.com": "Iran",
    "presstv.ir": "Iran",
    "irna.ir": "Iran",
    "tasnimnews.com": "Iran",
    "mehrnews.com": "Iran",
    "farsnews.ir": "Iran",

    # Middle East
    "aljazeera.com": "MiddleEast",
    "english.alarabiya.net": "MiddleEast",
    "arabnews.com": "MiddleEast",
    "thenationalnews.com": "MiddleEast",
    "middleeasteye.net": "MiddleEast",
    "dailysabah.com": "MiddleEast",
    "trtworld.com": "MiddleEast",
    "aa.com.tr": "MiddleEast",
    "gulfnews.com": "MiddleEast",
    "khaleejtimes.com": "MiddleEast",

    # South Asia
    "indiatimes.com": "SouthAsia",
    "timesofindia.indiatimes.com": "SouthAsia",
    "hindustantimes.com": "SouthAsia",
    "thehindu.com": "SouthAsia",
    "indianexpress.com": "SouthAsia",
    "ndtv.com": "SouthAsia",
    "firstpost.com": "SouthAsia",
    "dawn.com": "SouthAsia",
    "tribune.com.pk": "SouthAsia",

    # Russia / Eurasia
    "tass.com": "Russia",
    "rt.com": "Russia",
    "sputnikglobe.com": "Russia",
    "pravda.com.ua": "Ukraine",
    "kyivindependent.com": "Ukraine",
    "kyivpost.com": "Ukraine",
    "ukrinform.net": "Ukraine",

    # China / East Asia
    "chinadaily.com.cn": "China",
    "globaltimes.cn": "China",
    "xinhuanet.com": "China",
    "scmp.com": "EastAsia",
    "japantimes.co.jp": "EastAsia",
    "asahi.com": "EastAsia",
    "koreaherald.com": "EastAsia",
}


def normalize_domain(x):
    if pd.isna(x):
        return ""

    x = str(x).strip().lower()

    if not x:
        return ""

    # 如果 domain 字段本身是 URL
    if x.startswith("http"):
        try:
            netloc = urlparse(x).netloc.lower()
            x = netloc
        except Exception:
            pass

    x = x.replace("www.", "")
    x = x.split("/")[0]
    x = x.split(":")[0]
    return x


def domain_from_url(url):
    try:
        netloc = urlparse(str(url)).netloc.lower()
        netloc = netloc.replace("www.", "")
        return netloc.split(":")[0]
    except Exception:
        return ""


def is_bad_domain(domain):
    d = str(domain).lower()
    return any(k in d for k in BAD_DOMAIN_KEYWORDS)


def is_bad_url(url):
    u = str(url).lower()
    return any(re.search(p, u) for p in BAD_URL_PATTERNS)


def infer_region_from_domain(domain):
    d = normalize_domain(domain)

    if not d:
        return "Unknown"

    # 精确匹配
    if d in DOMAIN_REGION_RULES:
        return DOMAIN_REGION_RULES[d]

    # 后缀/包含匹配
    for key, region in DOMAIN_REGION_RULES.items():
        if d == key or d.endswith("." + key) or key in d:
            return region

    # 简单国家域名后缀兜底
    if d.endswith(".uk"):
        return "Europe"
    if d.endswith(".de") or d.endswith(".fr") or d.endswith(".it") or d.endswith(".es") or d.endswith(".nl") or d.endswith(".eu"):
        return "Europe"
    if d.endswith(".ir"):
        return "Iran"
    if d.endswith(".il"):
        return "Israel"
    if d.endswith(".in") or d.endswith(".pk") or d.endswith(".bd"):
        return "SouthAsia"
    if d.endswith(".ru"):
        return "Russia"
    if d.endswith(".ua"):
        return "Ukraine"
    if d.endswith(".cn"):
        return "China"
    if d.endswith(".jp") or d.endswith(".kr"):
        return "EastAsia"

    return "Unknown"


def clean_url_pool(df):
    required = ["event_id", "url"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"缺少必要列: {c}")

    if "domain" not in df.columns:
        df["domain"] = ""

    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.startswith("http", na=False)].copy()

    # domain 优先使用已有字段，否则从 url 抽取
    df["domain_norm"] = df["domain"].apply(normalize_domain)
    missing_domain = df["domain_norm"].eq("")
    df.loc[missing_domain, "domain_norm"] = df.loc[missing_domain, "url"].apply(domain_from_url)

    # 过滤低质量域名和URL类型
    df["bad_domain"] = df["domain_norm"].apply(is_bad_domain)
    df["bad_url"] = df["url"].apply(is_bad_url)

    df = df[~df["bad_domain"] & ~df["bad_url"]].copy()

    # 全局去重：同一个事件内同一URL只保留一条
    df = df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    # region 规则识别
    if "region_rule" not in df.columns:
        df["region_rule"] = df["domain_norm"].apply(infer_region_from_domain)

    # 先用规则结果作为 country_group_final
    if "country_group_final" not in df.columns:
        df["country_group_final"] = df["region_rule"]
    else:
        df["country_group_final"] = df["country_group_final"].fillna("")
        df.loc[df["country_group_final"].eq("") | df["country_group_final"].eq("Unknown"), "country_group_final"] = df["region_rule"]

    return df


def cap_domain_per_event(df, max_per_domain=120, seed=42):
    parts = []

    for (event_id, domain), sub in df.groupby(["event_id", "domain_norm"]):
        if len(sub) > max_per_domain:
            sub = sub.sample(max_per_domain, random_state=seed)
        parts.append(sub)

    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def stratified_sample(df, target_per_event=6000, target_per_country=800, seed=42):
    random.seed(seed)

    sampled_events = []

    for event_id, event_df in df.groupby("event_id"):
        event_df = event_df.copy()

        # 先按国家/地区限额
        country_parts = []
        for country, sub in event_df.groupby("country_group_final"):
            if len(sub) > target_per_country:
                sub = sub.sample(target_per_country, random_state=seed)
            country_parts.append(sub)

        event_sample = pd.concat(country_parts, ignore_index=True)

        # 如果事件总体仍超过目标，再按国家/地区比例抽
        if len(event_sample) > target_per_event:
            event_sample = (
                event_sample
                .groupby("country_group_final", group_keys=False)
                .apply(lambda x: x.sample(
                    max(1, int(target_per_event * len(x) / len(event_sample))),
                    random_state=seed
                ))
                .reset_index(drop=True)
            )

            # 由于四舍五入可能略少，补齐
            if len(event_sample) < target_per_event:
                remaining = event_df.drop(event_sample.index, errors="ignore")
                need = target_per_event - len(event_sample)
                if len(remaining) > 0:
                    extra = remaining.sample(min(need, len(remaining)), random_state=seed)
                    event_sample = pd.concat([event_sample, extra], ignore_index=True)

        sampled_events.append(event_sample)

    return pd.concat(sampled_events, ignore_index=True) if sampled_events else pd.DataFrame()


def make_stats(df, out_path):
    stats = (
        df.groupby(["event_id", "country_group_final"])
        .agg(
            rows=("url", "count"),
            domains=("domain_norm", "nunique")
        )
        .reset_index()
        .sort_values(["event_id", "rows"], ascending=[True, False])
    )

    stats.to_csv(out_path, index=False, encoding="utf-8-sig")
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--out_dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--target_per_event", type=int, default=TARGET_PER_EVENT)
    parser.add_argument("--target_per_country", type=int, default=TARGET_PER_COUNTRY)
    parser.add_argument("--max_per_domain", type=int, default=MAX_PER_DOMAIN_PER_EVENT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_refined = out_dir / "all_events_refined_url_pool.csv"
    out_sample = out_dir / "all_events_crawl_sample.csv"
    out_stats_refined = out_dir / "refine_stats_by_event_country.csv"
    out_stats_sample = out_dir / "sample_stats_by_event_country.csv"

    print("[Load]", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    print("Raw rows:", len(df))

    print("\n[Clean URL pool]")
    refined = clean_url_pool(df)
    print("After basic filter:", len(refined))

    print("\n[Cap domain per event]")
    refined = cap_domain_per_event(
        refined,
        max_per_domain=args.max_per_domain,
        seed=args.seed
    )
    print("After domain cap:", len(refined))

    refined.to_csv(out_refined, index=False, encoding="utf-8-sig")
    print("Saved refined:", out_refined)

    print("\n[Refined stats]")
    stats_refined = make_stats(refined, out_stats_refined)
    print(stats_refined.head(30))
    print("Saved refined stats:", out_stats_refined)

    print("\n[Stratified sample]")
    sample = stratified_sample(
        refined,
        target_per_event=args.target_per_event,
        target_per_country=args.target_per_country,
        seed=args.seed
    )

    # 爬虫输入尽量简洁
    crawl_cols = [
        "event_id",
        "event_start",
        "event_end",
        "day",
        "gdelt_timestamp",
        "country_group_final",
        "region_rule",
        "domain_norm",
        "url",
        "themes",
        "v2_themes",
        "locations",
        "v2_locations",
        "persons",
        "v2_persons",
        "organizations",
        "v2_organizations",
        "all_names",
        "v2_tone",
        "actor_hits",
        "event_hits",
        "total_hits",
    ]

    sample = sample[[c for c in crawl_cols if c in sample.columns]].copy()
    sample = sample.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    sample.to_csv(out_sample, index=False, encoding="utf-8-sig")
    print("Saved crawl sample:", out_sample, "rows=", len(sample))

    print("\n[Sample stats]")
    stats_sample = make_stats(sample, out_stats_sample)
    print(stats_sample.head(50))
    print("Saved sample stats:", out_stats_sample)

    print("\nRows by event:")
    print(sample["event_id"].value_counts())

    print("\nRows by country/region:")
    print(sample["country_group_final"].value_counts())

    print("\nDone.")


if __name__ == "__main__":
    main()
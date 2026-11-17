import re
import argparse
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


# =========================
# 默认路径
# =========================
DEFAULT_INPUT = "data/gdelt_events/all_events_url_pool.csv"
DEFAULT_OUT_DIR = "data/gdelt_events_v2"


# =========================
# 采样参数
# =========================
DEFAULT_TARGET_PER_EVENT_REGION = 600
DEFAULT_MAX_PER_DOMAIN_EVENT_REGION = 80
DEFAULT_MIN_REGION_ROWS = 80
DEFAULT_SEED = 42


# =========================
# 每个事件保留的核心国家/地区
# 不同事件不强行统一国家集合
# =========================
EVENT_TARGET_REGIONS = {
    "gaza_conflict_2023": [
        "US", "Europe", "MiddleEast", "Israel",
        "SouthAsia", "China", "Russia", "EastAsia"
    ],

    "russia_ukraine_invasion_2022": [
        "US", "Europe", "Russia", "Ukraine",
        "China", "SouthAsia", "MiddleEast", "EastAsia"
    ],

    "us_iran_israel_2026": [
        "US", "Europe", "MiddleEast", "Israel",
        "Iran", "China", "Russia", "SouthAsia", "EastAsia"
    ],

    "us_china_trade_war_2018": [
        "US", "China", "Europe", "SouthAsia",
        "EastAsia", "Russia", "MiddleEast", "Global"
    ],

    "trump_liberation_day_tariffs_2025": [
        "US", "China", "Europe", "SouthAsia",
        "EastAsia", "Russia", "MiddleEast", "Global"
    ],
}


# =========================
# 低质量/聚合/广告/金融行情类站点
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
    "nasdaq.com",
    "fool.com",

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
    r"/tag/",
    r"/author/",
]


# =========================
# Domain -> 国家/地区规则
# 后面你可以不断扩展这个表
# =========================
DOMAIN_REGION_RULES = {
    # Global / wire
    "reuters.com": "Global",
    "apnews.com": "Global",
    "afp.com": "Global",

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
    "bloomberg.com": "US",
    "politico.com": "US",
    "thehill.com": "US",
    "time.com": "US",
    "newsweek.com": "US",
    "latimes.com": "US",
    "chicagotribune.com": "US",
    "nypost.com": "US",
    "axios.com": "US",
    "voanews.com": "US",
    "foreignpolicy.com": "US",

    # Europe
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
    "sky.com": "Europe",
    "skynews.com": "Europe",
    "standard.co.uk": "Europe",
    "express.co.uk": "Europe",
    "mirror.co.uk": "Europe",
    "gbnews.com": "Europe",
    "rte.ie": "Europe",
    "irishtimes.com": "Europe",
    "ansa.it": "Europe",
    "elpais.com": "Europe",

    # Israel
    "timesofisrael.com": "Israel",
    "jpost.com": "Israel",
    "haaretz.com": "Israel",
    "ynetnews.com": "Israel",
    "israelhayom.com": "Israel",
    "i24news.tv": "Israel",
    "kan.org.il": "Israel",

    # Iran
    "tehrantimes.com": "Iran",
    "presstv.ir": "Iran",
    "irna.ir": "Iran",
    "tasnimnews.com": "Iran",
    "mehrnews.com": "Iran",
    "farsnews.ir": "Iran",
    "isna.ir": "Iran",

    # Middle East
    "aljazeera.com": "MiddleEast",
    "english.alarabiya.net": "MiddleEast",
    "alarabiya.net": "MiddleEast",
    "arabnews.com": "MiddleEast",
    "thenationalnews.com": "MiddleEast",
    "middleeasteye.net": "MiddleEast",
    "dailysabah.com": "MiddleEast",
    "trtworld.com": "MiddleEast",
    "aa.com.tr": "MiddleEast",
    "gulfnews.com": "MiddleEast",
    "khaleejtimes.com": "MiddleEast",
    "dohanews.co": "MiddleEast",
    "jordantimes.com": "MiddleEast",
    "naharnet.com": "MiddleEast",
    "lorientlejour.com": "MiddleEast",
    "kuwaittimes.com": "MiddleEast",

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
    "geo.tv": "SouthAsia",
    "thenews.com.pk": "SouthAsia",
    "bdnews24.com": "SouthAsia",

    # Russia / Ukraine
    "tass.com": "Russia",
    "rt.com": "Russia",
    "sputnikglobe.com": "Russia",
    "interfax.com": "Russia",
    "pravda.com.ua": "Ukraine",
    "kyivindependent.com": "Ukraine",
    "kyivpost.com": "Ukraine",
    "ukrinform.net": "Ukraine",

    # China / East Asia
    "chinadaily.com.cn": "China",
    "globaltimes.cn": "China",
    "xinhuanet.com": "China",
    "cgtn.com": "China",
    "people.com.cn": "China",
    "scmp.com": "EastAsia",
    "japantimes.co.jp": "EastAsia",
    "asahi.com": "EastAsia",
    "koreaherald.com": "EastAsia",
    "koreatimes.co.kr": "EastAsia",
    "straitstimes.com": "EastAsia",
}


def normalize_domain(x):
    if pd.isna(x):
        return ""

    x = str(x).strip().lower()

    if x.startswith("http"):
        try:
            x = urlparse(x).netloc.lower()
        except Exception:
            pass

    x = x.replace("www.", "")
    x = x.split("/")[0]
    x = x.split(":")[0]
    return x


def domain_from_url(url):
    try:
        netloc = urlparse(str(url)).netloc.lower()
        return netloc.replace("www.", "").split(":")[0]
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

    if d in DOMAIN_REGION_RULES:
        return DOMAIN_REGION_RULES[d]

    for key, region in DOMAIN_REGION_RULES.items():
        if d == key or d.endswith("." + key) or key in d:
            return region

    # 域名后缀兜底
    europe_suffix = (
        ".uk", ".de", ".fr", ".it", ".es", ".nl", ".eu", ".ie", ".be",
        ".at", ".ch", ".se", ".no", ".dk", ".fi", ".pl", ".cz", ".pt"
    )
    if d.endswith(europe_suffix):
        return "Europe"
    if d.endswith(".ir"):
        return "Iran"
    if d.endswith(".il"):
        return "Israel"
    if d.endswith((".in", ".pk", ".bd", ".lk")):
        return "SouthAsia"
    if d.endswith(".ru"):
        return "Russia"
    if d.endswith(".ua"):
        return "Ukraine"
    if d.endswith(".cn"):
        return "China"
    if d.endswith((".jp", ".kr", ".sg", ".hk", ".tw")):
        return "EastAsia"
    if d.endswith((".sa", ".ae", ".qa", ".tr", ".eg", ".jo", ".lb", ".kw", ".bh", ".om")):
        return "MiddleEast"

    return "Unknown"


def load_and_basic_clean(input_path):
    print("[Load]", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    print("Raw rows:", len(df))

    if "event_id" not in df.columns:
        raise ValueError("缺少 event_id 列")
    if "url" not in df.columns:
        raise ValueError("缺少 url 列")

    if "domain" not in df.columns:
        df["domain"] = ""

    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.startswith("http", na=False)].copy()

    df["domain_norm"] = df["domain"].apply(normalize_domain)
    missing_domain = df["domain_norm"].eq("")
    df.loc[missing_domain, "domain_norm"] = df.loc[missing_domain, "url"].apply(domain_from_url)

    df = df[~df["domain_norm"].apply(is_bad_domain)].copy()
    df = df[~df["url"].apply(is_bad_url)].copy()

    df = df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    df["region_rule"] = df["domain_norm"].apply(infer_region_from_domain)

    # 如果之前已有 country_group_final，优先保留非 Unknown；否则用规则
    if "country_group_final" not in df.columns:
        df["country_group_final"] = df["region_rule"]
    else:
        df["country_group_final"] = df["country_group_final"].fillna("").astype(str)
        bad = df["country_group_final"].isin(["", "Unknown", "nan", "None"])
        df.loc[bad, "country_group_final"] = df.loc[bad, "region_rule"]

    print("After basic clean:", len(df))
    return df


def split_known_unknown(df, out_dir):
    unknown = df[df["country_group_final"].eq("Unknown")].copy()
    known = df[~df["country_group_final"].eq("Unknown")].copy()

    unknown_out = out_dir / "unknown_for_llm_region.csv"

    unknown_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "domain_norm", "url", "themes", "v2_themes", "locations",
        "v2_locations", "persons", "v2_persons", "organizations",
        "v2_organizations", "all_names", "v2_tone",
        "actor_hits", "event_hits", "total_hits"
    ]
    unknown[[c for c in unknown_cols if c in unknown.columns]].to_csv(
        unknown_out, index=False, encoding="utf-8-sig"
    )

    print("Known rows:", len(known))
    print("Unknown rows:", len(unknown))
    print("Saved unknown for LLM:", unknown_out)

    return known, unknown


def keep_event_target_regions(df):
    kept = []

    for event_id, sub in df.groupby("event_id"):
        targets = EVENT_TARGET_REGIONS.get(event_id)

        if targets is None:
            print(f"[Warning] No target region config for event: {event_id}, keep all known regions.")
            kept.append(sub)
            continue

        before = len(sub)
        sub = sub[sub["country_group_final"].isin(targets)].copy()
        after = len(sub)

        print(f"[Target regions] {event_id}: {before} -> {after}")
        kept.append(sub)

    return pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()


def cap_domain_event_region(df, max_per_domain=80, seed=42):
    parts = []

    for (event_id, region, domain), sub in df.groupby(["event_id", "country_group_final", "domain_norm"]):
        if len(sub) > max_per_domain:
            sub = sub.sample(max_per_domain, random_state=seed)
        parts.append(sub)

    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    print("After domain cap:", len(out))
    return out


def sample_event_region(df, target_per_event_region=600, min_region_rows=80, seed=42):
    samples = []
    low_resource = []

    for (event_id, region), sub in df.groupby(["event_id", "country_group_final"]):
        n = len(sub)

        if n < min_region_rows:
            low_resource.append({
                "event_id": event_id,
                "country_group_final": region,
                "available_rows": n,
                "note": "below_min_region_rows_but_kept"
            })
            take = n
        else:
            take = min(target_per_event_region, n)

        sampled = sub.sample(take, random_state=seed) if n > take else sub.copy()
        samples.append(sampled)

    sample = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame()
    low_df = pd.DataFrame(low_resource)

    print("Sample rows:", len(sample))
    return sample, low_df


def save_stats(df, out_path):
    if df.empty:
        pd.DataFrame().to_csv(out_path, index=False)
        return pd.DataFrame()

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
    parser.add_argument("--target_per_event_region", type=int, default=DEFAULT_TARGET_PER_EVENT_REGION)
    parser.add_argument("--max_per_domain_event_region", type=int, default=DEFAULT_MAX_PER_DOMAIN_EVENT_REGION)
    parser.add_argument("--min_region_rows", type=int, default=DEFAULT_MIN_REGION_ROWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_known_refined = out_dir / "known_refined_url_pool.csv"
    out_target_refined = out_dir / "target_region_refined_url_pool.csv"
    out_sample = out_dir / "all_events_crawl_sample_v2.csv"
    out_stats_refined = out_dir / "target_region_refined_stats.csv"
    out_stats_sample = out_dir / "sample_stats_by_event_region_v2.csv"
    out_low = out_dir / "low_resource_event_regions.csv"

    df = load_and_basic_clean(args.input)

    known, unknown = split_known_unknown(df, out_dir)
    known.to_csv(out_known_refined, index=False, encoding="utf-8-sig")
    print("Saved known refined:", out_known_refined)

    target_df = keep_event_target_regions(known)
    target_df = cap_domain_event_region(
        target_df,
        max_per_domain=args.max_per_domain_event_region,
        seed=args.seed
    )

    target_df.to_csv(out_target_refined, index=False, encoding="utf-8-sig")
    print("Saved target refined:", out_target_refined)

    stats_refined = save_stats(target_df, out_stats_refined)
    print("\n[Target refined stats]")
    print(stats_refined.head(80))
    print("Saved:", out_stats_refined)

    sample, low_df = sample_event_region(
        target_df,
        target_per_event_region=args.target_per_event_region,
        min_region_rows=args.min_region_rows,
        seed=args.seed
    )

    crawl_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "country_group_final", "region_rule", "domain_norm", "url",
        "themes", "v2_themes", "locations", "v2_locations",
        "persons", "v2_persons", "organizations", "v2_organizations",
        "all_names", "v2_tone", "actor_hits", "event_hits", "total_hits"
    ]
    sample = sample[[c for c in crawl_cols if c in sample.columns]].copy()
    sample = sample.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    sample.to_csv(out_sample, index=False, encoding="utf-8-sig")
    print("Saved crawl sample:", out_sample, "rows=", len(sample))

    stats_sample = save_stats(sample, out_stats_sample)
    print("\n[Sample stats]")
    print(stats_sample.head(100))
    print("Saved:", out_stats_sample)

    low_df.to_csv(out_low, index=False, encoding="utf-8-sig")
    print("Saved low-resource event regions:", out_low)

    print("\nRows by event:")
    print(sample["event_id"].value_counts())

    print("\nRows by region:")
    print(sample["country_group_final"].value_counts())

    print("\nDone.")


if __name__ == "__main__":
    main()
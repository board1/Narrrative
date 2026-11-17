import pandas as pd
from pathlib import Path
from urllib.parse import urlparse

# =========================
# 路径
# =========================
BASE_DIR = Path("data/gdelt_events_v2")

KNOWN_FILE = BASE_DIR / "known_refined_url_pool.csv"
UNKNOWN_FILE = BASE_DIR / "unknown_for_llm_region.csv"

CURATED_FILE = BASE_DIR / "curated_sources.csv"

OUT_RELABELED_UNKNOWN = BASE_DIR / "unknown_relabel_by_curated_sources.csv"
OUT_MERGED = BASE_DIR / "known_plus_curated_relabel_url_pool.csv"
OUT_SAMPLE = BASE_DIR / "all_events_crawl_sample_v3.csv"
OUT_STATS = BASE_DIR / "sample_stats_by_event_region_v3.csv"

# =========================
# 采样参数
# =========================
TARGET_PER_EVENT_REGION = 600
MAX_PER_DOMAIN_EVENT_REGION = 80
SEED = 42

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


def normalize_domain(x):
    if pd.isna(x):
        return ""
    x = str(x).strip().lower()
    if x.startswith("http"):
        x = urlparse(x).netloc.lower()
    x = x.replace("www.", "")
    x = x.split("/")[0].split(":")[0]
    return x


def domain_from_url(url):
    try:
        return urlparse(str(url)).netloc.lower().replace("www.", "").split(":")[0]
    except Exception:
        return ""


def create_curated_sources():
    if CURATED_FILE.exists():
        print("[Skip] curated source file exists:", CURATED_FILE)
        return

    rows = [
        # Iran
        ("Iran", "presstv.ir", "Press TV", "state_media", 1),
        ("Iran", "tehrantimes.com", "Tehran Times", "national_media", 1),
        ("Iran", "irna.ir", "IRNA", "state_news_agency", 1),
        ("Iran", "tasnimnews.com", "Tasnim News Agency", "news_agency", 2),
        ("Iran", "mehrnews.com", "Mehr News Agency", "news_agency", 2),
        ("Iran", "farsnews.ir", "Fars News Agency", "news_agency", 2),
        ("Iran", "isna.ir", "ISNA", "news_agency", 2),

        # Israel
        ("Israel", "timesofisrael.com", "The Times of Israel", "national_media", 1),
        ("Israel", "jpost.com", "The Jerusalem Post", "national_media", 1),
        ("Israel", "haaretz.com", "Haaretz", "national_media", 1),
        ("Israel", "ynetnews.com", "Ynetnews", "national_media", 2),
        ("Israel", "israelhayom.com", "Israel Hayom", "national_media", 2),
        ("Israel", "i24news.tv", "i24NEWS", "national_media", 2),

        # Ukraine
        ("Ukraine", "kyivindependent.com", "The Kyiv Independent", "national_media", 1),
        ("Ukraine", "kyivpost.com", "Kyiv Post", "national_media", 1),
        ("Ukraine", "ukrinform.net", "Ukrinform", "state_news_agency", 1),
        ("Ukraine", "pravda.com.ua", "Ukrainska Pravda", "national_media", 2),
        ("Ukraine", "suspilne.media", "Suspilne", "public_broadcaster", 2),

        # Russia
        ("Russia", "tass.com", "TASS", "state_news_agency", 1),
        ("Russia", "rt.com", "RT", "state_media", 1),
        ("Russia", "sputnikglobe.com", "Sputnik", "state_media", 2),
        ("Russia", "interfax.com", "Interfax", "news_agency", 2),
        ("Russia", "iz.ru", "Izvestia", "national_media", 2),
        ("Russia", "kommersant.ru", "Kommersant", "national_media", 2),

        # China
        ("China", "chinadaily.com.cn", "China Daily", "state_media", 1),
        ("China", "globaltimes.cn", "Global Times", "state_media", 1),
        ("China", "cgtn.com", "CGTN", "state_media", 1),
        ("China", "xinhuanet.com", "Xinhua", "state_news_agency", 1),
        ("China", "people.com.cn", "People's Daily", "state_media", 2),

        # MiddleEast
        ("MiddleEast", "aljazeera.com", "Al Jazeera", "regional_media", 1),
        ("MiddleEast", "arabnews.com", "Arab News", "regional_media", 1),
        ("MiddleEast", "english.alarabiya.net", "Al Arabiya English", "regional_media", 1),
        ("MiddleEast", "thenationalnews.com", "The National", "regional_media", 1),
        ("MiddleEast", "middleeasteye.net", "Middle East Eye", "regional_media", 2),
        ("MiddleEast", "gulfnews.com", "Gulf News", "regional_media", 2),
        ("MiddleEast", "khaleejtimes.com", "Khaleej Times", "regional_media", 2),
        ("MiddleEast", "trtworld.com", "TRT World", "regional_media", 2),
        ("MiddleEast", "dailysabah.com", "Daily Sabah", "regional_media", 2),

        # EastAsia
        ("EastAsia", "scmp.com", "South China Morning Post", "regional_media", 1),
        ("EastAsia", "japantimes.co.jp", "The Japan Times", "national_media", 1),
        ("EastAsia", "asahi.com", "Asahi Shimbun", "national_media", 2),
        ("EastAsia", "koreaherald.com", "The Korea Herald", "national_media", 1),
        ("EastAsia", "koreatimes.co.kr", "The Korea Times", "national_media", 2),
        ("EastAsia", "straitstimes.com", "The Straits Times", "national_media", 1),

        # SouthAsia
        ("SouthAsia", "indiatimes.com", "India Times", "national_media", 1),
        ("SouthAsia", "timesofindia.indiatimes.com", "Times of India", "national_media", 1),
        ("SouthAsia", "hindustantimes.com", "Hindustan Times", "national_media", 1),
        ("SouthAsia", "thehindu.com", "The Hindu", "national_media", 1),
        ("SouthAsia", "indianexpress.com", "Indian Express", "national_media", 1),
        ("SouthAsia", "ndtv.com", "NDTV", "national_media", 1),
        ("SouthAsia", "firstpost.com", "Firstpost", "national_media", 2),
        ("SouthAsia", "dawn.com", "Dawn", "national_media", 1),
        ("SouthAsia", "tribune.com.pk", "The Express Tribune", "national_media", 2),
    ]

    df = pd.DataFrame(
        rows,
        columns=["region", "domain", "source_name", "source_type", "priority"]
    )
    df["domain_norm"] = df["domain"].apply(normalize_domain)
    df.to_csv(CURATED_FILE, index=False, encoding="utf-8-sig")
    print("[Created]", CURATED_FILE)


def load_curated_map():
    curated = pd.read_csv(CURATED_FILE)
    curated["domain_norm"] = curated["domain"].apply(normalize_domain)
    return dict(zip(curated["domain_norm"], curated["region"]))


def relabel_by_curated(df, curated_map):
    if "domain_norm" not in df.columns:
        if "domain" in df.columns:
            df["domain_norm"] = df["domain"].apply(normalize_domain)
        else:
            df["domain_norm"] = df["url"].apply(domain_from_url)

    def match_region(domain):
        d = normalize_domain(domain)
        if d in curated_map:
            return curated_map[d]
        for key, region in curated_map.items():
            if d == key or d.endswith("." + key):
                return region
        return "Unknown"

    df["curated_region"] = df["domain_norm"].apply(match_region)
    hit = df[df["curated_region"] != "Unknown"].copy()
    hit["country_group_final"] = hit["curated_region"]
    return hit


def filter_target_regions(df):
    parts = []
    for event_id, sub in df.groupby("event_id"):
        targets = EVENT_TARGET_REGIONS.get(event_id, [])
        sub = sub[sub["country_group_final"].isin(targets)].copy()
        parts.append(sub)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def cap_domain(df):
    parts = []
    for _, sub in df.groupby(["event_id", "country_group_final", "domain_norm"]):
        if len(sub) > MAX_PER_DOMAIN_EVENT_REGION:
            sub = sub.sample(MAX_PER_DOMAIN_EVENT_REGION, random_state=SEED)
        parts.append(sub)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def sample_event_region(df):
    parts = []
    for _, sub in df.groupby(["event_id", "country_group_final"]):
        n = len(sub)
        take = min(TARGET_PER_EVENT_REGION, n)
        if n > take:
            sub = sub.sample(take, random_state=SEED)
        parts.append(sub)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def save_stats(df):
    stats = (
        df.groupby(["event_id", "country_group_final"])
        .agg(rows=("url", "count"), domains=("domain_norm", "nunique"))
        .reset_index()
        .sort_values(["event_id", "rows"], ascending=[True, False])
    )
    stats.to_csv(OUT_STATS, index=False, encoding="utf-8-sig")
    print(stats.head(100))
    print("[Saved stats]", OUT_STATS)


def main():
    create_curated_sources()
    curated_map = load_curated_map()

    known = pd.read_csv(KNOWN_FILE, low_memory=False)
    unknown = pd.read_csv(UNKNOWN_FILE, low_memory=False)

    if "domain_norm" not in known.columns:
        if "domain" in known.columns:
            known["domain_norm"] = known["domain"].apply(normalize_domain)
        else:
            known["domain_norm"] = known["url"].apply(domain_from_url)

    print("Known rows:", len(known))
    print("Unknown rows:", len(unknown))

    relabeled_unknown = relabel_by_curated(unknown, curated_map)
    relabeled_unknown.to_csv(OUT_RELABELED_UNKNOWN, index=False, encoding="utf-8-sig")

    print("Relabeled unknown rows:", len(relabeled_unknown))
    print(relabeled_unknown["country_group_final"].value_counts())
    print("[Saved]", OUT_RELABELED_UNKNOWN)

    merged = pd.concat([known, relabeled_unknown], ignore_index=True)
    merged = merged.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    merged = filter_target_regions(merged)
    merged = cap_domain(merged)

    merged.to_csv(OUT_MERGED, index=False, encoding="utf-8-sig")
    print("[Saved merged]", OUT_MERGED, "rows=", len(merged))

    sample = sample_event_region(merged)

    crawl_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "country_group_final", "domain_norm", "url",
        "themes", "v2_themes", "locations", "v2_locations",
        "persons", "v2_persons", "organizations", "v2_organizations",
        "all_names", "v2_tone", "actor_hits", "event_hits", "total_hits"
    ]
    sample = sample[[c for c in crawl_cols if c in sample.columns]].copy()
    sample.to_csv(OUT_SAMPLE, index=False, encoding="utf-8-sig")

    print("[Saved sample]", OUT_SAMPLE, "rows=", len(sample))
    print("\nRows by event:")
    print(sample["event_id"].value_counts())
    print("\nRows by region:")
    print(sample["country_group_final"].value_counts())

    save_stats(sample)


if __name__ == "__main__":
    main()
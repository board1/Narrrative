"""精简版 refine + sample，只处理 COVID-19 起源 + COP28 两个事件"""
import re, csv, sys, argparse
from pathlib import Path
from urllib.parse import urlparse

csv.field_size_limit(sys.maxsize)
import pandas as pd

DEFAULT_INPUT = "data/gdelt_events/all_events_url_pool.csv"
DEFAULT_DOMAIN_COUNTRY = "../all_3/data/gdelt_events/domain_country.csv"
DEFAULT_OUT_DIR = "data/gdelt_events_v3"

DEFAULT_TARGET_PER_EVENT_REGION = 600
DEFAULT_MAX_PER_DOMAIN_EVENT_REGION = 80
DEFAULT_MIN_REGION_ROWS = 80
DEFAULT_SEED = 42

EVENT_TARGET_REGIONS = {
    "covid_origin_investigation_2021": [
        "US", "China", "Europe", "EastAsia",
        "SouthAsia", "Russia", "MiddleEast", "Global"
    ],
    "cop28_dubai_2023": [
        "US", "China", "Europe", "MiddleEast",
        "SouthAsia", "EastAsia", "Russia", "Global"
    ],
}

# ================ TLD / domain 规则（与 all_3 v3 一致） ================

GENERIC_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "us", "int",
    "news", "media", "info", "biz", "pro", "center", "world",
    "tv", "fm", "io", "co", "to", "ws", "nu", "tk", "cc", "ai",
    "sh", "me", "ly", "so", "st", "ac",
}

TLD_TO_REGION = {
    "uk": "Europe", "de": "Europe", "fr": "Europe", "it": "Europe",
    "es": "Europe", "nl": "Europe", "ie": "Europe", "be": "Europe",
    "at": "Europe", "ch": "Europe", "se": "Europe", "no": "Europe",
    "dk": "Europe", "fi": "Europe", "pl": "Europe", "cz": "Europe",
    "pt": "Europe", "gr": "Europe", "hu": "Europe", "ro": "Europe",
    "bg": "Europe", "hr": "Europe", "sk": "Europe", "si": "Europe",
    "lt": "Europe", "lv": "Europe", "ee": "Europe", "lu": "Europe",
    "mt": "Europe", "cy": "Europe", "is": "Europe", "eu": "Europe",
    "rs": "Europe", "ba": "Europe", "mk": "Europe", "al": "Europe",
    "md": "Europe", "gi": "Europe", "im": "Europe", "gg": "Europe",
    "je": "Europe", "fo": "Europe", "ax": "Europe", "li": "Europe",
    "mc": "Europe", "ad": "Europe", "sm": "Europe", "va": "Europe",
    "ru": "Russia", "ua": "Ukraine",
    "kz": "Russia", "kg": "Russia", "uz": "Russia", "tm": "Russia",
    "tj": "Russia", "az": "Russia", "am": "Russia", "ge": "Russia", "by": "Russia",
    "cn": "China",
    "jp": "EastAsia", "kr": "EastAsia", "sg": "EastAsia",
    "hk": "EastAsia", "tw": "EastAsia", "mo": "EastAsia", "mn": "EastAsia", "kp": "EastAsia",
    "kh": "EastAsia", "la": "EastAsia", "th": "EastAsia",
    "vn": "EastAsia", "ph": "EastAsia", "my": "EastAsia",
    "id": "EastAsia", "bn": "EastAsia", "tl": "EastAsia", "mm": "EastAsia",
    "in": "SouthAsia", "pk": "SouthAsia", "bd": "SouthAsia",
    "lk": "SouthAsia", "np": "SouthAsia", "mv": "SouthAsia", "bt": "SouthAsia",
    "il": "Israel", "ir": "Iran",
    "sa": "MiddleEast", "ae": "MiddleEast", "qa": "MiddleEast",
    "kw": "MiddleEast", "bh": "MiddleEast", "om": "MiddleEast",
    "tr": "MiddleEast", "eg": "MiddleEast", "jo": "MiddleEast",
    "lb": "MiddleEast", "sy": "MiddleEast", "iq": "MiddleEast",
    "ye": "MiddleEast", "ps": "MiddleEast",
    "ly": "MiddleEast", "dz": "MiddleEast", "ma": "MiddleEast",
    "tn": "MiddleEast", "sd": "MiddleEast", "so": "MiddleEast", "mr": "MiddleEast",
    "au": "EastAsia", "nz": "EastAsia",
    "za": "SouthAsia", "ng": "SouthAsia", "ke": "SouthAsia",
    "et": "SouthAsia", "tz": "SouthAsia", "gh": "SouthAsia",
    "ug": "SouthAsia", "zm": "SouthAsia", "zw": "SouthAsia",
    "ca": "US", "mx": "US",
    "br": "US", "ar": "US", "cl": "US", "co": "US", "pe": "US",
    "ve": "US", "ec": "US", "bo": "US", "py": "US", "uy": "US",
}

COUNTRY_CODE_TO_REGION = {
    "US": "US", "GB": "Europe", "UK": "Europe", "DE": "Europe", "FR": "Europe",
    "IT": "Europe", "ES": "Europe", "NL": "Europe", "BE": "Europe", "AT": "Europe",
    "CH": "Europe", "SE": "Europe", "NO": "Europe", "DK": "Europe", "FI": "Europe",
    "PL": "Europe", "CZ": "Europe", "PT": "Europe", "GR": "Europe", "HU": "Europe",
    "RO": "Europe", "BG": "Europe", "HR": "Europe", "SK": "Europe", "SI": "Europe",
    "LT": "Europe", "LV": "Europe", "EE": "Europe", "LU": "Europe", "MT": "Europe",
    "CY": "Europe", "IS": "Europe", "IE": "Europe", "FO": "Europe", "GI": "Europe",
    "IM": "Europe", "RS": "Europe", "BA": "Europe", "MK": "Europe", "AL": "Europe",
    "MD": "Europe", "EU": "Europe", "RU": "Russia", "UA": "Ukraine",
    "KZ": "Russia", "KG": "Russia", "UZ": "Russia", "TM": "Russia",
    "TJ": "Russia", "AZ": "Russia", "AM": "Russia", "GE": "Russia",
    "CN": "China", "JP": "EastAsia", "KR": "EastAsia", "SG": "EastAsia",
    "HK": "EastAsia", "TW": "EastAsia", "MO": "EastAsia", "MN": "EastAsia",
    "KH": "EastAsia", "LA": "EastAsia", "TH": "EastAsia", "VN": "EastAsia",
    "PH": "EastAsia", "MY": "EastAsia", "ID": "EastAsia", "BN": "EastAsia",
    "TL": "EastAsia", "MM": "EastAsia", "KP": "EastAsia",
    "IN": "SouthAsia", "PK": "SouthAsia", "BD": "SouthAsia",
    "LK": "SouthAsia", "NP": "SouthAsia", "MV": "SouthAsia", "BT": "SouthAsia",
    "IL": "Israel", "IR": "Iran",
    "SA": "MiddleEast", "AE": "MiddleEast", "QA": "MiddleEast",
    "KW": "MiddleEast", "BH": "MiddleEast", "OM": "MiddleEast",
    "TR": "MiddleEast", "EG": "MiddleEast", "JO": "MiddleEast",
    "LB": "MiddleEast", "SY": "MiddleEast", "IQ": "MiddleEast",
    "YE": "MiddleEast", "PS": "MiddleEast", "LY": "MiddleEast",
    "DZ": "MiddleEast", "MA": "MiddleEast", "TN": "MiddleEast",
    "SD": "MiddleEast", "SO": "MiddleEast", "MR": "MiddleEast",
    "AU": "EastAsia", "NZ": "EastAsia",
    "FJ": "EastAsia", "PG": "EastAsia", "WS": "EastAsia",
    "TO": "EastAsia", "VU": "EastAsia", "FM": "EastAsia",
    "ZA": "SouthAsia", "NG": "SouthAsia", "KE": "SouthAsia",
    "ET": "SouthAsia", "TZ": "SouthAsia", "GH": "SouthAsia",
    "UG": "SouthAsia", "ZM": "SouthAsia", "ZW": "SouthAsia",
    "CA": "US", "MX": "US", "BM": "US",
    "BR": "US", "AR": "US", "CL": "US", "CO": "US", "PE": "US",
    "VE": "US", "EC": "US", "??": "Unknown", "ZZ": "Unknown",
}

DOMAIN_REGION_RULES = {
    "reuters.com": "Global", "apnews.com": "Global", "afp.com": "Global",
    "cnn.com": "US", "foxnews.com": "US", "nytimes.com": "US",
    "washingtonpost.com": "US", "wsj.com": "US", "usatoday.com": "US",
    "nbcnews.com": "US", "abcnews.go.com": "US", "cbsnews.com": "US",
    "npr.org": "US", "bloomberg.com": "US", "politico.com": "US",
    "thehill.com": "US", "time.com": "US", "newsweek.com": "US",
    "latimes.com": "US", "chicagotribune.com": "US", "nypost.com": "US",
    "axios.com": "US", "voanews.com": "US", "foreignpolicy.com": "US",
    "bbc.com": "Europe", "bbc.co.uk": "Europe", "theguardian.com": "Europe",
    "independent.co.uk": "Europe", "telegraph.co.uk": "Europe",
    "dailymail.co.uk": "Europe", "ft.com": "Europe", "dw.com": "Europe",
    "france24.com": "Europe", "euronews.com": "Europe", "lemonde.fr": "Europe",
    "spiegel.de": "Europe", "politico.eu": "Europe", "sky.com": "Europe",
    "skynews.com": "Europe", "rte.ie": "Europe", "irishtimes.com": "Europe",
    "ansa.it": "Europe", "elpais.com": "Europe", "thetimes.com": "Europe",
    "theguardian.com": "Europe", "standard.co.uk": "Europe",
    "express.co.uk": "Europe", "mirror.co.uk": "Europe",
    "aljazeera.com": "MiddleEast", "arabnews.com": "MiddleEast",
    "thenationalnews.com": "MiddleEast", "dailysabah.com": "MiddleEast",
    "trtworld.com": "MiddleEast", "gulfnews.com": "MiddleEast",
    "khaleejtimes.com": "MiddleEast",
    "timesofisrael.com": "Israel", "jpost.com": "Israel", "haaretz.com": "Israel",
    "ynetnews.com": "Israel", "israelnationalnews.com": "Israel",
    "tehrantimes.com": "Iran", "presstv.ir": "Iran",
    "indiatimes.com": "SouthAsia", "hindustantimes.com": "SouthAsia",
    "thehindu.com": "SouthAsia", "indianexpress.com": "SouthAsia",
    "ndtv.com": "SouthAsia", "firstpost.com": "SouthAsia", "news18.com": "SouthAsia",
    "dawn.com": "SouthAsia", "tribune.com.pk": "SouthAsia",
    "tass.com": "Russia", "rt.com": "Russia", "sputniknews.com": "Russia",
    "sputnikglobe.com": "Russia", "interfax.com": "Russia",
    "chinadaily.com.cn": "China", "globaltimes.cn": "China",
    "xinhuanet.com": "China", "cgtn.com": "China", "people.com.cn": "China",
    "scmp.com": "EastAsia", "japantimes.co.jp": "EastAsia",
    "asahi.com": "EastAsia", "koreaherald.com": "EastAsia",
    "koreatimes.co.kr": "EastAsia", "straitstimes.com": "EastAsia",
}

BAD_DOMAIN_KEYWORDS = [
    "yahoo.", "aol.", "msn.", "bing.", "google.", "apple.news",
    "flipboard.", "newsbreak.", "ground.news",
    "prnewswire.", "globenewswire.", "businesswire.", "accesswire.",
    "einpresswire.", "newsfilecorp.", "openpr.", "einnews.", "pr-inside.com",
    "marketscreener.", "streetinsider.", "finanznachrichten.", "tmcnet.",
    "seekingalpha.", "benzinga.", "zacks.", "morningstar.", "marketwatch.",
    "investing.com", "nasdaq.com", "fool.com", "tickerreport.com",
    "iheart.", "radio.", "podcast", "youtube.", "tiktok.",
    "facebook.", "twitter.", "x.com", "instagram.", "reddit.",
    "bignewsnetwork.", "middleeaststar.", "arabherald.", "menafn.",
    "russiaherald.com", "heraldglobe.com", "europesun.com",
    "miragenews.com", "onenewspage.com", "hngn.com", "digitaljournal.com",
    "naturalnews.com", "infowars.com",
]

BAD_URL_PATTERNS = [
    r"/video/", r"/videos/", r"/podcast", r"/live/",
    r"/photos/", r"/gallery/", r"/slideshow/",
    r"/press-release", r"/press_releases", r"/sponsored", r"/advertorial",
    r"/tag/", r"/author/",
]


def normalize_domain(x):
    if pd.isna(x): return ""
    x = str(x).strip().lower()
    if x.startswith("http"):
        try: x = urlparse(x).netloc.lower()
        except Exception: pass
    x = x.replace("www.", "").split("/")[0].split(":")[0]
    return x

def domain_from_url(url):
    try: return urlparse(str(url)).netloc.lower().replace("www.", "").split(":")[0]
    except Exception: return ""

def is_bad_domain(domain):
    return any(k in str(domain).lower() for k in BAD_DOMAIN_KEYWORDS)

def is_bad_url(url):
    return any(re.search(p, str(url).lower()) for p in BAD_URL_PATTERNS)

def extract_tld(domain):
    parts = domain.rsplit(".", 1)
    return parts[1].lower() if len(parts) == 2 else ""

def country_code_to_region(code):
    if not code or pd.isna(code): return "Unknown"
    return COUNTRY_CODE_TO_REGION.get(str(code).strip().upper(), "Unknown")

def load_domain_country_map(path):
    dm = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = normalize_domain(row.get("domain", ""))
            if d:
                dm[d] = (row.get("country_code", "").strip(), row.get("country_name", "").strip())
    print(f"[Domain country map] Loaded {len(dm)} entries")
    return dm

def determine_region(domain_norm, url_country_code, domain_country_map):
    tld = extract_tld(domain_norm)
    if domain_norm in DOMAIN_REGION_RULES:
        return DOMAIN_REGION_RULES[domain_norm]
    if tld and tld not in GENERIC_TLDS and tld in TLD_TO_REGION:
        return TLD_TO_REGION[tld]
    if tld and tld in GENERIC_TLDS:
        return "US"
    if domain_norm and domain_norm in domain_country_map:
        cc, _ = domain_country_map[domain_norm]
        region = country_code_to_region(cc)
        if region != "Unknown": return region
    cc = str(url_country_code).strip()
    if cc and cc not in ("", "nan", "None", "??", "ZZ"):
        region = country_code_to_region(cc)
        if region != "Unknown": return region
    # suffix fallback
    if tld in TLD_TO_REGION: return TLD_TO_REGION[tld]
    for key, region in DOMAIN_REGION_RULES.items():
        if domain_norm == key or domain_norm.endswith("." + key) or key in domain_norm:
            return region
    return "Unknown"


def load_and_clean(input_path, domain_country_map):
    print("[Load]", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    print("Raw rows:", len(df))
    if "url" not in df.columns: raise ValueError("missing url")
    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.startswith("http", na=False)].copy()
    if "domain" not in df.columns: df["domain"] = ""
    df["domain_norm"] = df["domain"].apply(normalize_domain)
    missing = df["domain_norm"].eq("")
    df.loc[missing, "domain_norm"] = df.loc[missing, "url"].apply(domain_from_url)
    df = df[~df["domain_norm"].apply(is_bad_domain)].copy()
    df = df[~df["url"].apply(is_bad_url)].copy()
    df = df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)
    if "url_country_code" not in df.columns: df["url_country_code"] = ""
    if "url_country_name" not in df.columns: df["url_country_name"] = ""

    # fill missing country_code from domain map
    def fill_cc(row):
        cc = str(row.get("url_country_code", "")).strip()
        if not cc or cc in ("", "nan", "None", "??", "ZZ"):
            dn = row.get("domain_norm", "")
            if dn and dn in domain_country_map:
                return pd.Series([domain_country_map[dn][0], domain_country_map[dn][1]])
        return pd.Series([row.get("url_country_code", ""), row.get("url_country_name", "")])

    missing_cc = df["url_country_code"].isin(["", "nan", "None", "??", "ZZ"]).sum()
    if missing_cc > 0:
        df[["url_country_code", "url_country_name"]] = df.apply(fill_cc, axis=1)

    print("Assigning regions...")
    df["country_group_final"] = df.apply(
        lambda r: determine_region(r["domain_norm"], r.get("url_country_code", ""), domain_country_map), axis=1)
    print("After clean:", len(df))
    print(df["country_group_final"].value_counts())
    return df


def keep_target_regions(df):
    kept = []
    for event_id, sub in df.groupby("event_id"):
        targets = EVENT_TARGET_REGIONS.get(event_id)
        if targets is None:
            kept.append(sub)
            continue
        before = len(sub)
        sub = sub[sub["country_group_final"].isin(targets)].copy()
        print(f"[Target] {event_id}: {before} -> {len(sub)}")
        kept.append(sub)
    return pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()


def cap_domain(df, max_per=80, seed=42):
    parts = []
    for _, sub in df.groupby(["event_id", "country_group_final", "domain_norm"]):
        if len(sub) > max_per:
            sub = sub.sample(max_per, random_state=seed)
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    print("After domain cap:", len(out))
    return out


def sample_event_region(df, target=600, min_rows=80, seed=42):
    samples, low = [], []
    for (eid, region), sub in df.groupby(["event_id", "country_group_final"]):
        n = len(sub)
        if n < min_rows:
            low.append({"event_id": eid, "country_group_final": region, "available_rows": n})
            take = n
        else:
            take = min(target, n)
        sampled = sub.sample(take, random_state=seed) if n > take else sub.copy()
        samples.append(sampled)
    out = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame()
    print("Sample rows:", len(out))
    return out, pd.DataFrame(low)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--domain_country", default=DEFAULT_DOMAIN_COUNTRY)
    parser.add_argument("--out_dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_PER_EVENT_REGION)
    parser.add_argument("--max_domain", type=int, default=DEFAULT_MAX_PER_DOMAIN_EVENT_REGION)
    parser.add_argument("--min_rows", type=int, default=DEFAULT_MIN_REGION_ROWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dm = load_domain_country_map(args.domain_country)
    df = load_and_clean(args.input, dm)

    known = df[~df["country_group_final"].eq("Unknown")]
    unknown = df[df["country_group_final"].eq("Unknown")]
    unknown.to_csv(out_dir / "unknown_for_llm.csv", index=False, encoding="utf-8-sig")
    print(f"Known: {len(known)}, Unknown: {len(unknown)}")

    target_df = keep_target_regions(known)
    target_df = cap_domain(target_df, max_per=args.max_domain, seed=args.seed)
    sample, low_df = sample_event_region(target_df, target=args.target, min_rows=args.min_rows, seed=args.seed)

    crawl_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "country_group_final", "domain_norm", "url",
        "url_country_code", "url_country_name",
        "themes", "v2_themes", "locations", "v2_locations",
        "persons", "v2_persons", "organizations", "v2_organizations",
        "all_names", "v2_tone", "actor_hits", "event_hits", "total_hits"
    ]
    sample = sample[[c for c in crawl_cols if c in sample.columns]].copy()
    sample = sample.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    out_path = out_dir / "crawl_sample.csv"
    sample.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {out_path}  rows={len(sample)}")
    print(sample["event_id"].value_counts())
    print(sample["country_group_final"].value_counts())

    low_df.to_csv(out_dir / "low_resource.csv", index=False, encoding="utf-8-sig")
    print("Done.")


if __name__ == "__main__":
    main()

import os
import glob
import hashlib
from urllib.parse import urlparse

import pandas as pd


# =========================
# 1. 路径配置
# =========================
GKG_DIR = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/gkg_csv"
OUTPUT_PATH = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/article_pool_raw.csv"


# =========================
# 2. GKG 2.1 常用字段索引
# 说明：
# GKG 是 tab 分隔，无表头
# 我们这里只取常用字段，避免一次性读全太重
# =========================
GKG_COLUMNS = {
    0: "gkgrecordid",
    1: "date",
    3: "themes",
    4: "locations",
    5: "persons",
    6: "organizations",
    7: "tone",
    8: "enhanced_themes",
    9: "enhanced_locations",
    10: "enhanced_persons",
    11: "enhanced_organizations",
    23: "document_identifier",  # URL
}

USECOLS = list(GKG_COLUMNS.keys())


# =========================
# 3. 域名到国家组映射
# 可继续补充
# =========================
DOMAIN_COUNTRY_MAP = {
    # US
    "cnn.com": "US",
    "nytimes.com": "US",
    "washingtonpost.com": "US",
    "apnews.com": "US",
    "foxnews.com": "US",
    "wsj.com": "US",
    "npr.org": "US",
    "abcnews.go.com": "US",
    "cbsnews.com": "US",
    "nbcnews.com": "US",
    "politico.com": "US",
    "axios.com": "US",

    # Israel
    "jpost.com": "Israel",
    "timesofisrael.com": "Israel",
    "haaretz.com": "Israel",
    "ynetnews.com": "Israel",
    "israelhayom.com": "Israel",
    "i24news.tv": "Israel",

    # Iran
    "tehrantimes.com": "Iran",
    "irna.ir": "Iran",
    "presstv.ir": "Iran",
    "mehrnews.com": "Iran",
    "tasnimnews.com": "Iran",
    "farsnews.ir": "Iran",

    # Third-party / regional reference
    "aljazeera.com": "ThirdParty",
    "bbc.com": "ThirdParty",
    "reuters.com": "ThirdParty",
    "theguardian.com": "ThirdParty",
    "indianexpress.com": "ThirdParty",
    "timesofindia.indiatimes.com": "ThirdParty",
    "hindustantimes.com": "ThirdParty",
    "france24.com": "ThirdParty",
    "dw.com": "ThirdParty",
}


# =========================
# 4. 关键词配置
# 第一轮先宽一点，后面再收紧
# =========================
KEYWORDS = [
    "IRAN",
    "ISRAEL",
    "UNITED_STATES",
    "U.S.",
    "US",
    "IRGC",
    "IDF",
    "TEHRAN",
    "JERUSALEM",
    "TEL_AVIV",
    "WASHINGTON",
]

# 更偏“行动/冲突”的词，帮助后续过滤
ACTION_KEYWORDS = [
    "MISSILE",
    "STRIKE",
    "ATTACK",
    "RETALIATION",
    "MILITARY",
    "AIRSTRIKE",
    "DRONE",
    "NUCLEAR",
    "THREAT",
    "CEASEFIRE",
]


def stable_article_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8", errors="ignore")).hexdigest()


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def map_country_group(domain: str) -> str:
    # 先精确匹配
    if domain in DOMAIN_COUNTRY_MAP:
        return DOMAIN_COUNTRY_MAP[domain]

    # 再做后缀包含匹配
    for k, v in DOMAIN_COUNTRY_MAP.items():
        if domain.endswith(k):
            return v

    return "Unknown"


def is_relevant_row(row: pd.Series) -> bool:
    """
    第一轮相关性过滤：
    只要 themes / persons / organizations / locations / url 任一字段里
    出现核心关键词即可保留。
    """
    texts = [
        str(row.get("themes", "")),
        str(row.get("enhanced_themes", "")),
        str(row.get("locations", "")),
        str(row.get("enhanced_locations", "")),
        str(row.get("persons", "")),
        str(row.get("enhanced_persons", "")),
        str(row.get("organizations", "")),
        str(row.get("enhanced_organizations", "")),
        str(row.get("document_identifier", "")),
    ]
    merged = " || ".join(texts).upper()

    has_core = any(k.upper() in merged for k in KEYWORDS)
    has_action = any(k.upper() in merged for k in ACTION_KEYWORDS)

    # 第一轮建议：核心关键词必须有；action 关键词有则额外打标签
    return has_core


def detect_action_relevance(row: pd.Series) -> int:
    texts = [
        str(row.get("themes", "")),
        str(row.get("enhanced_themes", "")),
        str(row.get("document_identifier", "")),
    ]
    merged = " || ".join(texts).upper()
    return int(any(k.upper() in merged for k in ACTION_KEYWORDS))


def parse_tone(raw_tone: str):
    """
    GKG tone 字段通常是逗号分隔的一串数值
    这里先保留原始值，并尝试抽第一个 overall tone
    """
    if not isinstance(raw_tone, str):
        return None
    parts = raw_tone.split(",")
    try:
        return float(parts[0])
    except Exception:
        return None


def read_one_gkg_file(path: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        usecols=USECOLS,
        names=[GKG_COLUMNS[c] for c in USECOLS],
        dtype=str,
        low_memory=False,
        on_bad_lines="skip",
    )
    df["source_file"] = os.path.basename(path)
    return df


def main():
    files = sorted(glob.glob(os.path.join(GKG_DIR, "*.gkg.csv")))
    print(f"[INFO] Found {len(files)} GKG files.")

    all_parts = []

    for i, path in enumerate(files, 1):
        print(f"[INFO] Reading {i}/{len(files)}: {os.path.basename(path)}")
        try:
            df = read_one_gkg_file(path)
        except Exception as e:
            print(f"[WARN] Failed reading {path}: {e}")
            continue

        # 相关性过滤
        mask = df.apply(is_relevant_row, axis=1)
        df = df[mask].copy()

        if df.empty:
            continue

        # URL / domain / country_group
        df["url"] = df["document_identifier"].fillna("")
        df["domain"] = df["url"].apply(get_domain)
        df["country_group"] = df["domain"].apply(map_country_group)

        # article_id
        df["article_id"] = df["url"].apply(stable_article_id)

        # tone
        df["overall_tone"] = df["tone"].apply(parse_tone)

        # action relevance
        df["action_relevance"] = df.apply(detect_action_relevance, axis=1)

        all_parts.append(df)

    if not all_parts:
        print("[ERROR] No relevant rows found.")
        return

    result = pd.concat(all_parts, ignore_index=True)

    # 去重：同一个 URL 只保留一条
    result = result.drop_duplicates(subset=["url"]).copy()

    # 调整列顺序
    ordered_cols = [
        "article_id",
        "date",
        "country_group",
        "domain",
        "url",
        "themes",
        "enhanced_themes",
        "locations",
        "enhanced_locations",
        "persons",
        "enhanced_persons",
        "organizations",
        "enhanced_organizations",
        "tone",
        "overall_tone",
        "action_relevance",
        "source_file",
    ]
    existing_cols = [c for c in ordered_cols if c in result.columns]
    result = result[existing_cols]

    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"[DONE] Saved: {OUTPUT_PATH}")
    print(f"[INFO] Total unique relevant articles: {len(result)}")
    print(result["country_group"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
# import pandas as pd

# file_path = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_raw.csv"

# # 读取文件（大文件建议加 low_memory=False）
# # df = pd.read_csv(file_path, low_memory=False)
# df = pd.read_csv(file_path, nrows=3)

# # 输出列名（首行）
# print("=== Columns ===")
# print(df.columns.tolist())

# # 输出前3行数据
# print("\n=== First 3 rows ===")
# print(df.head(3))
# import pandas as pd

# file_path = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_raw.csv"
# df = pd.read_csv(file_path, low_memory=False)

# print(df.iloc[0].to_dict())


import pandas as pd
from urllib.parse import urlparse

INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_raw.csv"
OUTPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_fixed.csv"

DOMAIN_COUNTRY_MAP = {
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

    "jpost.com": "Israel",
    "timesofisrael.com": "Israel",
    "haaretz.com": "Israel",
    "ynetnews.com": "Israel",
    "israelhayom.com": "Israel",
    "i24news.tv": "Israel",

    "tehrantimes.com": "Iran",
    "irna.ir": "Iran",
    "presstv.ir": "Iran",
    "mehrnews.com": "Iran",
    "tasnimnews.com": "Iran",
    "farsnews.ir": "Iran",

    "aljazeera.com": "ThirdParty",
    "bbc.com": "ThirdParty",
    "reuters.com": "ThirdParty",
    "theguardian.com": "ThirdParty",
    "indianexpress.com": "ThirdParty",
    "timesofindia.indiatimes.com": "ThirdParty",
    "hindustantimes.com": "ThirdParty",
    "france24.com": "ThirdParty",
    "dw.com": "ThirdParty",
    "news18.com": "ThirdParty",
    "indiatimes.com": "ThirdParty",
}

def get_domain(url: str) -> str:
    try:
        return urlparse(str(url)).netloc.lower()
    except Exception:
        return ""

def map_country_group(domain: str) -> str:
    if domain in DOMAIN_COUNTRY_MAP:
        return DOMAIN_COUNTRY_MAP[domain]
    for k, v in DOMAIN_COUNTRY_MAP.items():
        if domain.endswith(k):
            return v
    return "Unknown"

df = pd.read_csv(INPUT, low_memory=False)

# 按你这份 CSV 的实际错位情况重建字段
fixed = pd.DataFrame({
    "article_id": df["article_id"],
    "date": df["date"],
    "raw_names": df["url"],                    # 原 url 列其实是 names/counts
    "domain": df["themes"],                    # 原 themes 列其实是 domain
    "theme_string": df["enhanced_themes"],     # 原 enhanced_themes 才是主题串
    "url": df["locations"],                    # 原 locations 才是真正 URL
    "location_string": df["enhanced_locations"],
    "event_like_string": df["persons"],
    "enhanced_location_string": df["enhanced_persons"],
    "event_like_string_2": df["organizations"],
    "clean_theme_list": df["tone"],            # 原 tone 是清洗后的主题列表
    "action_relevance": df["action_relevance"],
    "source_file": df["source_file"],
})

fixed["url"] = fixed["url"].fillna("").astype(str)
fixed["domain"] = fixed["domain"].fillna("").astype(str).str.lower()

# 只保留正常 URL
fixed = fixed[fixed["url"].str.startswith("http")].copy()

# 若 domain 为空，则从 url 反推
mask_empty_domain = fixed["domain"].eq("")
fixed.loc[mask_empty_domain, "domain"] = fixed.loc[mask_empty_domain, "url"].apply(get_domain)

fixed["country_group"] = fixed["domain"].apply(map_country_group)

fixed = fixed.drop_duplicates(subset=["url"]).copy()

cols = [
    "article_id", "date", "country_group", "domain", "url",
    "theme_string", "clean_theme_list", "location_string",
    "raw_names", "event_like_string", "enhanced_location_string",
    "event_like_string_2", "action_relevance", "source_file"
]
fixed = fixed[cols]

fixed.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
print("saved:", OUTPUT)
print("rows:", len(fixed))
print(fixed.head(3).to_dict(orient="records"))
print(fixed["country_group"].value_counts(dropna=False))

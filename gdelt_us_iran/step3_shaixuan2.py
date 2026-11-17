import re
import pandas as pd

INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_fixed.csv"
OUTPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/stage_filtered_expanded.csv"

df = pd.read_csv(INPUT, low_memory=False)

print("Raw:", len(df))
print("Columns:", list(df.columns))

# =========================
# 基础清洗
# =========================
for col in [
    "theme_string",
    "clean_theme_list",
    "location_string",
    "title",
    "url",
    "domain",
    "date",
]:
    if col not in df.columns:
        df[col] = ""
    df[col] = df[col].fillna("").astype(str)

# 日期转为可排序格式
df["date"] = pd.to_datetime(df["date"], errors="coerce")

# 合并用于匹配的文本
df["match_text"] = (
    df["theme_string"] + " " +
    df["clean_theme_list"] + " " +
    df["location_string"] + " " +
    df["title"]
).str.upper()

# =========================
# Stage 1: 事件过滤（方案A）
# =========================
ACTOR_TERMS = [
    "IRAN", "IRANIAN",
    "ISRAEL", "ISRAELI",
    "UNITED STATES", "U.S.", "US ", "USA", "AMERICA", "AMERICAN",
    "TEHRAN", "TEL AVIV", "WASHINGTON",
    "IDF", "IRGC", "PENTAGON", "WHITE HOUSE"
]

CONFLICT_TERMS = [
    "MISSILE", "MISSILES",
    "ATTACK", "ATTACKS",
    "STRIKE", "STRIKES",
    "MILITARY",
    "KILL", "KILLED",
    "WAR", "CONFLICT",
    "BOMB", "BOMBING",
    "DRONE", "DRONES",
    "ROCKET", "ROCKETS",
    "AIRSTRIKE", "AIRSTRIKES",
    "RETALIATION", "RETALIATE",
    "OFFENSIVE", "ESCALATION",
    "TROOPS", "FORCES",
    "NUCLEAR", "SANCTIONS",
    "HORMUZ", "STRAIT OF HORMUZ"
]

def count_hits(text, terms):
    text = str(text).upper()
    return sum(1 for t in terms if t in text)

df["actor_hits"] = df["match_text"].apply(lambda x: count_hits(x, ACTOR_TERMS))
df["conflict_hits"] = df["match_text"].apply(lambda x: count_hits(x, CONFLICT_TERMS))

mask_stage1 = (
    ((df["actor_hits"] >= 1) & (df["conflict_hits"] >= 1)) |
    (df["actor_hits"] >= 2)
)

df = df[mask_stage1].copy()
print("After stage1:", len(df))

# =========================
# Stage 2: 限制 domain（方案A）
# =========================
TOP_N_DOMAINS = 500
MAX_PER_DOMAIN = 12

domain_counts = df["domain"].value_counts()
top_domains = domain_counts.head(TOP_N_DOMAINS).index
df = df[df["domain"].isin(top_domains)].copy()

df = df.sort_values(["domain", "date"])
df = df.groupby("domain", group_keys=False).head(MAX_PER_DOMAIN).copy()

print("After stage2:", len(df))
print("Unique domains after stage2:", df["domain"].nunique())

# =========================
# Stage 3: 去重（修正版）
# =========================
def normalize_text(text):
    text = str(text).lower().strip()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text

# ---------- 1) URL去重：只对非空URL生效 ----------
df["url_norm"] = df["url"].apply(lambda x: x.strip().lower())

non_empty_url = df["url_norm"] != ""
df_url_nonempty = df[non_empty_url].drop_duplicates(subset=["url_norm"])
df_url_empty = df[~non_empty_url]

df = pd.concat([df_url_nonempty, df_url_empty], ignore_index=True)
print("After URL dedup:", len(df))

# ---------- 2) Title去重：只对非空title生效 ----------
df["title_norm"] = df["title"].apply(normalize_text)

# 认为长度太短的标题无效，不参与去重
valid_title = df["title_norm"].str.len() >= 15

df_title_valid = df[valid_title].drop_duplicates(subset=["title_norm"])
df_title_invalid = df[~valid_title]

df = pd.concat([df_title_valid, df_title_invalid], ignore_index=True)
print("After title dedup:", len(df))

# ---------- 3) 签名去重：只对有效签名生效 ----------
def build_sig(row):
    theme = normalize_text(row["theme_string"])[:200]
    title = normalize_text(row["title"])[:120]
    sig = (theme + " || " + title).strip()
    return sig

df["sig"] = df.apply(build_sig, axis=1)

# 至少要有一定长度才认为是有效签名
valid_sig = df["sig"].str.len() >= 30

df_sig_valid = df[valid_sig].drop_duplicates(subset=["sig"])
df_sig_invalid = df[~valid_sig]

df = pd.concat([df_sig_valid, df_sig_invalid], ignore_index=True)
print("After signature dedup:", len(df))

# =========================
# 可选清理
# =========================
df = df[df["domain"].str.len() > 0].copy()

# title 不再强制要求一定存在，只过滤特别离谱的情况
all_text_len = (
    df["theme_string"].astype(str).str.len() +
    df["clean_theme_list"].astype(str).str.len() +
    df["location_string"].astype(str).str.len() +
    df["title"].astype(str).str.len()
)
df = df[all_text_len >= 20].copy()

print("Final:", len(df))

# =========================
# 调试信息
# =========================
print("\nNon-empty URL rows:", (df["url"].str.strip() != "").sum())
print("Non-empty Title rows:", (df["title"].str.strip() != "").sum())

print("\nTop domains:")
print(df["domain"].value_counts().head(20))

if "country_group" in df.columns:
    print("\nCountry distribution:")
    print(df["country_group"].value_counts(dropna=False).head(20))

# =========================
# 保存
# =========================
df.to_csv(OUTPUT, index=False)
print("\nSaved:", OUTPUT)
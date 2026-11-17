import pandas as pd

# INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/stage_filtered.csv"
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/stage_filtered_expanded.csv"
OUTPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/event_A_candidates_expanded.csv"

df = pd.read_csv(INPUT, low_memory=False)

# ===== 关键词定义 =====
IRAN_TERMS = ["IRAN", "IRANIAN"]
ISRAEL_TERMS = ["ISRAEL", "ISRAELI"]

# 强事件词（优先）
STRONG_EVENT = [
    "CLUSTER MUNITIONS",
    "MISSILE",
    "AIRSTRIKE",
    "DRONE",
    "ROCKET",
    "BOMB"
]

# 一般事件词
WEAK_EVENT = [
    "ATTACK",
    "STRIKE",
    "RETALIATION",
    "KILL",
    "MILITARY"
]

# ===== 构造文本 =====
def build_text(row):
    return " ".join([
        str(row.get("url", "")),
        str(row.get("theme_string", "")),
        str(row.get("clean_theme_list", "")),
        str(row.get("location_string", "")),
    ]).upper()

df["text"] = df.apply(build_text, axis=1)

# ===== 计分函数 =====
def count_terms(text, terms):
    return sum(1 for t in terms if t in text)

df["iran_hit"] = df["text"].apply(lambda x: count_terms(x, IRAN_TERMS))
df["israel_hit"] = df["text"].apply(lambda x: count_terms(x, ISRAEL_TERMS))
df["strong_event"] = df["text"].apply(lambda x: count_terms(x, STRONG_EVENT))
df["weak_event"] = df["text"].apply(lambda x: count_terms(x, WEAK_EVENT))

# ===== 核心过滤 =====
df = df[
    (df["iran_hit"] >= 1) &
    (df["israel_hit"] >= 1) &
    (
        (df["strong_event"] >= 1) |
        (df["weak_event"] >= 2)
    )
]

print("After event filtering:", len(df))

# ===== 评分（核心）=====
df["score"] = (
    df["strong_event"] * 3 +
    df["weak_event"] * 1 +
    df["iran_hit"] * 2 +
    df["israel_hit"] * 2
)

# ===== 去重（避免同一叙事刷屏）=====
df = df.sort_values("score", ascending=False)

def build_sig(row):
    return str(row["theme_string"])[:120]

df["sig"] = df.apply(build_sig, axis=1)
df = df.drop_duplicates(subset=["sig"])

# ===== 控制规模（关键）=====
df = df.groupby("domain").head(3)

# ===== 只取前 N 条 =====
# df = df.head(120)

df.to_csv(OUTPUT, index=False)

print("Saved:", OUTPUT)
print("Final size:", len(df))

# 看一下分布
print(df["country_group"].value_counts())

# 看前10条
print(df[["domain", "url", "score"]].head(10))
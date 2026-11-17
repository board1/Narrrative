import pandas as pd

INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_fixed.csv"
OUTPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/stage_filtered.csv"

df = pd.read_csv(INPUT, low_memory=False)

# ===== Stage 1: 事件过滤 =====
ACTOR_TERMS = ["IRAN", "ISRAEL", "UNITED STATES", "U.S."]
CONFLICT_TERMS = ["MISSILE", "ATTACK", "STRIKE", "MILITARY", "KILL"]

def count_hits(text, terms):
    text = str(text).upper()
    return sum(1 for t in terms if t in text)

merged = (
    df["theme_string"].astype(str) + " " +
    df["clean_theme_list"].astype(str) + " " +
    df["location_string"].astype(str)
)

df["actor_hits"] = merged.apply(lambda x: count_hits(x, ACTOR_TERMS))
df["conflict_hits"] = merged.apply(lambda x: count_hits(x, CONFLICT_TERMS))

df = df[(df["actor_hits"] >= 2) & (df["conflict_hits"] >= 1)]

print("After stage1:", len(df))

# ===== Stage 2: 限制 domain =====
top_domains = df["domain"].value_counts().head(200).index
df = df[df["domain"].isin(top_domains)]

df = df.sort_values("date")
df = df.groupby("domain").head(5)

print("After stage2:", len(df))

# ===== Stage 3: 去重 =====
def build_sig(row):
    return str(row["theme_string"])[:150]

df["sig"] = df.apply(build_sig, axis=1)
df = df.drop_duplicates(subset=["sig"])

print("After stage3:", len(df))

df.to_csv(OUTPUT, index=False)
print("Saved:", OUTPUT)
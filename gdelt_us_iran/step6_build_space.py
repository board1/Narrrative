import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
from sklearn.feature_extraction.text import TfidfVectorizer

# ===== 路径 =====
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_clean.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_clusters.csv"
OUTPUT_FIG = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space.png"

# ===== 参数 =====
N_CLUSTERS = 4   # 可以调 3~6
TOP_KWORDS = 8

# ===== Step 1: 读取数据 =====
df = pd.read_csv(INPUT)

df = df[
    (df["text"].notna()) &
    (df["text"].str.len() > 200)
].copy()

print("Loaded:", len(df))

texts = df["text"].tolist()

# ===== Step 2: Embedding =====
print("\n[Embedding]")
model = SentenceTransformer("/data_ssd2/zbh/LLM/all-MiniLM-L6-v2")
embeddings = model.encode(texts, show_progress_bar=True)

# ===== Step 3: Clustering =====
print("\n[Clustering]")
kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42)
df["cluster"] = kmeans.fit_predict(embeddings)

# ===== Step 4: 降维（用于画图）=====
print("\n[TSNE]")
tsne = TSNE(n_components=2, random_state=42, perplexity=10)
coords = tsne.fit_transform(embeddings)

df["x"] = coords[:, 0]
df["y"] = coords[:, 1]

# ===== Step 5: 可视化 =====
print("\n[Plot]")
plt.figure(figsize=(8, 6))

for c in sorted(df["cluster"].unique()):
    sub = df[df["cluster"] == c]
    plt.scatter(sub["x"], sub["y"], label=f"Cluster {c}")

plt.legend()
plt.title("Narrative Space")
plt.xlabel("Dim 1")
plt.ylabel("Dim 2")
plt.tight_layout()
plt.savefig(OUTPUT_FIG, dpi=300)
print("Saved figure:", OUTPUT_FIG)

# ===== Step 6: 提取关键词（每个 cluster）=====
print("\n[Keywords]")

vectorizer = TfidfVectorizer(
    max_features=5000,
    stop_words="english"
)

X_tfidf = vectorizer.fit_transform(df["text"])
terms = np.array(vectorizer.get_feature_names_out())

cluster_keywords = {}

for c in sorted(df["cluster"].unique()):
    idx = np.where(df["cluster"] == c)[0]
    tfidf_mean = X_tfidf[idx].mean(axis=0).A1

    top_idx = tfidf_mean.argsort()[-TOP_KWORDS:][::-1]
    keywords = terms[top_idx]

    cluster_keywords[c] = keywords.tolist()

    print(f"\n=== Cluster {c} ===")
    print("Keywords:", keywords)

# ===== Step 7: 输出示例 =====
print("\n[Examples]")

for c in sorted(df["cluster"].unique()):
    print(f"\n=== Cluster {c} Examples ===")
    sub = df[df["cluster"] == c].head(3)
    for _, row in sub.iterrows():
        print("-", row.get("domain", ""), row.get("url", ""))

# ===== Step 8: 保存结果 =====
df.to_csv(OUTPUT_CSV, index=False)
print("\nSaved:", OUTPUT_CSV)
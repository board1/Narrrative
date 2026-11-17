import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

# 如果没装：pip install umap-learn
from umap import UMAP


# =========================
# 路径配置
# =========================
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_clean_expanded.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_clusters_umap_expanded.csv"
OUTPUT_FIG = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space_umap_expanded.png"
OUTPUT_CROSSTAB = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/country_cluster_distribution_expanded.csv"

# =========================
# 参数
# =========================
N_CLUSTERS = 4
TOP_KWORDS = 10
MIN_WORDS = 100


def main():
    # -------------------------
    # 1. 读取和清洗
    # -------------------------
    df = pd.read_csv(INPUT, low_memory=False)

    df = df[
        (df["text"].notna()) &
        (df["success"] == True) &
        (df["word_count"] > MIN_WORDS)
    ].copy()

    # 去重
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    print("Clean size:", len(df))

    texts = df["text"].astype(str).tolist()

    # -------------------------
    # 2. Embedding
    # -------------------------
    print("\n[Embedding]")
    model = SentenceTransformer("/data_ssd2/zbh/LLM/all-MiniLM-L6-v2")
    embeddings = model.encode(texts, show_progress_bar=True)

    # -------------------------
    # 3. 聚类
    # -------------------------
    print("\n[Clustering]")
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
    df["cluster"] = kmeans.fit_predict(embeddings)

    # -------------------------
    # 4. UMAP 降维
    # -------------------------
    print("\n[UMAP]")
    umap_model = UMAP(
        n_components=2,
        n_neighbors=10,
        min_dist=0.3,
        metric="cosine",
        random_state=42
    )
    coords = umap_model.fit_transform(embeddings)

    df["x"] = coords[:, 0]
    df["y"] = coords[:, 1]

    # -------------------------
    # 5. 画图
    # -------------------------
    print("\n[Plot]")
    plt.figure(figsize=(9, 7))

    for c in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == c]
        plt.scatter(sub["x"], sub["y"], label=f"Cluster {c}", s=60)

    plt.title("Narrative Space")
    plt.xlabel("Dim 1")
    plt.ylabel("Dim 2")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_FIG, dpi=300)
    print("Saved figure:", OUTPUT_FIG)

    # -------------------------
    # 6. 更好的关键词提取
    # -------------------------
    print("\n[Cluster Keywords]")
    vectorizer = TfidfVectorizer(
        max_features=8000,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2
    )
    X_tfidf = vectorizer.fit_transform(df["text"])
    terms = np.array(vectorizer.get_feature_names_out())

    cluster_keyword_map = {}

    for c in sorted(df["cluster"].unique()):
        idx = np.where(df["cluster"].values == c)[0]
        tfidf_mean = X_tfidf[idx].mean(axis=0).A1
        top_idx = tfidf_mean.argsort()[-TOP_KWORDS:][::-1]
        keywords = terms[top_idx].tolist()
        cluster_keyword_map[c] = keywords

        print(f"\n=== Cluster {c} ===")
        print("Keywords:", keywords)

    # -------------------------
    # 7. 示例输出
    # -------------------------
    print("\n[Cluster Examples]")
    for c in sorted(df["cluster"].unique()):
        print(f"\n=== Cluster {c} Examples ===")
        sub = df[df["cluster"] == c].head(3)
        for _, row in sub.iterrows():
            print("-", row.get("domain", ""), row.get("url", ""))

    # -------------------------
    # 8. country_group × cluster
    # -------------------------
    print("\n[Country x Cluster]")
    ctab = pd.crosstab(df["country_group"], df["cluster"])
    ctab_norm = pd.crosstab(df["country_group"], df["cluster"], normalize="index")

    print("\nCount table:")
    print(ctab)

    print("\nNormalized table:")
    print(ctab_norm.round(3))

    ctab_norm.to_csv(OUTPUT_CROSSTAB, encoding="utf-8-sig")
    print("Saved crosstab:", OUTPUT_CROSSTAB)

    # -------------------------
    # 9. 保存总表
    # -------------------------
    # 给每个 cluster 存一个可读标签字段
    df["cluster_keywords"] = df["cluster"].map(
        lambda c: " | ".join(cluster_keyword_map.get(c, []))
    )

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print("Saved data:", OUTPUT_CSV)


if __name__ == "__main__":
    main()
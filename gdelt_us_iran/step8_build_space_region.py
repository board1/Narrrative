import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from umap import UMAP


# =========================
# 路径配置
# =========================
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_region_inferred_expanded.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_clusters_region_expanded2.csv"
OUTPUT_FIG = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space_region_expanded2.png"
OUTPUT_CROSSTAB = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/region_cluster_distribution_expanded2.csv"

# =========================
# 参数
# =========================
N_CLUSTERS = 4
TOP_KWORDS = 12
MIN_WORDS = 100

CUSTOM_STOPWORDS = {
    "said", "iran", "israel", "iranian", "israeli",
    "trump", "new", "president", "wednesday"
}


def build_region_group_final(df: pd.DataFrame) -> pd.DataFrame:
    """
    如果文件里还没有 region_group_final，就自动生成。
    逻辑：
    - 已知 country_group 中 US / Israel / Iran / ThirdParty
    - Unknown 用 pred_region_group
    """
    if "region_group_final" in df.columns:
        df["region_group_final"] = df["region_group_final"].fillna("").astype(str).str.strip()
        return df

    df["region_group_final"] = ""

    if "country_group" in df.columns:
        def map_existing(x: str) -> str:
            x = str(x).strip()
            if x in {"US", "Israel", "Iran"}:
                return x
            if x == "ThirdParty":
                return "Global"
            return ""

        known_mask = df["country_group"].astype(str).isin(["US", "Israel", "Iran", "ThirdParty"])
        df.loc[known_mask, "region_group_final"] = df.loc[known_mask, "country_group"].apply(map_existing)

    if "pred_region_group" in df.columns and "country_group" in df.columns:
        unknown_mask = df["country_group"].astype(str).str.strip().eq("Unknown")
        df.loc[unknown_mask, "region_group_final"] = (
            df.loc[unknown_mask, "pred_region_group"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # 最后兜底
    df["region_group_final"] = df["region_group_final"].replace("", "Unknown")
    return df


def main():
    # -------------------------
    # 1. 读取和清洗
    # -------------------------
    df = pd.read_csv(INPUT, low_memory=False)

    df = build_region_group_final(df)

    df = df[
        (df["text"].notna()) &
        (df["success"] == True) &
        (df["word_count"] > MIN_WORDS)
    ].copy()

    # 去重
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    print("Clean size:", len(df))
    print("\n[region_group_final distribution]")
    print(df["region_group_final"].value_counts(dropna=False))

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
    # 5. 画图（按 cluster）
    # -------------------------
    print("\n[Plot - Cluster]")
    plt.figure(figsize=(9, 7))
    for c in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == c]
        plt.scatter(sub["x"], sub["y"], label=f"Cluster {c}", s=60)

    plt.title("Narrative Space by Cluster")
    plt.xlabel("Dim 1")
    plt.ylabel("Dim 2")
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_FIG, dpi=300)
    print("Saved figure:", OUTPUT_FIG)

    # -------------------------
    # 6. 提取 cluster 关键词
    # -------------------------
    print("\n[Cluster Keywords]")
    vectorizer = TfidfVectorizer(
        max_features=10000,
        stop_words="english",
        ngram_range=(1, 3),
        min_df=2
    )
    X_tfidf = vectorizer.fit_transform(df["text"])
    terms = np.array(vectorizer.get_feature_names_out())

    # 过滤自定义泛词
    mask = np.array([t not in CUSTOM_STOPWORDS for t in terms])
    terms_filtered = terms[mask]
    X_filtered = X_tfidf[:, mask]

    cluster_keyword_map = {}

    for c in sorted(df["cluster"].unique()):
        idx = np.where(df["cluster"].values == c)[0]
        tfidf_mean = X_filtered[idx].mean(axis=0).A1
        top_idx = tfidf_mean.argsort()[-TOP_KWORDS:][::-1]
        keywords = terms_filtered[top_idx].tolist()
        cluster_keyword_map[c] = keywords

        print(f"\n=== Cluster {c} ===")
        print("Keywords:", keywords)

    # -------------------------
    # 7. 输出每个 cluster 的示例
    # -------------------------
    print("\n[Cluster Examples]")
    for c in sorted(df["cluster"].unique()):
        print(f"\n=== Cluster {c} Examples ===")
        sub = df[df["cluster"] == c].head(3)
        for _, row in sub.iterrows():
            print("-", row.get("domain", ""), row.get("url", ""))

    # -------------------------
    # 8. region_group_final × cluster
    # -------------------------
    print("\n[Region x Cluster]")
    ctab = pd.crosstab(df["region_group_final"], df["cluster"])
    ctab_norm = pd.crosstab(df["region_group_final"], df["cluster"], normalize="index")

    print("\nCount table:")
    print(ctab)

    print("\nNormalized table:")
    print(ctab_norm.round(3))

    ctab_norm.to_csv(OUTPUT_CROSSTAB, encoding="utf-8-sig")
    print("Saved crosstab:", OUTPUT_CROSSTAB)

    # -------------------------
    # 9. 附加 cluster 关键词并保存
    # -------------------------
    df["cluster_keywords"] = df["cluster"].map(
        lambda c: " | ".join(cluster_keyword_map.get(c, []))
    )

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print("Saved data:", OUTPUT_CSV)

    # -------------------------
    # 10. 可选：再画一张按 region_group_final 上色的图
    # -------------------------
    region_fig = OUTPUT_FIG.replace(".png", "_by_region.png")
    print("\n[Plot - Region]")
    plt.figure(figsize=(9, 7))

    for region in sorted(df["region_group_final"].dropna().unique()):
        sub = df[df["region_group_final"] == region]
        plt.scatter(sub["x"], sub["y"], label=region, s=60)

    plt.title("Narrative Space by Region Group")
    plt.xlabel("Dim 1")
    plt.ylabel("Dim 2")
    plt.legend()
    plt.tight_layout()
    plt.savefig(region_fig, dpi=300)
    print("Saved figure:", region_fig)


if __name__ == "__main__":
    main()
# import pandas as pd
# import matplotlib.pyplot as plt
# import seaborn as sns
# import umap

# # ===== 读数据 =====
# df = pd.read_csv("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv")

# # ===== embedding列 =====
# embedding_cols = [c for c in df.columns if c.startswith("emb_")]
# X = df[embedding_cols].values

# # ===== 降维 =====
# reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, metric="cosine", random_state=42)
# coords = reducer.fit_transform(X)

# df["x"] = coords[:, 0]
# df["y"] = coords[:, 1]

# # ===== 画图 =====
# plt.figure(figsize=(8,6))
# sns.scatterplot(
#     data=df,
#     x="x", y="y",
#     hue="region_group_final",
#     palette="tab10",
#     s=10,
#     alpha=0.6
# )
# plt.title("Narrative Space (Colored by Region)")
# plt.legend(bbox_to_anchor=(1.05,1))
# plt.tight_layout()
# # plt.show()
# plt.savefig("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space.png")

# plt.figure(figsize=(8,6))

# for region in df["region_group_final"].unique():
#     subset = df[df["region_group_final"] == region]
#     sns.kdeplot(
#         x=subset["x"], y=subset["y"],
#         label=region,
#         fill=False,
#         alpha=0.7
#     )

# plt.title("Narrative Density by Region")
# plt.legend()
# # plt.show()
# plt.savefig("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_density.png")

# # ===== 计算centroid =====
# centroids = df.groupby("region_group_final")[["x","y"]].mean().reset_index()

# plt.figure(figsize=(8,6))

# # 背景点（淡一点）
# sns.scatterplot(
#     data=df,
#     x="x", y="y",
#     color="lightgray",
#     s=5,
#     alpha=0.3
# )

# # 画centroid
# sns.scatterplot(
#     data=centroids,
#     x="x", y="y",
#     hue="region_group_final",
#     palette="tab10",
#     s=200,
#     marker="X"
# )

# # 标注
# for _, row in centroids.iterrows():
#     plt.text(row["x"], row["y"], row["region_group_final"])

# plt.title("Narrative Space with Regional Centroids")
# plt.legend()
# # plt.show()
# plt.savefig("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space_centroids.png")



import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import umap

from sentence_transformers import SentenceTransformer

INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv"

OUT1 = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space_by_region.png"
OUT2 = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_space_region_centroids.png"
OUT3 = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/narrative_density_by_region.png"

MIN_WORDS = 100


def main():
    df = pd.read_csv(INPUT, low_memory=False)

    # 只保留可用样本
    df = df[
        (df["text"].notna()) &
        (df["success"] == True) &
        (df["word_count"] > MIN_WORDS)
    ].copy()

    # 去重
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    print("Clean size:", len(df))
    print("\nRegion distribution:")
    print(df["region_group_final"].value_counts(dropna=False))

    # 重新算 embedding
    texts = df["text"].astype(str).tolist()

    print("\n[Embedding]")
    model = SentenceTransformer("/data_ssd2/zbh/LLM/all-MiniLM-L6-v2")
    X = model.encode(texts, show_progress_bar=True)

    # UMAP
    print("\n[UMAP]")
    reducer = umap.UMAP(
        n_neighbors=10,
        min_dist=0.3,
        metric="cosine",
        random_state=42
    )
    coords = reducer.fit_transform(X)

    df["x"] = coords[:, 0]
    df["y"] = coords[:, 1]

    # =========================
    # 图1：按 region 上色的散点图
    # =========================
    plt.figure(figsize=(8, 6))
    sns.scatterplot(
        data=df,
        x="x", y="y",
        hue="region_group_final",
        palette="tab10",
        s=60,
        alpha=0.8
    )
    plt.title("Narrative Space Colored by Region")
    plt.tight_layout()
    plt.savefig(OUT1, dpi=300)
    print("Saved:", OUT1)
    plt.show()

    # =========================
    # 图2：centroid 图
    # =========================
    centroids = df.groupby("region_group_final")[["x", "y"]].mean().reset_index()

    plt.figure(figsize=(8, 6))

    # 背景点
    sns.scatterplot(
        data=df,
        x="x", y="y",
        color="lightgray",
        s=30,
        alpha=0.35,
        legend=False
    )

    # centroid
    sns.scatterplot(
        data=centroids,
        x="x", y="y",
        hue="region_group_final",
        palette="tab10",
        s=220,
        marker="X"
    )

    for _, row in centroids.iterrows():
        plt.text(row["x"] + 0.05, row["y"] + 0.05, row["region_group_final"], fontsize=10)

    plt.title("Narrative Space with Regional Centroids")
    plt.tight_layout()
    plt.savefig(OUT2, dpi=300)
    print("Saved:", OUT2)
    plt.show()

    # =========================
    # 图3：密度图
    # =========================
    plt.figure(figsize=(8, 6))

    for region in sorted(df["region_group_final"].dropna().unique()):
        sub = df[df["region_group_final"] == region]
        if len(sub) >= 3:
            sns.kdeplot(
                x=sub["x"], y=sub["y"],
                label=region,
                fill=False,
                alpha=0.8
            )

    plt.title("Narrative Density by Region")
    plt.tight_layout()
    plt.savefig(OUT3, dpi=300)
    print("Saved:", OUT3)
    plt.show()

    plt.figure(figsize=(8, 6))
    sns.scatterplot(
        data=df,
        x="x", y="y",
        hue="main_frame",
        palette="tab10",
        s=60,
        alpha=0.8
    )
    plt.title("Narrative Space Colored by Main Frame")
    plt.tight_layout()
    plt.show()
    plt.savefig('Narrative_Space_Colored_by_Main_Frame', dpi=300)
        # 如果你后面还想复用坐标，顺手存一份
    df.to_csv(
        "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed_with_xy.csv",
        index=False,
        encoding="utf-8-sig"
    )
    print("Saved coordinate CSV.")



if __name__ == "__main__":
    main()
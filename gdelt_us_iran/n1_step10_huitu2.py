import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import umap

from sentence_transformers import SentenceTransformer

# =========================
# 路径配置
# =========================
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv"

OUT_DENSITY = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_density_top3.png"
OUT_CENTROID = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_centroids.png"
OUT_HEATMAP = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_frame_heatmap.png"
OUT_WITH_XY = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed_with_xy.csv"

# =========================
# 参数
# =========================
MIN_WORDS = 100
TOP_REGIONS = ["US", "MiddleEast", "Europe"]


def main():
    sns.set_style("white")
    plt.rcParams["figure.dpi"] = 150

    # -------------------------
    # 1. 读数据
    # -------------------------
    df = pd.read_csv(INPUT, low_memory=False)

    df = df[
        (df["text"].notna()) &
        (df["success"] == True) &
        (df["word_count"] > MIN_WORDS)
    ].copy()

    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    print("Clean size:", len(df))
    print("\nRegion distribution:")
    print(df["region_group_final"].value_counts(dropna=False))

    # -------------------------
    # 2. 重新算 embedding
    # -------------------------
    texts = df["text"].astype(str).tolist()

    print("\n[Embedding]")
    model = SentenceTransformer("/data_ssd2/zbh/LLM/all-MiniLM-L6-v2")
    X = model.encode(texts, show_progress_bar=True)

    # -------------------------
    # 3. UMAP
    # -------------------------
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

    df.to_csv(OUT_WITH_XY, index=False, encoding="utf-8-sig")
    print("Saved with xy:", OUT_WITH_XY)

    # =========================
    # Figure A: Top-3 region density
    # =========================
    print("\n[Figure A] Density")
    df_top = df[df["region_group_final"].isin(TOP_REGIONS)].copy()

    plt.figure(figsize=(7.5, 6))

    # 背景散点
    # sns.scatterplot(
    #     data=df_top,
    #     x="x", y="y",
    #     color="lightgray",
    #     s=18,
    #     alpha=0.25,
    #     legend=False
    # )
    # sns.kdeplot(
    #     data=sub,
    #     x="x", y="y",
    #     fill=True,
    #     alpha=0.20,
    #     levels=3,
    #     thresh=0.05,
    #     label=region
    # )  

    # 单层填充密度
    for region in TOP_REGIONS:
        sub = df_top[df_top["region_group_final"] == region]
        if len(sub) >= 3:
            sns.kdeplot(
                data=sub,
                x="x", y="y",
                fill=True,
                alpha=0.20,
                levels=1,
                thresh=0.05,
                label=region
            )
    sns.kdeplot(
        data=sub,
        x="x", y="y",
        fill=True,
        alpha=0.20,
        levels=3,
        thresh=0.05,
        label=region
    )  
    plt.title("Narrative Density by Region")
    plt.xlabel("Dim 1")
    plt.ylabel("Dim 2")
    plt.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(OUT_DENSITY, dpi=300)
    print("Saved:", OUT_DENSITY)
    plt.close()

    # =========================
    # Figure B: Regional centroids
    # =========================
    print("\n[Figure B] Centroids")
    centroids = df.groupby("region_group_final")[["x", "y"]].mean().reset_index()

    plt.figure(figsize=(7.5, 6))

    # 全部背景点
    sns.scatterplot(
        data=df,
        x="x", y="y",
        color="lightgray",
        s=18,
        alpha=0.25,
        legend=False
    )

    # 重心
    sns.scatterplot(
        data=centroids,
        x="x", y="y",
        hue="region_group_final",
        s=220,
        marker="X"
    )

    for _, row in centroids.iterrows():
        plt.text(
            row["x"] + 0.05,
            row["y"] + 0.05,
            row["region_group_final"],
            fontsize=10
        )

    plt.title("Narrative Space with Regional Centroids")
    plt.xlabel("Dim 1")
    plt.ylabel("Dim 2")
    plt.legend(frameon=True, bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(OUT_CENTROID, dpi=300)
    print("Saved:", OUT_CENTROID)
    plt.close()

    # =========================
    # Figure C: region × frame heatmap
    # =========================
    print("\n[Figure C] Heatmap")
    ctab = pd.crosstab(
        df["region_group_final"],
        df["main_frame"],
        normalize="index"
    )

    # 固定列顺序，便于比较
    desired_cols = [
        "military_operation",
        "ideological_regime",
        "energy_economic",
        "regional_spillover",
        "diplomatic_strategic",
        "humanitarian_victimhood",
        "mixed"
    ]
    existing_cols = [c for c in desired_cols if c in ctab.columns]
    ctab = ctab[existing_cols]

    plt.figure(figsize=(9, 4.8))
    sns.heatmap(
        ctab,
        annot=True,
        fmt=".2f",
        cmap="Blues",
        cbar=True
    )
    plt.title("Regional Distribution over Narrative Frames")
    plt.xlabel("Main Frame")
    plt.ylabel("Region Group")
    plt.tight_layout()
    plt.savefig(OUT_HEATMAP, dpi=300)
    print("Saved:", OUT_HEATMAP)
    plt.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
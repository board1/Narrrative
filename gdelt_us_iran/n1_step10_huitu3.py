import os
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import umap.umap_ as umap

from sentence_transformers import SentenceTransformer

# =========================
# 路径配置
# =========================
INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv"

OUT_DENSITY = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_density_top3.png"
OUT_CENTROID = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_centroids.png"
OUT_HEATMAP = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/fig_region_frame_heatmap.png"
OUT_WITH_XY = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed_with_xy.csv"

# 本地模型路径
MODEL_PATH = "/data_ssd2/zbh/LLM/all-MiniLM-L6-v2"

# =========================
# 参数
# =========================
MIN_WORDS = 100
TOP_REGIONS = ["US", "MiddleEast", "Europe"]


def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def normalize_success_col(series: pd.Series) -> pd.Series:
    """
    兼容 True / False / 'True' / 'FALSE' / 1 / 0 等情况
    """
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y"})
    )


def validate_columns(df: pd.DataFrame, required_cols):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"缺少必要列: {missing}")


def main():
    warnings.filterwarnings("ignore", category=UserWarning)

    sns.set_style("white")
    plt.rcParams["figure.dpi"] = 150

    # -------------------------
    # 1. 读数据
    # -------------------------
    print("[Load]")
    df = pd.read_csv(INPUT, low_memory=False)

    required_cols = [
        "text", "success", "word_count",
        "region_group_final", "main_frame"
    ]
    validate_columns(df, required_cols)

    df["success_norm"] = normalize_success_col(df["success"])
    df["word_count"] = pd.to_numeric(df["word_count"], errors="coerce")

    df = df[
        df["text"].notna() &
        df["success_norm"] &
        (df["word_count"] > MIN_WORDS)
    ].copy()

    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"] != ""].copy()
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    if len(df) == 0:
        raise ValueError("筛选后数据为空，请检查 success / word_count / text 过滤条件。")

    print("Clean size:", len(df))
    print("\nRegion distribution:")
    print(df["region_group_final"].fillna("NaN").value_counts(dropna=False))

    # -------------------------
    # 2. 重新算 embedding
    # -------------------------
    print("\n[Embedding]")
    texts = df["text"].tolist()

    model = SentenceTransformer(MODEL_PATH)
    X = model.encode(
        texts,
        show_progress_bar=True,
        batch_size=64,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    if len(X.shape) != 2 or X.shape[0] != len(df):
        raise ValueError(f"embedding 维度异常: X.shape={X.shape}, len(df)={len(df)}")

    # -------------------------
    # 3. UMAP
    # -------------------------
    print("\n[UMAP]")
    n_neighbors = min(10, max(2, len(df) - 1))

    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=0.3,
        metric="cosine",
        random_state=42
    )

    coords = reducer.fit_transform(X)
    df["x"] = coords[:, 0]
    df["y"] = coords[:, 1]

    ensure_parent_dir(OUT_WITH_XY)
    df.to_csv(OUT_WITH_XY, index=False, encoding="utf-8-sig")
    print("Saved with xy:", OUT_WITH_XY)

    # =========================
    # Figure A: Top-3 region density
    # =========================
    print("\n[Figure A] Density")
    df_top = df[df["region_group_final"].isin(TOP_REGIONS)].copy()

    if len(df_top) == 0:
        print("Warning: TOP_REGIONS 在数据中没有匹配项，跳过 Density 图。")
    else:
        plt.figure(figsize=(7.5, 6))

        plotted = 0
        for region in TOP_REGIONS:
            sub = df_top[df_top["region_group_final"] == region].copy()

            # KDE 至少要有足够点数，且不能全重合
            if len(sub) < 3:
                print(f"Skip region {region}: too few points ({len(sub)})")
                continue

            if sub["x"].nunique() < 2 or sub["y"].nunique() < 2:
                print(f"Skip region {region}: insufficient variance for KDE")
                continue

            sns.kdeplot(
                data=sub,
                x="x",
                y="y",
                fill=True,
                alpha=0.20,
                levels=3,
                thresh=0.05,
                label=region
            )
            plotted += 1

        if plotted == 0:
            print("Warning: 没有任何 region 满足 KDE 绘图条件，跳过保存 Density 图。")
            plt.close()
        else:
            plt.title("Narrative Density by Region")
            plt.xlabel("Dim 1")
            plt.ylabel("Dim 2")
            plt.legend(frameon=True)
            plt.tight_layout()

            ensure_parent_dir(OUT_DENSITY)
            plt.savefig(OUT_DENSITY, dpi=300, bbox_inches="tight")
            print("Saved:", OUT_DENSITY)
            plt.close()

    # =========================
    # Figure B: Regional centroids
    # =========================
    print("\n[Figure B] Centroids")
    centroid_df = df.dropna(subset=["region_group_final"]).copy()

    if len(centroid_df) == 0:
        print("Warning: region_group_final 全为空，跳过 Centroids 图。")
    else:
        centroids = (
            centroid_df.groupby("region_group_final", as_index=False)[["x", "y"]]
            .mean()
        )

        plt.figure(figsize=(7.5, 6))

        sns.scatterplot(
            data=df,
            x="x",
            y="y",
            color="lightgray",
            s=18,
            alpha=0.25,
            legend=False
        )

        sns.scatterplot(
            data=centroids,
            x="x",
            y="y",
            hue="region_group_final",
            s=220,
            marker="X"
        )

        for _, row in centroids.iterrows():
            plt.text(
                row["x"] + 0.05,
                row["y"] + 0.05,
                str(row["region_group_final"]),
                fontsize=10
            )

        plt.title("Narrative Space with Regional Centroids")
        plt.xlabel("Dim 1")
        plt.ylabel("Dim 2")
        plt.legend(frameon=True, bbox_to_anchor=(1.02, 1), loc="upper left")
        plt.tight_layout()

        ensure_parent_dir(OUT_CENTROID)
        plt.savefig(OUT_CENTROID, dpi=300, bbox_inches="tight")
        print("Saved:", OUT_CENTROID)
        plt.close()

    # =========================
    # Figure C: region × frame heatmap
    # =========================
    print("\n[Figure C] Heatmap")
    heat_df = df.dropna(subset=["region_group_final", "main_frame"]).copy()

    if len(heat_df) == 0:
        print("Warning: region_group_final 或 main_frame 为空，无法绘制 heatmap。")
    else:
        ctab = pd.crosstab(
            heat_df["region_group_final"],
            heat_df["main_frame"],
            normalize="index"
        )

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
        if existing_cols:
            ctab = ctab[existing_cols]

        if ctab.shape[0] == 0 or ctab.shape[1] == 0:
            print("Warning: heatmap 交叉表为空，跳过。")
        else:
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

            ensure_parent_dir(OUT_HEATMAP)
            plt.savefig(OUT_HEATMAP, dpi=300, bbox_inches="tight")
            print("Saved:", OUT_HEATMAP)
            plt.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
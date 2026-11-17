import pandas as pd
from collections import Counter
from datetime import datetime
from tqdm import tqdm


INPUT_PATH = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_pool_raw.csv"
OUTPUT_PATH = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/event_clusters.csv"

TIME_WINDOW_HOURS = 12
MIN_CLUSTER_SIZE = 20


def parse_time(x):
    try:
        return datetime.strptime(str(x), "%Y%m%d%H%M%S")
    except:
        return None


def extract_keywords(text):
    if not isinstance(text, str):
        return []
    return [w for w in text.split(";") if len(w) > 3]


def main():
    print("[INFO] Loading data...")
    df = pd.read_csv(INPUT_PATH)

    df["datetime"] = df["date"].apply(parse_time)
    df = df.dropna(subset=["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    print(f"[INFO] Total articles: {len(df)}")

    clusters = []
    cluster_id = 0

    # 👉 用 index 避免重复扫描
    for i in tqdm(range(len(df)), desc="Clustering"):
        base_time = df.loc[i, "datetime"]

        # 👉 只往后看（关键优化）
        j = i
        window_indices = []

        while j < len(df):
            if df.loc[j, "datetime"] <= base_time + pd.Timedelta(hours=TIME_WINDOW_HOURS):
                window_indices.append(j)
                j += 1
            else:
                break

        if len(window_indices) < MIN_CLUSTER_SIZE:
            continue

        window_df = df.loc[window_indices]

        # 提取关键词
        all_keywords = []
        for t in window_df["themes"]:
            all_keywords.extend(extract_keywords(t))

        counter = Counter(all_keywords)
        top_keywords = [k for k, v in counter.most_common(10)]

        cluster_df = window_df[
            window_df["themes"].apply(
                lambda x: any(k in str(x) for k in top_keywords)
            )
        ]

        if len(cluster_df) >= MIN_CLUSTER_SIZE:
            cluster_df = cluster_df.copy()
            cluster_df["cluster_id"] = cluster_id
            clusters.append(cluster_df)

            print(f"\n[CLUSTER FOUND] id={cluster_id}, size={len(cluster_df)}")
            print(f"Top keywords: {top_keywords[:5]}")

            cluster_id += 1

    if clusters:
        result = pd.concat(clusters, ignore_index=True)
        result.to_csv(OUTPUT_PATH, index=False)

        print("\n[DONE] event_clusters.csv")
        print(result["cluster_id"].value_counts())
    else:
        print("[WARN] No clusters found.")


if __name__ == "__main__":
    main()
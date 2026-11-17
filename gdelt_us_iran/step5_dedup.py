import pandas as pd

df = pd.read_csv("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_expanded.csv")
df = df.drop_duplicates(subset=["text"])
# 只保留成功且文本够长
df = df[
    (df["success"] == True) &
    (df["word_count"] > 100)
].copy()


print("clean size:", len(df))
df.to_csv("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_clean_expanded.csv", index=False)
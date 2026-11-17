import pandas as pd

df = pd.read_csv("/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv")

print(pd.crosstab(df["region_group_final"], df["main_frame"], normalize="index").round(3))
import pandas as pd

INPUT = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events_v3/all_events_crawl_sample_v3.csv"

df = pd.read_csv(INPUT, low_memory=False)

print("\n" + "="*80)
print("TOTAL")
print("="*80)
print("Rows:", len(df))
print("Events:", df["event_id"].nunique())
print("Regions:", df["country_group_final"].nunique())
print("Domains:", df["domain_norm"].nunique())

print("\n" + "="*80)
print("EVENT DISTRIBUTION")
print("="*80)
print(df["event_id"].value_counts())

print("\n" + "="*80)
print("REGION DISTRIBUTION")
print("="*80)
print(df["country_group_final"].value_counts())

print("\n" + "="*80)
print("TOP 100 DOMAINS")
print("="*80)
print(df["domain_norm"].value_counts().head(100))

print("\n" + "="*80)
print("EVENT × REGION")
print("="*80)

stats = (
    df.groupby(["event_id","country_group_final"])
      .agg(
          rows=("url","count"),
          domains=("domain_norm","nunique")
      )
      .reset_index()
      .sort_values(["event_id","rows"], ascending=[True, False])
)

print(stats.to_string())

print("\n" + "="*80)
print("LOW DOMAIN DIVERSITY (<5)")
print("="*80)

low = stats[stats["domains"] < 5]
print(low.to_string())

print("\n" + "="*80)
print("EVENT × REGION × DOMAIN TOP")
print("="*80)

for (event, region), sub in df.groupby(["event_id","country_group_final"]):
    print(f"\n[{event}] [{region}]")
    print(sub["domain_norm"].value_counts().head(10))
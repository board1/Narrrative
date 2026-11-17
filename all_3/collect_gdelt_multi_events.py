import time
import zipfile
import requests
import pandas as pd

from pathlib import Path
from tqdm import tqdm

MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

BASE_DIR = Path("data/gdelt_events")
RAW_DIR = BASE_DIR / "raw_gkg"
MASTER_FILE = BASE_DIR / "masterfilelist.txt"

RAW_DIR.mkdir(parents=True, exist_ok=True)

EVENTS = {
    "russia_ukraine_invasion_2022": {
        "start_date": "20220224",
        "end_date": "20220324",
        "actor_terms": ["RUSSIA", "RUSSIAN", "UKRAINE", "UKRAINIAN", "NATO", "UNITED STATES", "EUROPE"],
        "event_terms": ["INVASION", "WAR", "ATTACK", "MISSILE", "STRIKE", "MILITARY", "KYIV", "KIEV", "DONBAS", "SANCTION"],
    },
    "us_iran_israel_2026": {
        "start_date": "20260228",
        "end_date": "20260331",
        "actor_terms": ["IRAN", "IRANIAN", "ISRAEL", "ISRAELI", "UNITED STATES", "U.S.", "AMERICA"],
        "event_terms": ["MISSILE", "ATTACK", "STRIKE", "AIRSTRIKE", "WAR", "MILITARY", "RETALIATION", "ESCALATION", "NUCLEAR", "SANCTION"],
    },
    "trump_liberation_day_tariffs_2025": {
        "start_date": "20250402",
        "end_date": "20250502",
        "actor_terms": ["UNITED STATES", "U.S.", "AMERICA", "CHINA", "EUROPEAN UNION", "EU", "CANADA", "MEXICO", "JAPAN"],
        "event_terms": ["TARIFF", "TARIFFS", "IMPORT DUTY", "TRADE WAR", "RECIPROCAL TARIFF", "LIBERATION DAY", "SUPPLY CHAIN"],
    },
    "us_china_trade_war_2018": {
        "start_date": "20180301",
        "end_date": "20180415",
        "actor_terms": ["UNITED STATES", "U.S.", "AMERICA", "CHINA", "CHINESE"],
        "event_terms": ["TARIFF", "TARIFFS", "STEEL", "ALUMINUM", "TRADE WAR", "SECTION 232", "SECTION 301", "IMPORTS"],
    },
    "gaza_conflict_2023": {
        "start_date": "20231007",
        "end_date": "20231107",
        "actor_terms": ["ISRAEL", "ISRAELI", "GAZA", "PALESTINE", "PALESTINIAN", "HAMAS", "UNITED STATES"],
        "event_terms": ["ATTACK", "WAR", "AIRSTRIKE", "HOSTAGE", "CIVILIAN", "HUMANITARIAN", "CEASEFIRE", "BOMBING"],
    },
    "covid_origin_investigation_2021": {
        "start_date": "20210526",
        "end_date": "20210827",
        "actor_terms": ["CHINA", "CHINESE", "UNITED STATES", "U.S.", "WHO", "WUHAN", "BEIJING", "BIDEN"],
        "event_terms": ["COVID", "CORONAVIRUS", "LAB LEAK", "ORIGIN", "WUHAN INSTITUTE", "ZOONOTIC", "GAIN OF FUNCTION", "INTELLIGENCE REPORT", "VIROLOGY", "PANDEMIC ORIGIN"],
    },
    "cop28_dubai_2023": {
        "start_date": "20231128",
        "end_date": "20231215",
        "actor_terms": ["UNITED NATIONS", "UAE", "DUBAI", "UNITED STATES", "CHINA", "EUROPEAN UNION", "INDIA", "BRAZIL", "SAUDI ARABIA"],
        "event_terms": ["COP28", "CLIMATE SUMMIT", "FOSSIL FUEL", "PHASE OUT", "RENEWABLE", "EMISSIONS", "GLOBAL STOCKTAKE", "CLIMATE FINANCE", "LOSS AND DAMAGE", "TRANSITION"],
    },
}

GKG_COLUMNS = [
    "gkg_record_id",
    "date",
    "source_collection_id",
    "source_common_name",
    "document_identifier",
    "counts",
    "v2_counts",
    "themes",
    "v2_themes",
    "locations",
    "v2_locations",
    "persons",
    "v2_persons",
    "organizations",
    "v2_organizations",
    "v2_tone",
    "dates",
    "gcam",
    "sharing_image",
    "related_images",
    "social_image_embeds",
    "social_video_embeds",
    "quotations",
    "all_names",
    "amounts",
    "translation_info",
    "extras",
]


def download_masterfile():
    if MASTER_FILE.exists():
        print(f"[Skip] masterfile exists: {MASTER_FILE}")
        return

    print("[Download] masterfilelist")
    r = requests.get(MASTER_URL, timeout=60)
    r.raise_for_status()
    MASTER_FILE.write_bytes(r.content)
    print("Saved:", MASTER_FILE)


def get_timestamp_from_url(url_or_name: str) -> str:
    name = url_or_name.split("/")[-1]
    return name.split(".")[0]


def read_master_urls():
    lines = MASTER_FILE.read_text(errors="ignore").splitlines()
    urls = []

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 3:
            continue

        url = parts[-1]
        if ".gkg.csv.zip" not in url:
            continue

        urls.append(url)

    return sorted(set(urls))


def filter_urls_for_event(all_urls, start_date, end_date):
    selected = []
    for url in all_urls:
        ts = get_timestamp_from_url(url)
        day = ts[:8]
        if start_date <= day <= end_date:
            selected.append(url)
    return selected


def download_gkg_file(url):
    filename = url.split("/")[-1]
    out_path = RAW_DIR / filename

    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    try:
        r = requests.get(url, timeout=90)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        time.sleep(0.1)
        return out_path
    except Exception as e:
        print("[Download Error]", url, e)
        return None


def read_gkg_zip(zip_path: Path):
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            inner = z.namelist()[0]
            with z.open(inner) as f:
                df = pd.read_csv(
                    f,
                    sep="\t",
                    header=None,
                    names=GKG_COLUMNS,
                    dtype=str,
                    low_memory=False,
                    on_bad_lines="skip",
                )
        return df
    except Exception as e:
        print("[Read Error]", zip_path, e)
        return pd.DataFrame()


def count_hits(text: str, terms):
    text = str(text).upper()
    return sum(1 for t in terms if t.upper() in text)


def filter_event_rows(df: pd.DataFrame, event_cfg: dict):
    needed_cols = [
        "themes", "v2_themes",
        "locations", "v2_locations",
        "persons", "v2_persons",
        "organizations", "v2_organizations",
        "all_names",
        "source_common_name",
        "document_identifier",
        "v2_tone",
    ]

    for col in needed_cols:
        if col not in df.columns:
            df[col] = ""

    search_text = (
        df["themes"].astype(str) + " " +
        df["v2_themes"].astype(str) + " " +
        df["locations"].astype(str) + " " +
        df["v2_locations"].astype(str) + " " +
        df["persons"].astype(str) + " " +
        df["v2_persons"].astype(str) + " " +
        df["organizations"].astype(str) + " " +
        df["v2_organizations"].astype(str) + " " +
        df["all_names"].astype(str) + " " +
        df["source_common_name"].astype(str) + " " +
        df["document_identifier"].astype(str)
    ).str.upper()

    actor_terms = event_cfg["actor_terms"]
    event_terms = event_cfg["event_terms"]
    all_terms = list(set(actor_terms + event_terms))

    actor_hits = search_text.apply(lambda x: count_hits(x, actor_terms))
    event_hits = search_text.apply(lambda x: count_hits(x, event_terms))
    total_hits = search_text.apply(lambda x: count_hits(x, all_terms))

    # 规则：至少一个行为体 + 至少一个事件词 + 总命中不少于2
    mask = (
        (actor_hits >= 1) &
        (event_hits >= 1) &
        (total_hits >= 2)
    )

    out = df[mask].copy()
    out["actor_hits"] = actor_hits[mask].values
    out["event_hits"] = event_hits[mask].values
    out["total_hits"] = total_hits[mask].values

    return out


def process_one_zip(zip_path: Path, event_id: str, event_cfg: dict, daily_dir: Path):
    ts = get_timestamp_from_url(zip_path.name)
    day = ts[:8]

    df = read_gkg_zip(zip_path)
    if df.empty:
        return 0, 0

    raw_n = len(df)
    filtered = filter_event_rows(df, event_cfg)

    if filtered.empty:
        return raw_n, 0

    filtered["event_id"] = event_id
    filtered["event_start"] = event_cfg["start_date"]
    filtered["event_end"] = event_cfg["end_date"]
    filtered["gdelt_file"] = zip_path.name
    filtered["gdelt_timestamp"] = ts
    filtered["day"] = day

    keep_cols = [
        "event_id",
        "event_start",
        "event_end",
        "day",
        "gdelt_timestamp",
        "source_common_name",
        "document_identifier",
        "themes",
        "v2_themes",
        "locations",
        "v2_locations",
        "persons",
        "v2_persons",
        "organizations",
        "v2_organizations",
        "all_names",
        "v2_tone",
        "actor_hits",
        "event_hits",
        "total_hits",
        "gdelt_file",
    ]

    filtered = filtered[[c for c in keep_cols if c in filtered.columns]].copy()

    daily_out = daily_dir / f"{day}.csv"

    if daily_out.exists():
        filtered.to_csv(
            daily_out,
            mode="a",
            header=False,
            index=False,
            encoding="utf-8-sig",
        )
    else:
        filtered.to_csv(
            daily_out,
            index=False,
            encoding="utf-8-sig",
        )

    return raw_n, len(filtered)


def merge_daily_outputs(daily_dir: Path):
    files = sorted(daily_dir.glob("*.csv"))
    dfs = []

    for f in files:
        try:
            dfs.append(pd.read_csv(f, low_memory=False))
        except Exception as e:
            print("[Merge Error]", f, e)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    df = df.rename(columns={
        "document_identifier": "url",
        "source_common_name": "domain",
    })

    df["url"] = df["url"].astype(str)
    df["domain"] = df["domain"].astype(str)

    df = df[df["url"].str.startswith("http", na=False)].copy()
    df = df.drop_duplicates(subset=["url"]).reset_index(drop=True)

    return df


def run_event(event_id: str, event_cfg: dict, all_urls):
    print("\n" + "=" * 80)
    print(f"[EVENT] {event_id}")
    print(f"Window: {event_cfg['start_date']} - {event_cfg['end_date']}")

    event_dir = BASE_DIR / "events" / event_id
    daily_dir = event_dir / "daily_filtered"
    flags_dir = event_dir / "processed_flags"

    event_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)
    flags_dir.mkdir(parents=True, exist_ok=True)

    out_candidates = event_dir / "candidates.csv"
    out_url_pool = event_dir / "url_pool.csv"
    out_stats = event_dir / "stats.csv"

    urls = filter_urls_for_event(
        all_urls,
        event_cfg["start_date"],
        event_cfg["end_date"],
    )

    print(f"GKG files selected: {len(urls)}")

    stats = []

    for url in tqdm(urls, desc=event_id):
        zip_path = download_gkg_file(url)
        if zip_path is None:
            continue

        flag = flags_dir / f"{zip_path.name}.done"
        if flag.exists():
            continue

        raw_n, kept_n = process_one_zip(
            zip_path=zip_path,
            event_id=event_id,
            event_cfg=event_cfg,
            daily_dir=daily_dir,
        )

        stats.append({
            "event_id": event_id,
            "file": zip_path.name,
            "raw_rows": raw_n,
            "kept_rows": kept_n,
        })

        flag.write_text("done", encoding="utf-8")

    if stats:
        pd.DataFrame(stats).to_csv(out_stats, index=False, encoding="utf-8-sig")
        print("Saved stats:", out_stats)

    df = merge_daily_outputs(daily_dir)

    if df.empty:
        print("[Warning] no candidates found:", event_id)
        return

    df.to_csv(out_candidates, index=False, encoding="utf-8-sig")
    print("Saved candidates:", out_candidates, "rows=", len(df))

    url_pool_cols = [
        "event_id",
        "event_start",
        "event_end",
        "day",
        "gdelt_timestamp",
        "domain",
        "url",
        "themes",
        "v2_themes",
        "locations",
        "v2_locations",
        "persons",
        "v2_persons",
        "organizations",
        "v2_organizations",
        "all_names",
        "v2_tone",
        "actor_hits",
        "event_hits",
        "total_hits",
    ]

    url_pool = df[[c for c in url_pool_cols if c in df.columns]].copy()
    url_pool = url_pool.drop_duplicates(subset=["url"]).reset_index(drop=True)

    url_pool.to_csv(out_url_pool, index=False, encoding="utf-8-sig")
    print("Saved URL pool:", out_url_pool, "rows=", len(url_pool))

    print("\nTop domains:")
    print(url_pool["domain"].value_counts().head(20))


def merge_all_events():
    all_files = sorted((BASE_DIR / "events").glob("*/url_pool.csv"))
    dfs = []

    for f in all_files:
        try:
            dfs.append(pd.read_csv(f, low_memory=False))
        except Exception as e:
            print("[All Merge Error]", f, e)

    if not dfs:
        return

    all_df = pd.concat(dfs, ignore_index=True)
    all_df = all_df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    out = BASE_DIR / "all_events_url_pool.csv"
    all_df.to_csv(out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 80)
    print("Saved all events URL pool:", out, "rows=", len(all_df))
    print("\nRows by event:")
    print(all_df["event_id"].value_counts())


def main():
    download_masterfile()
    all_urls = read_master_urls()
    print("Total GKG URLs in masterfile:", len(all_urls))

    for event_id, event_cfg in EVENTS.items():
        run_event(event_id, event_cfg, all_urls)

    merge_all_events()

    print("\nDone.")


if __name__ == "__main__":
    main()
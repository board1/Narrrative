"""采集两个新事件的 GDELT 原始数据：COVID-19 起源 + COP28（修复版：从 v2_gcam 提取 URL，在 locations 搜索主题编码）"""
import time, zipfile, requests, pandas as pd, re as re_mod
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
BASE_DIR = Path("data/gdelt_events")
RAW_DIR = BASE_DIR / "raw_gkg"
MASTER_FILE = BASE_DIR / "masterfilelist.txt"
RAW_DIR.mkdir(parents=True, exist_ok=True)
EXISTING_MASTER = Path("../all_3/data/gdelt_events/masterfilelist.txt")

EVENTS = {
    "covid_origin_investigation_2021": {
        "start_date": "20210526",
        "end_date": "20210827",
        "actor_terms": ["UNITED STATES", "CHINA", "CHINESE", "BEIJING", "WUHAN", "WHO", "BIDEN", "XI JINPING"],
        "event_terms": ["TAX_DISEASE_CORONAVIRUS", "TAX_DISEASE_COVID", "HEALTH_PANDEMIC", "HEALTH_VACCINATION",
                        "WUHAN INSTITUTE", "LAB LEAK", "ZOONOTIC", "GAIN OF FUNCTION", "ORIGIN",
                        "VIROLOGY", "COVID-19", "CORONAVIRUS", "COVID", "PANDEMIC ORIGIN"],
    },
    "cop28_dubai_2023": {
        "start_date": "20231128",
        "end_date": "20231215",
        "actor_terms": ["UNITED NATIONS", "UAE", "DUBAI", "UNITED STATES", "CHINA", "EUROPEAN UNION",
                        "INDIA", "BRAZIL", "SAUDI ARABIA"],
        "event_terms": ["ENV_CLIMATECHANGE", "ENV_GREEN", "ENV_OIL", "ENV_SOLAR", "ENV_CARBONCAPTURE",
                        "ENV_COAL", "CARBON", "FOSSIL", "RENEWABLE", "EMISSION",
                        "GLOBAL_WARMING", "PARIS_ACCORD", "UNFCCC", "CLIMATE CHANGE", "ENERGY TRANSITION",
                        "COP28", "GLOBAL STOCKTAKE", "LOSS AND DAMAGE"],
    },
}

GKG_COLUMNS = [
    "gkg_record_id", "date", "source_collection_id", "source_common_name",
    "document_identifier", "themes", "v2_themes", "locations", "v2_locations",
    "persons", "v2_persons", "organizations", "v2_organizations",
    "tone", "v2_tone", "counts", "v2_counts", "all_names",
    "v2_all_names", "urls", "v1urls", "v2urls", "domainstags", "translation_info",
    "extras", "v2_extras", "v2_gcam", "v2_share_img", "v2_ocr",
]

URL_COLS = [
    "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
    "domain", "url", "themes", "v2_themes", "locations", "v2_locations",
    "persons", "v2_persons", "organizations", "v2_organizations",
    "all_names", "v2_tone", "actor_hits", "event_hits", "total_hits",
]


def download_master():
    if EXISTING_MASTER.exists():
        print(f"[Reuse] Existing master file: {EXISTING_MASTER}")
        text = EXISTING_MASTER.read_text(encoding="utf-8")
        MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
        MASTER_FILE.write_text(text, encoding="utf-8")
    else:
        print("[Download] master file list ...")
        r = requests.get(MASTER_URL, timeout=120)
        r.raise_for_status()
        MASTER_FILE.write_text(r.text, encoding="utf-8")
        text = r.text
    lines = [l for l in text.strip().split("\n") if l.strip()]
    print(f"  Total entries: {len(lines)}")
    return lines


def download_zip(url, dest):
    if dest.exists():
        return True
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
    return False


def extract_urls_from_gcam(gcam_val):
    """从 v2_gcam XML 中提取 HTTPS 文章链接，排除社交/视频网站"""
    urls = set()
    if pd.isna(gcam_val):
        return urls
    s = str(gcam_val)
    skip_prefixes = ('https://twitter', 'https://t.co', 'https://facebook', 'https://instagram',
                     'https://youtube', 'https://youtu.be', 'https://linkedin', 'https://x.com',
                     'https://reddit', 'https://tiktok')
    for m in re_mod.finditer(r'https?://[^\s<>"\']{20,}', s):
        u = m.group().rstrip('.;,')
        if not any(u.lower().startswith(p) for p in skip_prefixes):
            urls.add(u)
    return urls


def process_one_zip(zip_path, event_id, event_cfg):
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.endswith((".csv", ".CSV")):
                continue
            with zf.open(name) as f:
                try:
                    df = pd.read_csv(f, sep="\t", header=None, names=GKG_COLUMNS, low_memory=False)
                except Exception:
                    continue

            # 构建搜索文本：locations(主题编码) + v2_gcam(文章标题/元数据) + themes
            search = pd.Series("", index=df.index)
            for col in ["locations", "v2_locations", "v2_gcam", "themes"]:
                search += " | " + df[col].fillna("").astype(str).str.upper()

            # 事件关键词匹配
            event_mask = pd.Series(False, index=df.index)
            for term in event_cfg["event_terms"]:
                event_mask |= search.str.contains(term.upper(), na=False)

            # Actor 关键词匹配
            actor_mask = pd.Series(False, index=df.index)
            for term in event_cfg["actor_terms"]:
                actor_mask |= search.str.contains(term.upper(), na=False)

            hits = df[event_mask & actor_mask] if actor_mask.any() else df[event_mask]
            if len(hits) == 0:
                continue

            for idx in hits.index:
                row = hits.loc[idx]
                domain = str(row.get("document_identifier", ""))
                domain = domain.lower() if domain and domain != "nan" else ""
                day = str(row["date"])[:8] if pd.notna(row["date"]) else ""

                # 优先 v2_gcam 提取 URL，其次 v2urls / v1urls
                gcam_urls = extract_urls_from_gcam(row.get("v2_gcam", ""))
                if gcam_urls:
                    url_list = list(gcam_urls)
                else:
                    url_str = ""
                    for ucol in ["v2urls", "v1urls"]:
                        val = str(row.get(ucol, ""))
                        if val and val != "nan":
                            url_str = val
                            break
                    url_list = [u.strip() for u in url_str.split(";") if u.strip().startswith("http")]

                for u in url_list:
                    rows.append({
                        "event_id": event_id,
                        "event_start": event_cfg["start_date"],
                        "event_end": event_cfg["end_date"],
                        "day": day,
                        "gdelt_timestamp": str(row["date"]),
                        "domain": domain,
                        "url": u,
                        "themes": str(row.get("themes", "")),
                        "v2_themes": str(row.get("v2_themes", "")),
                        "locations": str(row.get("locations", "")),
                        "v2_locations": str(row.get("v2_locations", "")),
                        "persons": str(row.get("persons", "")),
                        "v2_persons": str(row.get("v2_persons", "")),
                        "organizations": str(row.get("organizations", "")),
                        "v2_organizations": str(row.get("v2_organizations", "")),
                        "all_names": str(row.get("all_names", "")),
                        "v2_tone": str(row.get("v2_tone", "")),
                        "actor_hits": 1, "event_hits": 1, "total_hits": 1,
                    })
    return rows


def download_and_process(url, event_id, event_cfg):
    fname = url.split("/")[-1]
    dest = RAW_DIR / fname
    if not download_zip(url, dest):
        return []
    return process_one_zip(dest, event_id, event_cfg)


def run_event(event_id, event_cfg, all_urls, workers=8):
    print(f"\n[EVENT] {event_id}")
    dates = pd.date_range(start=event_cfg["start_date"], end=event_cfg["end_date"], freq="D")
    date_set = {d.strftime("%Y%m%d") for d in dates}

    relevant = [(u, u.split("/")[-1]) for u, _ in all_urls
                if ".gkg.csv.zip" in u and len(u.split("/")[-1].split(".")[0]) >= 8
                and u.split("/")[-1].split(".")[0][:8] in date_set]
    print(f"  GKG ZIPs: {len(relevant)}")
    if len(relevant) == 0:
        return pd.DataFrame()

    all_rows = []
    urls = [u for u, _ in relevant]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(download_and_process, url, event_id, event_cfg): url for url in urls}
        for fut in tqdm(as_completed(futures), total=len(urls), desc=event_id):
            try:
                all_rows.extend(fut.result())
            except Exception:
                pass

    if not all_rows:
        print("[Warning] no candidates found:", event_id)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)
    print(f"  Candidates: {len(df)}")
    return df


def main():
    lines = download_master()
    all_urls = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        url = parts[2]
        if ".gkg.csv.zip" in url:
            all_urls.append((url, url.split("/")[-1]))

    all_dfs = []
    for event_id, event_cfg in EVENTS.items():
        df = run_event(event_id, event_cfg, all_urls)
        if len(df) > 0:
            all_dfs.append(df)

    if all_dfs:
        out = pd.concat(all_dfs, ignore_index=True)
        out = out.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)
        out_path = BASE_DIR / "all_events_url_pool.csv"
        out[URL_COLS].to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\n=== FINAL ===")
        print(f"Total rows: {len(out)}")
        print(f"Saved: {out_path}")
        print(out["event_id"].value_counts())
    else:
        print("\nNo data collected.")


if __name__ == "__main__":
    main()

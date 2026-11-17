import requests
from pathlib import Path
from datetime import datetime

# =========================
# 配置
# =========================
START_DATE = "20260301"
END_DATE   = "20260331"

MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

DATA_DIR = Path("data/gdelt_raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MASTER_FILE = Path("data/masterfilelist.txt")


# =========================
# Step 1: 下载 masterfilelist
# =========================
def download_master():
    if MASTER_FILE.exists():
        print("Master file exists, skip download.")
        return

    print("[Download masterfilelist]")
    r = requests.get(MASTER_URL, timeout=60)
    r.raise_for_status()

    MASTER_FILE.write_bytes(r.content)
    print("Saved:", MASTER_FILE)


# =========================
# Step 2: 解析时间
# =========================
def parse_time_from_url(url):
    # 示例：
    # http://data.gdeltproject.org/gdeltv2/20260301120000.gkg.csv.zip
    name = url.split("/")[-1]
    timestamp = name.split(".")[0]
    return timestamp  # 20260301120000


def in_range(ts):
    return START_DATE <= ts[:8] <= END_DATE


# =========================
# Step 3: 筛选需要下载的文件
# =========================
def filter_gkg_files():
    lines = MASTER_FILE.read_text().splitlines()

    urls = []

    for line in lines:
        parts = line.strip().split(" ")
        if len(parts) < 3:
            continue

        url = parts[-1]

        # 只要 gkg（包含文本、URL）
        if ".gkg.csv.zip" not in url:
            continue

        ts = parse_time_from_url(url)

        if in_range(ts):
            urls.append(url)

    print(f"Selected {len(urls)} files")
    return urls


# =========================
# Step 4: 下载（支持断点）
# =========================
def download_files(urls):
    for i, url in enumerate(urls):
        filename = url.split("/")[-1]
        out_path = DATA_DIR / filename

        if out_path.exists():
            continue

        try:
            print(f"[{i+1}/{len(urls)}] Downloading {filename}")
            r = requests.get(url, timeout=60)
            r.raise_for_status()

            out_path.write_bytes(r.content)

        except Exception as e:
            print("Error:", url, e)


# =========================
# main
# =========================
def main():
    download_master()
    urls = filter_gkg_files()
    download_files(urls)


if __name__ == "__main__":
    main()
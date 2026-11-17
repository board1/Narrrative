import os
import time
import requests
from pathlib import Path

infile = Path("data/gkg_urls_filtered.txt")
outdir = Path("data/gkg_zips")
outdir.mkdir(parents=True, exist_ok=True)

session = requests.Session()

with open(infile, "r", encoding="utf-8") as f:
    urls = [line.strip() for line in f if line.strip()]

for i, url in enumerate(urls, 1):
    filename = url.split("/")[-1]
    savepath = outdir / filename

    if savepath.exists():
        print(f"[{i}/{len(urls)}] exists, skip:", filename)
        continue

    print(f"[{i}/{len(urls)}] downloading:", filename)
    try:
        r = session.get(url, timeout=120)
        r.raise_for_status()
        with open(savepath, "wb") as out:
            out.write(r.content)
    except Exception as e:
        print("failed:", url, e)

    time.sleep(1)
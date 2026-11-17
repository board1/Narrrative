from pathlib import Path

infile = Path("data/gkg_urls.txt")
outfile = Path("data/gkg_urls_filtered.txt")

# 改成你想要的日期前缀
date_prefixes = [
    "20260311", "20260312", "20260313", "20260314",
    "20260315", "20260316", "20260317"
]

count = 0
with open(infile, "r", encoding="utf-8") as f, open(outfile, "w", encoding="utf-8") as out:
    for line in f:
        url = line.strip()
        filename = url.split("/")[-1]
        if any(filename.startswith(prefix) for prefix in date_prefixes):
            out.write(url + "\n")
            count += 1

print("saved", count, "filtered GKG urls to", outfile)
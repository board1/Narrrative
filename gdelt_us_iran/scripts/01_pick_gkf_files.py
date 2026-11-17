from pathlib import Path

infile = Path("data/masterfilelist.txt")
outfile = Path("data/gkg_urls.txt")

count = 0
with open(infile, "r", encoding="utf-8") as f, open(outfile, "w", encoding="utf-8") as out:
    for line in f:
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        url = parts[-1]
        if ".gkg.csv.zip" in url:
            out.write(url + "\n")
            count += 1

print("saved", count, "GKG file urls to", outfile)
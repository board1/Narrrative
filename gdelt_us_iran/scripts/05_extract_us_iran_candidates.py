import csv
import sys
import json
from pathlib import Path

# ⭐ 关键：放开字段长度限制
csv.field_size_limit(sys.maxsize)

csv_dir = Path("data/gkg_csv")
outfile = Path("data/us_iran_candidates.jsonl")

def hit(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    has_iran = any(k in t for k in ["iran", "iranian", "tehran", "irgc"])
    has_us = any(k in t for k in ["united states", "u.s.", "us ", "america", "washington", "pentagon"])
    return has_iran and has_us

count = 0

with open(outfile, "w", encoding="utf-8") as out:
    for file in sorted(csv_dir.glob("*.gkg.csv")):
        print("processing:", file.name)

        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f, delimiter="\t")

            for row in reader:
                if len(row) < 5:
                    continue

                try:
                    url = row[-1]
                    text_blob = " ".join(row[:15])  # 只用前面字段，避免爆内存

                    if hit(text_blob):
                        rec = {
                            "url": url,
                            "source": row[3] if len(row) > 3 else None,
                            "themes": row[7] if len(row) > 7 else None,
                            "tone": row[15] if len(row) > 15 else None,
                        }
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        count += 1

                except Exception as e:
                    continue

print("saved", count, "candidate articles")
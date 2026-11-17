import json
from pathlib import Path

IN_FILE = Path("data/us_iran_candidates_parsed.jsonl")
OUT_FILE = Path("data/us_iran_candidates_unique.jsonl")

seen = set()
kept = 0
total = 0

with open(IN_FILE, "r", encoding="utf-8") as f, open(OUT_FILE, "w", encoding="utf-8") as out:
    for line in f:
        total += 1
        item = json.loads(line)
        url = item.get("article_url")

        if not url:
            continue
        if url in seen:
            continue

        seen.add(url)
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        kept += 1

print(f"dedup done: kept {kept} / total {total}")
print(f"saved to {OUT_FILE}")
import json
from pathlib import Path

infile = Path("data/us_iran_candidates.jsonl")
outfile = Path("data/us_iran_candidates_dedup.jsonl")

seen = set()
count = 0

with open(infile, "r", encoding="utf-8") as f, open(outfile, "w", encoding="utf-8") as out:
    for line in f:
        item = json.loads(line)
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        count += 1

print("saved", count, "deduped candidates")
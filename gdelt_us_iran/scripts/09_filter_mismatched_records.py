import json
import re
from pathlib import Path
from urllib.parse import urlparse

IN_FILE = Path("data/us_iran_candidates_unique.jsonl")
OUT_FILE = Path("data/us_iran_candidates_filtered.jsonl")

KEYWORDS = [
    "iran", "iranian", "tehran", "irgc",
    "us", "u.s", "united states", "america", "washington", "pentagon"
]

def normalize(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9\s\-]", " ", text.lower())

def keep_record(title: str, url: str, themes: str) -> bool:
    text = " ".join([title or "", themes or ""]).lower()
    url_text = normalize(url or "")

    has_iran = any(k in text for k in ["iran", "iranian", "tehran", "irgc"])
    has_us = any(k in text for k in ["us", "u.s", "united states", "america", "washington", "pentagon"])

    if not (has_iran and has_us):
        return False

    # 链接里至少也该有一个主题词，否则大概率错配
    if not any(k in url_text for k in ["iran", "tehran", "us", "america", "washington", "pentagon"]):
        return False

    return True

kept = 0
total = 0

with open(IN_FILE, "r", encoding="utf-8") as f, open(OUT_FILE, "w", encoding="utf-8") as out:
    for line in f:
        total += 1
        item = json.loads(line)

        if keep_record(item.get("title", ""), item.get("article_url", ""), item.get("themes", "")):
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            kept += 1

print(f"filtered done: kept {kept} / total {total}")
print(f"saved to {OUT_FILE}")
import json
import re
from pathlib import Path

IN_FILE = Path("data/us_iran_candidates.jsonl")
OUT_FILE = Path("data/us_iran_candidates_parsed.jsonl")

def extract_tag(text: str, tag: str):
    pattern = rf"<{tag}>(.*?)</{tag}>"
    m = re.search(pattern, text, flags=re.DOTALL)
    return m.group(1).strip() if m else None

def choose_best_url(raw_url_field: str):
    amp_url = extract_tag(raw_url_field, "PAGE_ALTURL_AMP")
    page_links = extract_tag(raw_url_field, "PAGE_LINKS")

    # 1. 优先 AMP 链接
    if amp_url and amp_url.startswith("http"):
        return amp_url

    # 2. 再从 PAGE_LINKS 里挑看起来像正文页的
    if page_links:
        links = [x.strip() for x in page_links.split(";") if x.strip()]
        good_links = []
        bad_keywords = ["privacy", "disclaimer", "/agency/", "/tag/", "/topics/"]

        for link in links:
            if not link.startswith("http"):
                continue
            if any(b in link.lower() for b in bad_keywords):
                continue
            # 简单判断：正文页通常带 .html 或较长 slug
            if ".html" in link or link.count("/") >= 4:
                good_links.append(link)

        if good_links:
            return good_links[0]

    return None

def is_us_iran_related(title: str, url: str, themes: str):
    text = " ".join([
        title or "",
        url or "",
        themes or ""
    ]).lower()

    has_iran = any(k in text for k in ["iran", "iranian", "tehran", "irgc"])
    has_us = any(k in text for k in ["united states", "u.s.", "us ", "washington", "pentagon", "america"])

    return has_iran and has_us

count_in = 0
count_out = 0

with open(IN_FILE, "r", encoding="utf-8") as f, open(OUT_FILE, "w", encoding="utf-8") as out:
    for line in f:
        count_in += 1
        item = json.loads(line)

        raw_url_field = item.get("url", "")
        title = extract_tag(raw_url_field, "PAGE_TITLE")
        publish_time = extract_tag(raw_url_field, "PAGE_PRECISEPUBTIMESTAMP")
        amp_url = extract_tag(raw_url_field, "PAGE_ALTURL_AMP")
        article_url = choose_best_url(raw_url_field)

        parsed = {
            "source": item.get("source"),
            "title": title,
            "publish_time": publish_time,
            "amp_url": amp_url,
            "article_url": article_url,
            "themes": item.get("themes"),
            "tone": item.get("tone"),
        }

        # 二次过滤：必须真的是 US-Iran
        if article_url and is_us_iran_related(title or "", article_url or "", item.get("themes", "")):
            out.write(json.dumps(parsed, ensure_ascii=False) + "\n")
            count_out += 1

print(f"parsed {count_in} records, kept {count_out}")
print(f"saved to {OUT_FILE}")
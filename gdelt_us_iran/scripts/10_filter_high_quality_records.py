import json
import re
from pathlib import Path
from urllib.parse import urlparse

IN_FILE = Path("data/us_iran_candidates_unique.jsonl")
OUT_KEEP = Path("data/us_iran_candidates_high_quality.jsonl")
OUT_REJECT = Path("data/us_iran_candidates_rejected.jsonl")

# 明确排除：社交媒体 / 视频平台
SOCIAL_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "reddit.com"
}

# 往往不是单篇稳定新闻正文页
BAD_URL_PATTERNS = [
    "/video/",
    "/videos/",
    "/gallery/",
    "/photos/",
    "/podcast/",
    "/podcasts/",
    "/tag/",
    "/tags/",
    "/topic/",
    "/topics/",
    "/search/",
    "/category/",
    "/categories/",
]

# 单独标记，不直接全部删除
LIVE_PATTERNS = [
    "/live-updates/",
    "/live/",
    "live-blog",
    "liveblog",
    "/updates/",
]

# 主题词
IRAN_WORDS = [
    "iran", "iranian", "tehran", "irgc", "hormuz",
    "persian gulf", "persian-gulf", "khamenei"
]

US_WORDS = [
    "united states", "u.s", "us ", " u s ", "america",
    "american", "washington", "pentagon", "trump", "white house"
]

# 一些容易误伤的标题词，但如果链接完全不对应，要删
WEAK_MISMATCH_HINTS = [
    "draft scare", "property tax", "school", "tariffs"
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = text.replace("%20", " ")
    text = re.sub(r"[_\-\/\?\=\&\.\:\,]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_any(text: str, words) -> bool:
    return any(w in text for w in words)


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_social(url: str) -> bool:
    d = domain_of(url)
    return any(d == s or d.endswith("." + s) for s in SOCIAL_DOMAINS)


def has_bad_pattern(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in BAD_URL_PATTERNS)


def detect_page_type(url: str) -> str:
    u = url.lower()
    if any(p in u for p in LIVE_PATTERNS):
        return "live"
    return "article"


def extract_slug_tokens(url: str):
    u = normalize_text(url)
    tokens = set(u.split())
    return tokens


def title_url_consistency_score(title: str, url: str):
    """
    一个简单的一致性打分：
    - 标题和 URL 共享核心词越多，分越高
    """
    title_n = normalize_text(title)
    url_n = normalize_text(url)

    title_hits = set()
    url_hits = set()

    all_core_words = [
        "iran", "iranian", "tehran", "hormuz", "persian", "gulf",
        "us", "america", "american", "washington", "pentagon", "trump",
        "strike", "war", "troops", "oil", "threats", "draft"
    ]

    for w in all_core_words:
        if w in title_n:
            title_hits.add(w)
        if w in url_n:
            url_hits.add(w)

    overlap = len(title_hits & url_hits)
    return overlap, sorted(title_hits), sorted(url_hits)


def evaluate_record(item: dict):
    """
    返回:
    keep: bool
    reason: str
    enriched_item: dict
    """
    title = item.get("title", "") or ""
    url = item.get("article_url", "") or ""
    themes = item.get("themes", "") or ""
    source = item.get("source", "") or ""

    title_n = normalize_text(title)
    url_n = normalize_text(url)
    themes_n = normalize_text(themes)

    enriched = dict(item)
    enriched["source_domain"] = domain_of(url)
    enriched["page_type"] = detect_page_type(url)

    if not url:
        return False, "missing_url", enriched

    if is_social(url):
        return False, "social_url", enriched

    if has_bad_pattern(url):
        return False, "bad_url_pattern", enriched

    # 基本主题判断：整条记录必须同时带 US + Iran
    combined = " ".join([title_n, url_n, themes_n])

    has_iran = contains_any(combined, IRAN_WORDS)
    has_us = contains_any(combined, US_WORDS)

    if not has_iran:
        return False, "missing_iran_signal", enriched
    if not has_us:
        return False, "missing_us_signal", enriched

    # 标题至少也应该跟 Iran 有点关系
    if not contains_any(title_n + " " + themes_n, IRAN_WORDS):
        return False, "title_theme_no_iran", enriched

    # 标题-链接一致性检查
    overlap, title_hits, url_hits = title_url_consistency_score(title, url)
    enriched["title_url_overlap"] = overlap
    enriched["title_hits"] = title_hits
    enriched["url_hits"] = url_hits

    # 强错配：标题里有主题词，但 URL 完全没有相关词
    if contains_any(title_n, IRAN_WORDS) and not contains_any(url_n + " " + themes_n, IRAN_WORDS):
        return False, "iran_mismatch_title_vs_url", enriched

    # 如果标题里有美国相关内容，但 URL+themes 完全无相关信号，也删
    if contains_any(title_n, US_WORDS) and not contains_any(url_n + " " + themes_n, US_WORDS + IRAN_WORDS):
        return False, "us_mismatch_title_vs_url", enriched

    # 显著错配：标题和链接几乎没有任何共同关键词，且标题含弱错配提示词
    if overlap == 0 and contains_any(title_n, WEAK_MISMATCH_HINTS):
        return False, "weak_title_url_match", enriched

    # live 页面不删，但单独标记，后续分析可分开
    if enriched["page_type"] == "live":
        enriched["quality_flag"] = "live_page"
        return True, "keep_live", enriched

    # 正常文章页：要求至少有一点标题-链接重合，或者链接本身足够强主题
    strong_url_signal = contains_any(url_n, IRAN_WORDS) and contains_any(url_n + " " + themes_n, US_WORDS)
    if overlap >= 1 or strong_url_signal:
        enriched["quality_flag"] = "high"
        return True, "keep_high", enriched

    return False, "low_consistency", enriched


def main():
    total = 0
    kept = 0
    rejected = 0

    with open(IN_FILE, "r", encoding="utf-8") as fin, \
         open(OUT_KEEP, "w", encoding="utf-8") as fkeep, \
         open(OUT_REJECT, "w", encoding="utf-8") as frej:

        for line in fin:
            total += 1
            item = json.loads(line)

            keep, reason, enriched = evaluate_record(item)
            enriched["filter_reason"] = reason

            if keep:
                fkeep.write(json.dumps(enriched, ensure_ascii=False) + "\n")
                kept += 1
            else:
                frej.write(json.dumps(enriched, ensure_ascii=False) + "\n")
                rejected += 1

    print(f"total={total}")
    print(f"kept={kept}")
    print(f"rejected={rejected}")
    print(f"saved keep file to: {OUT_KEEP}")
    print(f"saved reject file to: {OUT_REJECT}")


if __name__ == "__main__":
    main()
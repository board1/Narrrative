#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from collections import Counter
from urllib.parse import urlparse

INPUT = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/interim/gkg_articles_dedup.jsonl"


def get_domain(url):
    try:
        d = urlparse(url).netloc.lower()
        if d.startswith("www."):
            d = d[4:]
        return d
    except:
        return ""


def main():
    domain_counter = Counter()
    total = 0

    with open(INPUT) as f:
        for line in f:
            item = json.loads(line)
            total += 1

            url = item.get("url", "")
            domain = get_domain(url)

            if domain:
                domain_counter[domain] += 1
            else:
                domain_counter["UNKNOWN"] += 1

    print("\n=== ORIGINAL ARTICLES ===")
    print(f"原创文章数量: {total}")

    print("\n=== 媒体列表（按数量排序）===")
    for domain, count in domain_counter.most_common():
        print(f"{domain}\t{count}")

    print("\n=== 媒体总数 ===")
    print(f"{len(domain_counter)}")


if __name__ == "__main__":
    main()
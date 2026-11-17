#!/usr/bin/env python3
"""
Domain → Country mapping v2: ccTLD + local GeoIP database (DB-IP lite)
Phase 1: ccTLD direct mapping (instant)
Phase 2: DNS resolve → local IP-to-country DB lookup (no API calls)
"""

import csv
import gzip
import ipaddress
import json
import os
import socket
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

csv.field_size_limit(sys.maxsize)

CSV_PATH = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/all_events_url_pool.csv"
OUTPUT_MAP = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/domain_country.csv"
OUTPUT_ENRICHED = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/all_events_url_pool_with_country.csv"
CACHE_PATH = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/domain_country_cache.json"
DBIP_URL = "https://download.db-ip.com/free/dbip-country-lite-2026-05.csv.gz"
DBIP_LOCAL = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/dbip_country.csv.gz"

CCTLD_MAP = {
    "ac": ("AC", "Ascension Island"), "ad": ("AD", "Andorra"), "ae": ("AE", "United Arab Emirates"),
    "af": ("AF", "Afghanistan"), "ag": ("AG", "Antigua and Barbuda"), "ai": ("AI", "Anguilla"),
    "al": ("AL", "Albania"), "am": ("AM", "Armenia"), "ao": ("AO", "Angola"),
    "aq": ("AQ", "Antarctica"), "ar": ("AR", "Argentina"), "as": ("AS", "American Samoa"),
    "at": ("AT", "Austria"), "au": ("AU", "Australia"), "aw": ("AW", "Aruba"),
    "ax": ("AX", "Aland Islands"), "az": ("AZ", "Azerbaijan"), "ba": ("BA", "Bosnia and Herzegovina"),
    "bb": ("BB", "Barbados"), "bd": ("BD", "Bangladesh"), "be": ("BE", "Belgium"),
    "bf": ("BF", "Burkina Faso"), "bg": ("BG", "Bulgaria"), "bh": ("BH", "Bahrain"),
    "bi": ("BI", "Burundi"), "bj": ("BJ", "Benin"), "bm": ("BM", "Bermuda"),
    "bn": ("BN", "Brunei"), "bo": ("BO", "Bolivia"), "bq": ("BQ", "Caribbean Netherlands"),
    "br": ("BR", "Brazil"), "bs": ("BS", "Bahamas"), "bt": ("BT", "Bhutan"),
    "bw": ("BW", "Botswana"), "by": ("BY", "Belarus"), "bz": ("BZ", "Belize"),
    "ca": ("CA", "Canada"), "cc": ("CC", "Cocos Islands"), "cd": ("CD", "DR Congo"),
    "cf": ("CF", "Central African Republic"), "cg": ("CG", "Republic of the Congo"),
    "ch": ("CH", "Switzerland"), "ci": ("CI", "Ivory Coast"), "ck": ("CK", "Cook Islands"),
    "cl": ("CL", "Chile"), "cm": ("CM", "Cameroon"), "cn": ("CN", "China"),
    "co": ("CO", "Colombia"), "cr": ("CR", "Costa Rica"), "cu": ("CU", "Cuba"),
    "cv": ("CV", "Cape Verde"), "cw": ("CW", "Curacao"), "cy": ("CY", "Cyprus"),
    "cz": ("CZ", "Czech Republic"), "de": ("DE", "Germany"), "dj": ("DJ", "Djibouti"),
    "dk": ("DK", "Denmark"), "dm": ("DM", "Dominica"), "do": ("DO", "Dominican Republic"),
    "dz": ("DZ", "Algeria"), "ec": ("EC", "Ecuador"), "ee": ("EE", "Estonia"),
    "eg": ("EG", "Egypt"), "er": ("ER", "Eritrea"), "es": ("ES", "Spain"),
    "et": ("ET", "Ethiopia"), "eu": ("EU", "European Union"), "fi": ("FI", "Finland"),
    "fj": ("FJ", "Fiji"), "fk": ("FK", "Falkland Islands"), "fm": ("FM", "Micronesia"),
    "fo": ("FO", "Faroe Islands"), "fr": ("FR", "France"), "ga": ("GA", "Gabon"),
    "gb": ("GB", "United Kingdom"), "gd": ("GD", "Grenada"), "ge": ("GE", "Georgia"),
    "gf": ("GF", "French Guiana"), "gg": ("GG", "Guernsey"), "gh": ("GH", "Ghana"),
    "gi": ("GI", "Gibraltar"), "gl": ("GL", "Greenland"), "gm": ("GM", "Gambia"),
    "gn": ("GN", "Guinea"), "gp": ("GP", "Guadeloupe"), "gq": ("GQ", "Equatorial Guinea"),
    "gr": ("GR", "Greece"), "gt": ("GT", "Guatemala"), "gu": ("GU", "Guam"),
    "gw": ("GW", "Guinea-Bissau"), "gy": ("GY", "Guyana"),
    "hk": ("HK", "Hong Kong"), "hn": ("HN", "Honduras"), "hr": ("HR", "Croatia"),
    "ht": ("HT", "Haiti"), "hu": ("HU", "Hungary"), "id": ("ID", "Indonesia"),
    "ie": ("IE", "Ireland"), "il": ("IL", "Israel"), "im": ("IM", "Isle of Man"),
    "in": ("IN", "India"), "io": ("IO", "British Indian Ocean Territory"),
    "iq": ("IQ", "Iraq"), "ir": ("IR", "Iran"), "is": ("IS", "Iceland"),
    "it": ("IT", "Italy"), "je": ("JE", "Jersey"), "jm": ("JM", "Jamaica"),
    "jo": ("JO", "Jordan"), "jp": ("JP", "Japan"), "ke": ("KE", "Kenya"),
    "kg": ("KG", "Kyrgyzstan"), "kh": ("KH", "Cambodia"), "ki": ("KI", "Kiribati"),
    "km": ("KM", "Comoros"), "kn": ("KN", "Saint Kitts and Nevis"),
    "kp": ("KP", "North Korea"), "kr": ("KR", "South Korea"), "kw": ("KW", "Kuwait"),
    "ky": ("KY", "Cayman Islands"), "kz": ("KZ", "Kazakhstan"), "la": ("LA", "Laos"),
    "lb": ("LB", "Lebanon"), "lc": ("LC", "Saint Lucia"), "li": ("LI", "Liechtenstein"),
    "lk": ("LK", "Sri Lanka"), "lr": ("LR", "Liberia"), "ls": ("LS", "Lesotho"),
    "lt": ("LT", "Lithuania"), "lu": ("LU", "Luxembourg"), "lv": ("LV", "Latvia"),
    "ly": ("LY", "Libya"), "ma": ("MA", "Morocco"), "mc": ("MC", "Monaco"),
    "md": ("MD", "Moldova"), "me": ("ME", "Montenegro"), "mg": ("MG", "Madagascar"),
    "mh": ("MH", "Marshall Islands"), "mk": ("MK", "North Macedonia"),
    "ml": ("ML", "Mali"), "mm": ("MM", "Myanmar"), "mn": ("MN", "Mongolia"),
    "mo": ("MO", "Macau"), "mp": ("MP", "Northern Mariana Islands"),
    "mq": ("MQ", "Martinique"), "mr": ("MR", "Mauritania"), "ms": ("MS", "Montserrat"),
    "mt": ("MT", "Malta"), "mu": ("MU", "Mauritius"), "mv": ("MV", "Maldives"),
    "mw": ("MW", "Malawi"), "mx": ("MX", "Mexico"), "my": ("MY", "Malaysia"),
    "mz": ("MZ", "Mozambique"), "na": ("NA", "Namibia"), "nc": ("NC", "New Caledonia"),
    "ne": ("NE", "Niger"), "nf": ("NF", "Norfolk Island"), "ng": ("NG", "Nigeria"),
    "ni": ("NI", "Nicaragua"), "nl": ("NL", "Netherlands"), "no": ("NO", "Norway"),
    "np": ("NP", "Nepal"), "nr": ("NR", "Nauru"), "nu": ("NU", "Niue"),
    "nz": ("NZ", "New Zealand"), "om": ("OM", "Oman"), "pa": ("PA", "Panama"),
    "pe": ("PE", "Peru"), "pf": ("PF", "French Polynesia"), "pg": ("PG", "Papua New Guinea"),
    "ph": ("PH", "Philippines"), "pk": ("PK", "Pakistan"), "pl": ("PL", "Poland"),
    "pm": ("PM", "Saint Pierre and Miquelon"), "pn": ("PN", "Pitcairn Islands"),
    "pr": ("PR", "Puerto Rico"), "ps": ("PS", "Palestine"), "pt": ("PT", "Portugal"),
    "pw": ("PW", "Palau"), "py": ("PY", "Paraguay"), "qa": ("QA", "Qatar"),
    "re": ("RE", "Reunion"), "ro": ("RO", "Romania"), "rs": ("RS", "Serbia"),
    "ru": ("RU", "Russia"), "rw": ("RW", "Rwanda"), "sa": ("SA", "Saudi Arabia"),
    "sb": ("SB", "Solomon Islands"), "sc": ("SC", "Seychelles"), "sd": ("SD", "Sudan"),
    "se": ("SE", "Sweden"), "sg": ("SG", "Singapore"), "sh": ("SH", "Saint Helena"),
    "si": ("SI", "Slovenia"), "sk": ("SK", "Slovakia"), "sl": ("SL", "Sierra Leone"),
    "sm": ("SM", "San Marino"), "sn": ("SN", "Senegal"), "so": ("SO", "Somalia"),
    "sr": ("SR", "Suriname"), "ss": ("SS", "South Sudan"),
    "st": ("ST", "Sao Tome and Principe"), "sv": ("SV", "El Salvador"),
    "sx": ("SX", "Sint Maarten"), "sy": ("SY", "Syria"), "sz": ("SZ", "Eswatini"),
    "tc": ("TC", "Turks and Caicos"), "td": ("TD", "Chad"), "tg": ("TG", "Togo"),
    "th": ("TH", "Thailand"), "tj": ("TJ", "Tajikistan"), "tk": ("TK", "Tokelau"),
    "tl": ("TL", "East Timor"), "tm": ("TM", "Turkmenistan"), "tn": ("TN", "Tunisia"),
    "to": ("TO", "Tonga"), "tr": ("TR", "Turkey"), "tt": ("TT", "Trinidad and Tobago"),
    "tv": ("TV", "Tuvalu"), "tw": ("TW", "Taiwan"), "tz": ("TZ", "Tanzania"),
    "ua": ("UA", "Ukraine"), "ug": ("UG", "Uganda"),
    "uk": ("GB", "United Kingdom"), "us": ("US", "United States"),
    "uy": ("UY", "Uruguay"), "uz": ("UZ", "Uzbekistan"),
    "va": ("VA", "Vatican City"), "vc": ("VC", "Saint Vincent and the Grenadines"),
    "ve": ("VE", "Venezuela"), "vg": ("VG", "British Virgin Islands"),
    "vi": ("VI", "US Virgin Islands"), "vn": ("VN", "Vietnam"),
    "vu": ("VU", "Vanuatu"), "wf": ("WF", "Wallis and Futuna"),
    "ws": ("WS", "Samoa"), "ye": ("YE", "Yemen"), "yt": ("YT", "Mayotte"),
    "za": ("ZA", "South Africa"), "zm": ("ZM", "Zambia"), "zw": ("ZW", "Zimbabwe"),
}

GENERIC_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "int",
    "info", "biz", "name", "pro", "mobi", "travel",
    "asia", "aero", "coop", "jobs", "museum", "tel", "xxx",
    "news", "online", "site", "app", "blog", "shop", "club",
    "media", "agency", "email", "guru", "today", "tech",
    "dev", "io", "me", "ai", "gg",
    "live", "world", "life", "digital", "cloud", "link",
    "icu", "xyz", "top", "work", "ltd", "global", "international",
}


def download_dbip():
    """Download DB-IP country lite database if not cached."""
    if os.path.exists(DBIP_LOCAL):
        print(f"  Using cached: {DBIP_LOCAL}")
        return DBIP_LOCAL

    print(f"  Downloading {DBIP_URL} ...")
    resp = requests.get(DBIP_URL, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(DBIP_LOCAL, "wb") as f:
        downloaded = 0
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                print(f"\r  Progress: {downloaded * 100 // total}%", end="", flush=True)
    print(f"\n  Saved to {DBIP_LOCAL}")
    return DBIP_LOCAL


def load_dbip_country(db_path: str) -> dict[int, str]:
    """
    Parse DB-IP CSV: start_ip, end_ip, country_code
    Returns a sorted list of (start_int, end_int, country_code)
    with a lookup function via binary search.
    """
    print("  Parsing IP-to-country database ...")
    ranges = []  # list of (start_int, end_int, country_code)

    opener = gzip.open if db_path.endswith(".gz") else open
    with opener(db_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue
            start_str, end_str, country = row[0], row[1], row[2]
            try:
                start = int(ipaddress.IPv4Address(start_str))
                end = int(ipaddress.IPv4Address(end_str))
                ranges.append((start, end, country))
            except (ValueError, ipaddress.AddressValueError):
                continue

    ranges.sort(key=lambda x: x[0])
    print(f"  Loaded {len(ranges)} IP ranges")
    return ranges


def ip_to_country(ip_str: str, ranges: list) -> tuple[str, str] | None:
    """Binary search IP in sorted ranges. Returns (country_code, country_name)."""
    try:
        ip_int = int(ipaddress.IPv4Address(ip_str))
    except (ValueError, ipaddress.AddressValueError):
        return None

    # Binary search on start_int
    lo, hi = 0, len(ranges) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        start, end, country = ranges[mid]
        if ip_int < start:
            hi = mid - 1
        elif ip_int > end:
            lo = mid + 1
        else:
            return (country, country)  # DB-IP lite only has country code
    return None


def get_tld(domain: str) -> str:
    parts = domain.strip().lower().rsplit(".", 1)
    return parts[-1] if len(parts) == 2 else ""


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def resolve_domain(domain: str, timeout: float = 3.0) -> str | None:
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None


def resolve_domains_parallel(domains: list[str], max_workers: int = 60) -> dict[str, str | None]:
    results = {}
    done = 0
    total = len(domains)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(resolve_domain, d): d for d in domains}
        for fut in as_completed(futures):
            domain = futures[fut]
            try:
                results[domain] = fut.result()
            except Exception:
                results[domain] = None
            done += 1
            if done % 500 == 0:
                print(f"  DNS: {done}/{total}")
    return results


def main():
    print("=" * 60)
    print("Step 1: Download/load local GeoIP database (DB-IP lite)")
    print("=" * 60)
    db_path = download_dbip()
    ip_ranges = load_dbip_country(db_path)

    print("\n" + "=" * 60)
    print("Step 2: Extract unique domains from CSV")
    print("=" * 60)

    domains_set = set()
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row.get("domain", "").strip().lower()
            if domain:
                domains_set.add(domain)

    all_domains = sorted(domains_set)
    print(f"  Total unique domains: {len(all_domains)}")

    # ── Phase 1: ccTLD mapping ────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 3: ccTLD direct mapping")
    print("=" * 60)

    cache = load_cache()
    domain_map: dict[str, tuple[str, str, str]] = {}
    generic_domains = []

    for domain in all_domains:
        if domain in cache:
            domain_map[domain] = cache[domain]
            continue
        tld = get_tld(domain)
        if tld in GENERIC_TLDS:
            generic_domains.append(domain)
        elif tld in CCTLD_MAP:
            code, name = CCTLD_MAP[tld]
            domain_map[domain] = (code, name, "cctld")
        else:
            generic_domains.append(domain)

    print(f"  ccTLD mapped: {len(domain_map)}")
    print(f"  Need GeoIP:   {len(generic_domains)}")

    # ── Phase 2: DNS resolve + local GeoIP lookup ─────────────────
    if generic_domains:
        print("\n" + "=" * 60)
        print("Step 4: DNS resolution for generic-TLD domains")
        print("=" * 60)
        dns_results = resolve_domains_parallel(generic_domains)

        resolved = sum(1 for ip in dns_results.values() if ip)
        print(f"  Resolved: {resolved}/{len(generic_domains)}")

        print("\n" + "=" * 60)
        print("Step 5: IP → Country via local DB lookup")
        print("=" * 60)
        ip_to_domains: dict[str, list[str]] = {}
        for domain, ip in dns_results.items():
            if ip:
                ip_to_domains.setdefault(ip, []).append(domain)

        unique_ips = list(ip_to_domains.keys())
        print(f"  {len(unique_ips)} unique IPs to look up ...")

        geoip_count = 0
        for i, ip in enumerate(unique_ips):
            result = ip_to_country(ip, ip_ranges)
            if result:
                cc, cn = result
                for domain in ip_to_domains[ip]:
                    domain_map[domain] = (cc, cn, "geoip")
                geoip_count += 1
            else:
                for domain in ip_to_domains[ip]:
                    domain_map[domain] = ("??", "Unknown", "geoip_unmatched")

        unresolved = sum(1 for d in generic_domains if dns_results.get(d) is None)
        for domain in generic_domains:
            if domain not in domain_map:
                domain_map[domain] = ("??", "Unknown", "unresolved")

        print(f"  GeoIP matched: {geoip_count} IPs")
        print(f"  DNS unresolved domains: {unresolved}")

    # ── Save mapping ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 6: Save domain→country mapping")
    print("=" * 60)

    with open(OUTPUT_MAP, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["domain", "country_code", "country_name", "method"])
        for domain in sorted(domain_map.keys()):
            code, name, method = domain_map[domain]
            writer.writerow([domain, code, name, method])

    print(f"  Saved to {OUTPUT_MAP}")

    # ── Statistics ────────────────────────────────────────────────
    from collections import Counter
    country_counts = Counter(
        domain_map[d][1] for d in domain_map if domain_map[d][0] != "??"
    )
    method_counts = Counter(domain_map[d][2] for d in domain_map)

    print(f"\n  Total domains: {len(domain_map)}")
    print(f"  - ccTLD:       {method_counts.get('cctld', 0)}")
    print(f"  - GeoIP:       {method_counts.get('geoip', 0)}")
    print(f"  - GeoIP fail:  {method_counts.get('geoip_unmatched', 0)}")
    print(f"  - Unresolved:  {method_counts.get('unresolved', 0)}")
    print(f"\n  Top 15 countries:")
    for country, count in country_counts.most_common(15):
        print(f"    {country}: {count}")

    # ── Update cache ──────────────────────────────────────────────
    for domain, val in domain_map.items():
        if domain not in cache:
            cache[domain] = val
    save_cache(cache)

    # ── Apply to full CSV ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 7: Apply mapping to full CSV (2.17M rows)")
    print("=" * 60)

    with open(CSV_PATH, "r", encoding="utf-8-sig") as fin:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames + ["url_country_code", "url_country_name"]

        with open(OUTPUT_ENRICHED, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()

            for i, row in enumerate(reader, 1):
                domain = row.get("domain", "").strip().lower()
                if domain in domain_map:
                    cc, cn, _ = domain_map[domain]
                    row["url_country_code"] = cc
                    row["url_country_name"] = cn
                else:
                    row["url_country_code"] = "??"
                    row["url_country_name"] = "Unknown"
                writer.writerow(row)

                if i % 200000 == 0:
                    print(f"  {i:,} / 2,169,215 rows ...")

    print(f"  Done! Enriched CSV: {OUTPUT_ENRICHED}")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Domain → Country mapping for all_events_url_pool.csv
Phase 1: ccTLD direct mapping (instant, ~22% of domains)
Phase 2: DNS resolve + ip-api.com batch for generic TLDs (.com, .org, .net, etc.)
Output: domain_country.csv (domain, country_code, country_name, method)
"""

import csv
import json
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

csv.field_size_limit(sys.maxsize)

CSV_PATH = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/all_events_url_pool.csv"
OUTPUT_MAP = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/domain_country.csv"
OUTPUT_ENRICHED = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/all_events_url_pool_with_country.csv"
CACHE_PATH = "/data_ssd2/zbh/Narrrative/all_3/data/gdelt_events/domain_country_cache.json"

# ── Comprehensive ccTLD → Country mapping ──────────────────────────
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

# Generic TLDs that need IP-based geolocation
GENERIC_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "int",
    "info", "biz", "name", "pro", "mobi", "travel",
    "asia", "aero", "coop", "jobs", "museum", "tel", "xxx",
    "news", "online", "site", "app", "blog", "shop", "club",
    "media", "agency", "email", "guru", "today", "tech",
    "dev", "io",  # .io = British Indian Ocean Territory but used as generic
    "me",         # .me = Montenegro but often generic
    "ai",         # .ai = Anguilla but often AI companies
    "gg",         # .gg = Guernsey but often gaming
    "live", "world", "life", "digital", "cloud", "link",
    "icu", "xyz", "top", "work", "ltd", "global", "international",
}


def get_tld(domain: str) -> str:
    """Extract the top-level domain (last part) from a domain."""
    domain = domain.strip().lower()
    parts = domain.rsplit(".", 1)
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
    """Resolve domain to IP. Returns None on failure."""
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None


def resolve_domains_parallel(domains: list[str], max_workers: int = 50) -> dict[str, str | None]:
    """Resolve many domains to IPs concurrently."""
    results = {}
    done = 0
    total = len(domains)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(resolve_domain, d): d for d in domains}
        for fut in as_completed(futures):
            domain = futures[fut]
            try:
                ip = fut.result()
                results[domain] = ip
            except Exception:
                results[domain] = None
            done += 1
            if done % 500 == 0:
                print(f"  DNS: {done}/{total}")
    return results


def batch_ip_lookup(ips: list[str]) -> list[dict]:
    """Batch query ip-api.com for up to 100 IPs."""
    url = "http://ip-api.com/batch"
    resp = requests.post(url, json=ips, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    return []


def ip_country_lookup(domains_with_ips: dict[str, str | None]) -> dict[str, tuple[str, str]]:
    """
    Given {domain: ip_or_None}, return {domain: (country_code, country_name)}.
    Uses ip-api.com batch endpoint (100 IPs per request, rate limited to ~40/min).
    """
    # Filter domains that resolved successfully
    ip_to_domains: dict[str, list[str]] = {}
    for domain, ip in domains_with_ips.items():
        if ip:
            ip_to_domains.setdefault(ip, []).append(domain)

    unique_ips = list(ip_to_domains.keys())
    print(f"  {len(unique_ips)} unique IPs to geolocate ({len(domains_with_ips) - len(unique_ips)} duplicate IPs)")

    result: dict[str, tuple[str, str]] = {}
    batch_size = 100
    total_batches = (len(unique_ips) + batch_size - 1) // batch_size

    for i in range(0, len(unique_ips), batch_size):
        batch = unique_ips[i:i + batch_size]
        batch_num = i // batch_size + 1

        # Rate limiting: ip-api free allows ~45 req/min, be conservative
        if i > 0:
            time.sleep(1.5)

        print(f"  GeoIP batch {batch_num}/{total_batches} ({len(batch)} IPs)", end=" ", flush=True)
        try:
            results = batch_ip_lookup(batch)
        except Exception as e:
            print(f"ERROR: {e}, retrying after 5s...")
            time.sleep(5)
            try:
                results = batch_ip_lookup(batch)
            except Exception:
                print("FAILED, skipping batch")
                continue

        success = 0
        for entry in results:
            if entry.get("status") == "success":
                ip = entry["query"]
                cc = entry.get("countryCode", "??")
                cn = entry.get("country", "Unknown")
                for domain in ip_to_domains.get(ip, []):
                    result[domain] = (cc, cn)
                success += 1
        print(f"-> {success} OK")

    return result


def main():
    print("=" * 60)
    print("Step 1: Extract unique domains from CSV")
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
    print("Step 2: ccTLD direct mapping")
    print("=" * 60)

    cache = load_cache()
    domain_map: dict[str, tuple[str, str, str]] = {}  # domain -> (country_code, country, method)
    generic_domains = []

    for domain in all_domains:
        if domain in cache:
            code, name, method = cache[domain]
            domain_map[domain] = (code, name, method)
            continue

        tld = get_tld(domain)
        if tld in GENERIC_TLDS:
            generic_domains.append(domain)
        elif tld in CCTLD_MAP:
            code, name = CCTLD_MAP[tld]
            domain_map[domain] = (code, name, "cctld")
        else:
            # Unknown TLD — treat as needing IP lookup
            generic_domains.append(domain)

    print(f"  ccTLD mapped: {len(domain_map)}")
    print(f"  Need GeoIP:   {len(generic_domains)}")

    # ── Phase 2: DNS resolve + IP geolocation ─────────────────────
    if generic_domains:
        print("\n" + "=" * 60)
        print("Step 3: DNS resolution for generic-TLD domains")
        print("=" * 60)
        dns_results = resolve_domains_parallel(generic_domains)
        resolved = sum(1 for ip in dns_results.values() if ip)
        print(f"  Resolved: {resolved}/{len(generic_domains)}")

        print("\n" + "=" * 60)
        print("Step 4: IP → Country via ip-api.com batch")
        print("=" * 60)
        ip_results = ip_country_lookup(dns_results)

        for domain in generic_domains:
            if domain in ip_results:
                cc, cn = ip_results[domain]
                domain_map[domain] = (cc, cn, "geoip")
            else:
                domain_map[domain] = ("??", "Unknown", "unresolved")

        print(f"  GeoIP resolved: {len(ip_results)}")

    # ── Save domain→country mapping ───────────────────────────────
    print("\n" + "=" * 60)
    print("Step 5: Save domain→country mapping")
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

    print(f"\n  Total domains mapped: {len(domain_map)}")
    print(f"  - By ccTLD:   {method_counts.get('cctld', 0)}")
    print(f"  - By GeoIP:   {method_counts.get('geoip', 0)}")
    print(f"  - Unresolved: {method_counts.get('unresolved', 0)}")
    print(f"\n  Top 15 countries:")
    for country, count in country_counts.most_common(15):
        print(f"    {country}: {count}")

    # ── Update cache ──────────────────────────────────────────────
    for domain, (code, name, method) in domain_map.items():
        if domain not in cache:
            cache[domain] = (code, name, method)
    save_cache(cache)

    # ── Apply to full CSV ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 6: Apply mapping to full CSV (2.17M rows)")
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
                    print(f"  {i:,} rows...")

    print(f"  Done! Saved to {OUTPUT_ENRICHED}")
    print("=" * 60)


if __name__ == "__main__":
    main()

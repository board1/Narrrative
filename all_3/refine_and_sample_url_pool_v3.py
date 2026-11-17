"""
基于 refine_and_sample_url_pool_v2.py 的 pipeline，增加:
1. 从 domain_country.csv 补充缺失的 IP/国家信息
2. 用真实 country_code 做 country→region 映射，替代纯 domain 规则
3. 保留 DOMAIN_REGION_RULES 作为优先级最高的 override
"""
import re
import csv
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse

# 增大 CSV field size limit
csv.field_size_limit(sys.maxsize)

import pandas as pd


# =========================
# 默认路径
# =========================
DEFAULT_INPUT = "data/gdelt_events/all_events_url_pool_with_country.csv"
DEFAULT_DOMAIN_COUNTRY = "data/gdelt_events/domain_country.csv"
DEFAULT_OUT_DIR = "data/gdelt_events_v3"


# =========================
# 采样参数
# =========================
DEFAULT_TARGET_PER_EVENT_REGION = 600
DEFAULT_MAX_PER_DOMAIN_EVENT_REGION = 80
DEFAULT_MIN_REGION_ROWS = 80
DEFAULT_SEED = 42


# =========================
# 每个事件保留的核心国家/地区
# =========================
EVENT_TARGET_REGIONS = {
    "gaza_conflict_2023": [
        "US", "Europe", "MiddleEast", "Israel",
        "SouthAsia", "China", "Russia", "EastAsia"
    ],
    "russia_ukraine_invasion_2022": [
        "US", "Europe", "Russia", "Ukraine",
        "China", "SouthAsia", "MiddleEast", "EastAsia"
    ],
    "us_iran_israel_2026": [
        "US", "Europe", "MiddleEast", "Israel",
        "Iran", "China", "Russia", "SouthAsia", "EastAsia"
    ],
    "us_china_trade_war_2018": [
        "US", "China", "Europe", "SouthAsia",
        "EastAsia", "Russia", "MiddleEast", "Global"
    ],
    "trump_liberation_day_tariffs_2025": [
        "US", "China", "Europe", "SouthAsia",
        "EastAsia", "Russia", "MiddleEast", "Global"
    ],
    "covid_origin_investigation_2021": [
        "US", "China", "Europe", "EastAsia",
        "SouthAsia", "Russia", "MiddleEast", "Global"
    ],
    "cop28_dubai_2023": [
        "US", "China", "Europe", "MiddleEast",
        "SouthAsia", "EastAsia", "Russia", "Global"
    ],
}


# =========================
# 通用 / 被滥用的 TLD（没有地理含义，默认视为美国媒体）
# =========================
GENERIC_TLDS = {
    "com", "org", "net", "edu", "gov", "mil", "us", "int",
    "news", "media", "info", "biz", "pro", "center", "world",
    # 被 FM 电台 / 视频网站 / 科技公司滥用的 ccTLD
    "tv", "fm", "io", "co", "to", "ws", "nu", "tk", "cc", "ai",
    "sh", "me", "ly", "so", "st", "ac",
}

# =========================
# TLD -> region 映射（仅地理明确的 ccTLD）
# =========================
TLD_TO_REGION = {
    # Europe
    "uk": "Europe", "de": "Europe", "fr": "Europe", "it": "Europe",
    "es": "Europe", "nl": "Europe", "ie": "Europe", "be": "Europe",
    "at": "Europe", "ch": "Europe", "se": "Europe", "no": "Europe",
    "dk": "Europe", "fi": "Europe", "pl": "Europe", "cz": "Europe",
    "pt": "Europe", "gr": "Europe", "hu": "Europe", "ro": "Europe",
    "bg": "Europe", "hr": "Europe", "sk": "Europe", "si": "Europe",
    "lt": "Europe", "lv": "Europe", "ee": "Europe", "lu": "Europe",
    "mt": "Europe", "cy": "Europe", "is": "Europe", "eu": "Europe",
    "rs": "Europe", "ba": "Europe", "mk": "Europe", "al": "Europe",
    "md": "Europe", "gi": "Europe", "im": "Europe", "gg": "Europe",
    "je": "Europe", "fo": "Europe", "ax": "Europe", "li": "Europe",
    "mc": "Europe", "ad": "Europe", "sm": "Europe", "va": "Europe",
    # Russia / CIS
    "ru": "Russia", "ua": "Ukraine",
    "kz": "Russia", "kg": "Russia", "uz": "Russia", "tm": "Russia",
    "tj": "Russia", "az": "Russia", "am": "Russia", "ge": "Russia",
    "by": "Russia",
    # China / East Asia
    "cn": "China",
    "jp": "EastAsia", "kr": "EastAsia", "sg": "EastAsia",
    "hk": "EastAsia", "tw": "EastAsia", "mo": "EastAsia",
    "mn": "EastAsia", "kp": "EastAsia",
    "kh": "EastAsia", "la": "EastAsia", "th": "EastAsia",
    "vn": "EastAsia", "ph": "EastAsia", "my": "EastAsia",
    "id": "EastAsia", "bn": "EastAsia", "tl": "EastAsia", "mm": "EastAsia",
    # South Asia
    "in": "SouthAsia", "pk": "SouthAsia", "bd": "SouthAsia",
    "lk": "SouthAsia", "np": "SouthAsia", "mv": "SouthAsia",
    "bt": "SouthAsia",
    # Israel / Iran
    "il": "Israel", "ir": "Iran",
    # Middle East
    "sa": "MiddleEast", "ae": "MiddleEast", "qa": "MiddleEast",
    "kw": "MiddleEast", "bh": "MiddleEast", "om": "MiddleEast",
    "tr": "MiddleEast", "eg": "MiddleEast", "jo": "MiddleEast",
    "lb": "MiddleEast", "sy": "MiddleEast", "iq": "MiddleEast",
    "ye": "MiddleEast", "ps": "MiddleEast",
    "ly": "MiddleEast", "dz": "MiddleEast", "ma": "MiddleEast",
    "tn": "MiddleEast", "sd": "MiddleEast", "so": "MiddleEast",
    "mr": "MiddleEast",
    # Oceania
    "au": "EastAsia", "nz": "EastAsia",
    # Africa
    "za": "SouthAsia", "ng": "SouthAsia", "ke": "SouthAsia",
    "et": "SouthAsia", "tz": "SouthAsia", "gh": "SouthAsia",
    "ug": "SouthAsia", "zm": "SouthAsia", "zw": "SouthAsia",
    # Americas (non-US)
    "ca": "US", "mx": "US",
    "br": "US", "ar": "US", "cl": "US", "co": "US", "pe": "US",
    "ve": "US", "ec": "US", "bo": "US", "py": "US", "uy": "US",
}

# =========================
# country_code -> region 映射（兜底）
# =========================
COUNTRY_CODE_TO_REGION = {
    # US
    "US": "US",

    # Europe (EU + EEA + UK + 瑞士等)
    "GB": "Europe", "UK": "Europe",
    "DE": "Europe", "FR": "Europe", "IT": "Europe", "ES": "Europe",
    "NL": "Europe", "BE": "Europe", "AT": "Europe", "CH": "Europe",
    "SE": "Europe", "NO": "Europe", "DK": "Europe", "FI": "Europe",
    "PL": "Europe", "CZ": "Europe", "PT": "Europe", "GR": "Europe",
    "HU": "Europe", "RO": "Europe", "BG": "Europe", "HR": "Europe",
    "SK": "Europe", "SI": "Europe", "LT": "Europe", "LV": "Europe",
    "EE": "Europe", "LU": "Europe", "MT": "Europe", "CY": "Europe",
    "IS": "Europe", "IE": "Europe",
    "FO": "Europe", "GI": "Europe", "IM": "Europe", "GG": "Europe",
    "JE": "Europe", "MC": "Europe", "LI": "Europe", "AD": "Europe",
    "SM": "Europe", "VA": "Europe", "RS": "Europe", "BA": "Europe",
    "MK": "Europe", "AL": "Europe", "MD": "Europe", "EU": "Europe",
    "AX": "Europe", "SJ": "Europe",

    # Russia
    "RU": "Russia",

    # Ukraine
    "UA": "Ukraine",

    # China
    "CN": "China",

    # Israel
    "IL": "Israel",

    # Iran
    "IR": "Iran",

    # South Asia
    "IN": "SouthAsia", "PK": "SouthAsia", "BD": "SouthAsia",
    "LK": "SouthAsia", "NP": "SouthAsia", "MV": "SouthAsia",
    "BT": "SouthAsia",

    # East Asia / Southeast Asia
    "JP": "EastAsia", "KR": "EastAsia", "SG": "EastAsia",
    "HK": "EastAsia", "TW": "EastAsia", "MN": "EastAsia",
    "KH": "EastAsia", "LA": "EastAsia", "TH": "EastAsia",
    "VN": "EastAsia", "PH": "EastAsia", "MY": "EastAsia",
    "ID": "EastAsia", "BN": "EastAsia", "TL": "EastAsia",
    "MO": "EastAsia", "MM": "EastAsia",
    "KP": "EastAsia",

    # Middle East / North Africa
    "SA": "MiddleEast", "AE": "MiddleEast", "QA": "MiddleEast",
    "KW": "MiddleEast", "BH": "MiddleEast", "OM": "MiddleEast",
    "TR": "MiddleEast", "EG": "MiddleEast", "JO": "MiddleEast",
    "LB": "MiddleEast", "SY": "MiddleEast", "IQ": "MiddleEast",
    "YE": "MiddleEast", "PS": "MiddleEast", "LY": "MiddleEast",
    "DZ": "MiddleEast", "MA": "MiddleEast", "TN": "MiddleEast",
    "SD": "MiddleEast", "SO": "MiddleEast", "MR": "MiddleEast",

    # Caucasus / Central Asia -> 归入 Russia 或 MiddleEast
    "KZ": "Russia", "KG": "Russia", "UZ": "Russia", "TM": "Russia",
    "TJ": "Russia", "AZ": "Russia", "AM": "Russia", "GE": "Russia",

    # Oceania
    "AU": "EastAsia", "NZ": "EastAsia",
    "FJ": "EastAsia", "PG": "EastAsia", "WS": "EastAsia",
    "TO": "EastAsia", "VU": "EastAsia", "FM": "EastAsia",
    "NU": "EastAsia", "TV": "EastAsia", "TK": "EastAsia",

    # North America (non-US)
    "CA": "US", "MX": "US", "BM": "US",

    # Latin America / Caribbean
    "AR": "US", "BR": "US", "CL": "US", "CO": "US", "PE": "US",
    "VE": "US", "EC": "US", "BO": "US", "PY": "US", "UY": "US",
    "GY": "US", "SR": "US", "GF": "US",
    "CR": "US", "PA": "US", "NI": "US", "GT": "US", "HN": "US",
    "SV": "US", "BZ": "US", "HT": "US", "DO": "US", "CU": "US",
    "JM": "US", "TT": "US", "BB": "US", "BS": "US", "KY": "US",
    "GD": "US", "DM": "US", "VC": "US", "LC": "US", "KN": "US",
    "AG": "US", "CW": "US", "SX": "US", "AW": "US",
    "MS": "US", "VG": "US", "SH": "US",

    # Africa (sub-Saharan) -> 根据事件可能归入 Global
    "ZA": "SouthAsia", "NG": "SouthAsia", "KE": "SouthAsia",
    "ET": "SouthAsia", "TZ": "SouthAsia", "GH": "SouthAsia",
    "UG": "SouthAsia", "ZM": "SouthAsia", "ZW": "SouthAsia",
    "BW": "SouthAsia", "NA": "SouthAsia", "MU": "SouthAsia",
    "RW": "SouthAsia", "MW": "SouthAsia", "GM": "SouthAsia",
    "LS": "SouthAsia", "SZ": "SouthAsia", "CV": "SouthAsia",
    "ST": "SouthAsia", "SC": "SouthAsia", "AO": "SouthAsia",
    "CM": "SouthAsia", "CG": "SouthAsia", "CI": "SouthAsia",
    "BJ": "SouthAsia", "BF": "SouthAsia", "BI": "SouthAsia",
    "CD": "SouthAsia", "CF": "SouthAsia", "TD": "SouthAsia",
    "DJ": "SouthAsia", "ER": "SouthAsia", "GA": "SouthAsia",
    "GN": "SouthAsia", "GW": "SouthAsia", "GQ": "SouthAsia",
    "KM": "SouthAsia", "LR": "SouthAsia", "MG": "SouthAsia",
    "ML": "SouthAsia", "MZ": "SouthAsia", "NE": "SouthAsia",
    "RE": "SouthAsia", "SL": "SouthAsia", "SN": "SouthAsia",
    "SS": "SouthAsia", "TG": "SouthAsia",
    "??": "Unknown", "ZZ": "Unknown",
}

# 保留原始 DOMAIN_REGION_RULES 作为最高优先级的 override
DOMAIN_REGION_RULES = {
    # Global / wire
    "reuters.com": "Global",
    "apnews.com": "Global",
    "afp.com": "Global",

    # US
    "cnn.com": "US",
    "foxnews.com": "US",
    "nytimes.com": "US",
    "washingtonpost.com": "US",
    "wsj.com": "US",
    "usatoday.com": "US",
    "nbcnews.com": "US",
    "abcnews.go.com": "US",
    "cbsnews.com": "US",
    "npr.org": "US",
    "bloomberg.com": "US",
    "politico.com": "US",
    "thehill.com": "US",
    "time.com": "US",
    "newsweek.com": "US",
    "latimes.com": "US",
    "chicagotribune.com": "US",
    "nypost.com": "US",
    "axios.com": "US",
    "voanews.com": "US",
    "foreignpolicy.com": "US",

    # Europe
    "bbc.com": "Europe",
    "bbc.co.uk": "Europe",
    "theguardian.com": "Europe",
    "independent.co.uk": "Europe",
    "telegraph.co.uk": "Europe",
    "dailymail.co.uk": "Europe",
    "ft.com": "Europe",
    "dw.com": "Europe",
    "france24.com": "Europe",
    "euronews.com": "Europe",
    "lemonde.fr": "Europe",
    "spiegel.de": "Europe",
    "politico.eu": "Europe",
    "sky.com": "Europe",
    "skynews.com": "Europe",
    "standard.co.uk": "Europe",
    "express.co.uk": "Europe",
    "mirror.co.uk": "Europe",
    "gbnews.com": "Europe",
    "rte.ie": "Europe",
    "irishtimes.com": "Europe",
    "ansa.it": "Europe",
    "elpais.com": "Europe",
    "thetimes.com": "Europe",
    "thenational.scot": "Europe",
    "heraldscotland.com": "Europe",
    "irishnews.com": "Europe",
    "novinite.com": "Europe",
    "hellenicshippingnews.com": "Europe",
    "impartialreporter.com": "Europe",
    "bicesteradvertiser.net": "Europe",
    "dunfermlinepress.com": "Europe",
    "peeblesshirenews.com": "Europe",
    "irvinetimes.com": "Europe",
    "eastlothiancourier.com": "Europe",
    "bordertelegraph.com": "Europe",

    # Israel
    "timesofisrael.com": "Israel",
    "jpost.com": "Israel",
    "haaretz.com": "Israel",
    "ynetnews.com": "Israel",
    "israelhayom.com": "Israel",
    "i24news.tv": "Israel",
    "kan.org.il": "Israel",
    "israelnationalnews.com": "Israel",
    "algemeiner.com": "Israel",

    # Iran
    "tehrantimes.com": "Iran",
    "presstv.ir": "Iran",
    "irna.ir": "Iran",
    "tasnimnews.com": "Iran",
    "mehrnews.com": "Iran",
    "farsnews.ir": "Iran",
    "isna.ir": "Iran",

    # Middle East
    "aljazeera.com": "MiddleEast",
    "english.alarabiya.net": "MiddleEast",
    "alarabiya.net": "MiddleEast",
    "arabnews.com": "MiddleEast",
    "thenationalnews.com": "MiddleEast",
    "middleeasteye.net": "MiddleEast",
    "dailysabah.com": "MiddleEast",
    "trtworld.com": "MiddleEast",
    "aa.com.tr": "MiddleEast",
    "gulfnews.com": "MiddleEast",
    "khaleejtimes.com": "MiddleEast",
    "dohanews.co": "MiddleEast",
    "jordantimes.com": "MiddleEast",
    "naharnet.com": "MiddleEast",
    "lorientlejour.com": "MiddleEast",
    "kuwaittimes.com": "MiddleEast",
    "aawsat.com": "MiddleEast",
    "zawya.com": "MiddleEast",
    "el-balad.com": "MiddleEast",
    "thepeninsulaqatar.com": "MiddleEast",
    "gdnonline.com": "MiddleEast",

    # South Asia
    "indiatimes.com": "SouthAsia",
    "timesofindia.indiatimes.com": "SouthAsia",
    "hindustantimes.com": "SouthAsia",
    "thehindu.com": "SouthAsia",
    "indianexpress.com": "SouthAsia",
    "ndtv.com": "SouthAsia",
    "firstpost.com": "SouthAsia",
    "news18.com": "SouthAsia",
    "republicworld.com": "SouthAsia",
    "wionews.com": "SouthAsia",
    "thequint.com": "SouthAsia",
    "opindia.com": "SouthAsia",
    "deccanherald.com": "SouthAsia",
    "oneindia.com": "SouthAsia",
    "dawn.com": "SouthAsia",
    "tribune.com.pk": "SouthAsia",
    "geo.tv": "SouthAsia",
    "thenews.com.pk": "SouthAsia",
    "bdnews24.com": "SouthAsia",
    "thedailystar.net": "SouthAsia",
    "prothomalo.com": "SouthAsia",
    "telegraphindia.com": "SouthAsia",
    "india.com": "SouthAsia",
    "moneycontrol.com": "SouthAsia",
    "prokerala.com": "SouthAsia",
    "thehindubusinessline.com": "SouthAsia",
    "deccanchronicle.com": "SouthAsia",
    "indiatvnews.com": "SouthAsia",
    "rediff.com": "SouthAsia",
    "thefrontierpost.com": "SouthAsia",
    "indiagazette.com": "SouthAsia",
    "channelstv.com": "SouthAsia",
    "punchng.com": "SouthAsia",

    # Russia / Ukraine
    "tass.com": "Russia",
    "rt.com": "Russia",
    "sputnikglobe.com": "Russia",
    "sputniknews.com": "Russia",
    "interfax.com": "Russia",
    "pravda.com.ua": "Ukraine",
    "kyivindependent.com": "Ukraine",
    "kyivpost.com": "Ukraine",
    "ukrinform.net": "Ukraine",

    # China / East Asia
    "chinadaily.com.cn": "China",
    "globaltimes.cn": "China",
    "xinhuanet.com": "China",
    "cgtn.com": "China",
    "people.com.cn": "China",
    "scmp.com": "EastAsia",
    "japantimes.co.jp": "EastAsia",
    "asahi.com": "EastAsia",
    "koreaherald.com": "EastAsia",
    "koreatimes.co.kr": "EastAsia",
    "straitstimes.com": "EastAsia",
    "inquirer.net": "EastAsia",
    "philstar.com": "EastAsia",
    "channelnewsasia.com": "EastAsia",
    "freemalaysiatoday.com": "EastAsia",
    "manilatimes.net": "EastAsia",
}


# =========================
# 低质量/聚合/广告/金融行情类站点
# =========================
BAD_DOMAIN_KEYWORDS = [
    # 搜索引擎 / 门户 / 聚合
    "yahoo.",
    "aol.",
    "msn.",
    "bing.",
    "google.",
    "apple.news",
    "flipboard.",
    "newsbreak.",
    "ground.news",

    # 通讯社稿 / PR 分发
    "prnewswire.",
    "globenewswire.",
    "businesswire.",
    "accesswire.",
    "einpresswire.",
    "newsfilecorp.",
    "openpr.",
    "einnews.",
    "pr-inside.com",
    "lelezard.com",

    # 金融行情 / 投资类
    "marketscreener.",
    "streetinsider.",
    "finanznachrichten.",
    "tmcnet.",
    "seekingalpha.",
    "benzinga.",
    "zacks.",
    "morningstar.",
    "marketwatch.",
    "investing.com",
    "nasdaq.com",
    "fool.com",
    "tickerreport.com",
    "themarketsdaily.com",
    "4-traders.com",

    # 音视频 / 社交
    "iheart.",
    "radio.",
    "podcast",
    "youtube.",
    "tiktok.",
    "facebook.",
    "twitter.",
    "x.com",
    "instagram.",
    "reddit.",

    # Big News Network 及其马甲（内容农场）
    "bignewsnetwork.",
    "middleeaststar.",
    "arabherald.",
    "menafn.",
    "russiaherald.com",
    "israelherald.com",
    "heraldglobe.com",
    "iranherald.com",
    "iraqsun.com",
    "greekherald.com",
    "europesun.com",
    "kenyastar.com",
    "mexicostar.com",
    "clevelandstar.com",
    "bostonstar.com",
    "pittsburghstar.com",
    "stlouisstar.com",
    "baltimorestar.com",
    "sandiegosun.com",
    "dallassun.com",
    "saltlakecitysun.com",
    "memphissun.com",
    "austinglobe.com",
    "phoenixherald.com",
    "nashvilleherald.com",
    "newyorktelegraph.com",
    "newjerseytelegraph.com",
    "hawaiitelegraph.com",
    "californiatelegraph.com",
    "torontotelegraph.com",
    "tennesseedaily.com",
    "texasguardian.com",
    "floridastatesman.com",
    "albuquerqueeexpress.com",
    "batonrougepost.com",
    "parisguardian.com",
    "dominicanrepublicpost.com",
    "cambodiantimes.com",
    "athens-times.com",
    "britainnews.net",
    "azerbaijannews.net",
    "asiabulletin.com",
    "chinanationalnews.com",
    "calcuttanews.net",
    "indiagazette.com",

    # 其他低质量聚合站
    "miragenews.com",
    "onenewspage.com",
    "hngn.com",
    "itnewsonline.com",
    "econotimes.com",
    "spacewar.com",
    "digitaljournal.com",
    "theusnews.com",
    "naturalnews.com",
    "aceshowbiz.com",
    "comicbook.com",
    "broadwayworld.com",
    "twitchy.com",
    "pjmedia.com",
    "freerepublic.com",
    "rawstory.com",
    "infowars.com",
    "oann.com",
    "naturalnews.com",
]

BAD_URL_PATTERNS = [
    r"/video/",
    r"/videos/",
    r"/podcast",
    r"/live/",
    r"/photos/",
    r"/gallery/",
    r"/slideshow/",
    r"/press-release",
    r"/press_releases",
    r"/sponsored",
    r"/advertorial",
    r"/tag/",
    r"/author/",
]


def normalize_domain(x):
    if pd.isna(x):
        return ""
    x = str(x).strip().lower()
    if x.startswith("http"):
        try:
            x = urlparse(x).netloc.lower()
        except Exception:
            pass
    x = x.replace("www.", "")
    x = x.split("/")[0]
    x = x.split(":")[0]
    return x


def domain_from_url(url):
    try:
        netloc = urlparse(str(url)).netloc.lower()
        return netloc.replace("www.", "").split(":")[0]
    except Exception:
        return ""


def is_bad_domain(domain):
    d = str(domain).lower()
    return any(k in d for k in BAD_DOMAIN_KEYWORDS)


def is_bad_url(url):
    u = str(url).lower()
    return any(re.search(p, u) for p in BAD_URL_PATTERNS)


def load_domain_country_map(domain_country_path):
    """加载 domain_country.csv 作为 domain -> (country_code, country_name) 字典"""
    dm = {}
    with open(domain_country_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = normalize_domain(row.get("domain", ""))
            if d:
                dm[d] = (row.get("country_code", "").strip(),
                         row.get("country_name", "").strip())
    print(f"[Domain country map] Loaded {len(dm)} domain -> country entries")
    return dm


def country_code_to_region(code):
    """国家码 -> region"""
    if not code or pd.isna(code):
        return "Unknown"
    return COUNTRY_CODE_TO_REGION.get(str(code).strip().upper(), "Unknown")


def infer_region_from_domain(domain):
    """从 domain 规则推断 region（兜底用）"""
    d = normalize_domain(domain)
    if not d:
        return "Unknown"

    if d in DOMAIN_REGION_RULES:
        return DOMAIN_REGION_RULES[d]

    for key, region in DOMAIN_REGION_RULES.items():
        if d == key or d.endswith("." + key) or key in d:
            return region

    # 域名后缀兜底
    europe_suffix = (
        ".uk", ".de", ".fr", ".it", ".es", ".nl", ".eu", ".ie", ".be",
        ".at", ".ch", ".se", ".no", ".dk", ".fi", ".pl", ".cz", ".pt"
    )
    if d.endswith(europe_suffix):
        return "Europe"
    if d.endswith(".ir"):
        return "Iran"
    if d.endswith(".il"):
        return "Israel"
    if d.endswith((".in", ".pk", ".bd", ".lk")):
        return "SouthAsia"
    if d.endswith(".ru"):
        return "Russia"
    if d.endswith(".ua"):
        return "Ukraine"
    if d.endswith(".cn"):
        return "China"
    if d.endswith((".jp", ".kr", ".sg", ".hk", ".tw")):
        return "EastAsia"
    if d.endswith((".sa", ".ae", ".qa", ".tr", ".eg", ".jo", ".lb", ".kw", ".bh", ".om")):
        return "MiddleEast"

    return "Unknown"


def extract_tld(domain):
    """提取域名的顶级 TLD"""
    parts = domain.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return ""


def determine_region(row, domain_country_map):
    """
    决定每行的 region，优先级：
    1. DOMAIN_REGION_RULES 硬编码（最高优先）
    2. 地理明确的 ccTLD -> region（如 .uk/.cn/.ru/.in/.ir/.il 等）
    3. 通用 TLD（.com/.org/.net/.tv/.fm 等）-> 默认 US
    4. domain_country.csv 中 cctld 方法的条目
    5. url_country_code（最低优先，CDN 污染严重）
    6. infer_region_from_domain 后缀兜底
    """
    domain_norm = row.get("domain_norm", "")
    tld = extract_tld(domain_norm)

    # 1. DOMAIN_REGION_RULES 硬编码（最高优先）
    if domain_norm in DOMAIN_REGION_RULES:
        return DOMAIN_REGION_RULES[domain_norm]

    # 2. 地理明确的 ccTLD -> region
    if tld and tld not in GENERIC_TLDS and tld in TLD_TO_REGION:
        return TLD_TO_REGION[tld]

    # 3. 通用 TLD -> 默认 US（大量 .com/.org/.net 媒体被 CDN 污染）
    if tld and tld in GENERIC_TLDS:
        return "US"

    # 4. domain_country.csv 中 cctld 方法的条目
    if domain_norm and domain_norm in domain_country_map:
        cc, _ = domain_country_map[domain_norm]
        region = country_code_to_region(cc)
        if region != "Unknown":
            return region

    # 5. url_country_code（最低优先）
    country_code = str(row.get("url_country_code", "")).strip()
    if country_code and country_code not in ("", "nan", "None", "??", "ZZ"):
        region = country_code_to_region(country_code)
        if region != "Unknown":
            return region

    # 6. domain 后缀兜底
    region = infer_region_from_domain(domain_norm)
    if region != "Unknown":
        return region

    # 7. DOMAIN_REGION_RULES fuzzy match（最后手段）
    for key, region in DOMAIN_REGION_RULES.items():
        if domain_norm == key or domain_norm.endswith("." + key) or key in domain_norm:
            return region

    return "Unknown"


def load_and_basic_clean(input_path, domain_country_map):
    print("[Load]", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    print("Raw rows:", len(df))

    if "event_id" not in df.columns:
        raise ValueError("缺少 event_id 列")
    if "url" not in df.columns:
        raise ValueError("缺少 url 列")

    if "domain" not in df.columns:
        df["domain"] = ""

    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"].str.startswith("http", na=False)].copy()

    # 确保 url_country_code / url_country_name 存在
    if "url_country_code" not in df.columns:
        df["url_country_code"] = ""
    if "url_country_name" not in df.columns:
        df["url_country_name"] = ""

    # 归一化 domain
    df["domain_norm"] = df["domain"].apply(normalize_domain)
    missing_domain = df["domain_norm"].eq("")
    df.loc[missing_domain, "domain_norm"] = df.loc[missing_domain, "url"].apply(domain_from_url)

    # 用 domain_country.csv 补充缺失的 country_code
    def fill_country_from_domain(row):
        code = str(row.get("url_country_code", "")).strip()
        if not code or code in ("", "nan", "None", "??", "ZZ"):
            dn = row.get("domain_norm", "")
            if dn and dn in domain_country_map:
                cc, cn = domain_country_map[dn]
                return pd.Series([cc, cn])
        return pd.Series([row.get("url_country_code", ""),
                          row.get("url_country_name", "")])

    missing_before = df["url_country_code"].isin(["", "nan", "None", "??", "ZZ"]).sum()
    if missing_before > 0:
        print(f"Missing country_code before supplement: {missing_before}")
        df[["url_country_code", "url_country_name"]] = df.apply(
            fill_country_from_domain, axis=1
        )
        missing_after = df["url_country_code"].isin(["", "nan", "None", "??", "ZZ"]).sum()
        print(f"Missing country_code after supplement: {missing_after}")

    # 过滤低质量 domain / URL
    df = df[~df["domain_norm"].apply(is_bad_domain)].copy()
    df = df[~df["url"].apply(is_bad_url)].copy()

    df = df.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    # 决定 region
    print("Assigning regions...")
    df["region_from_country"] = df["url_country_code"].apply(country_code_to_region)

    # 用 determine_region 做最终 region 判定
    df["country_group_final"] = df.apply(
        lambda row: determine_region(row, domain_country_map), axis=1
    )

    # 统计
    print("After basic clean:", len(df))
    print("\nRegion distribution:")
    print(df["country_group_final"].value_counts())
    print("\nRegion from country_code distribution:")
    print(df["region_from_country"].value_counts())

    return df


def split_known_unknown(df, out_dir):
    unknown = df[df["country_group_final"].eq("Unknown")].copy()
    known = df[~df["country_group_final"].eq("Unknown")].copy()

    unknown_out = out_dir / "unknown_for_llm_region_v3.csv"

    unknown_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "domain_norm", "url", "url_country_code", "url_country_name",
        "themes", "v2_themes", "locations",
        "v2_locations", "persons", "v2_persons", "organizations",
        "v2_organizations", "all_names", "v2_tone",
        "actor_hits", "event_hits", "total_hits"
    ]
    unknown[[c for c in unknown_cols if c in unknown.columns]].to_csv(
        unknown_out, index=False, encoding="utf-8-sig"
    )

    print("Known rows:", len(known))
    print("Unknown rows:", len(unknown))
    print("Saved unknown for LLM:", unknown_out)

    return known, unknown


def keep_event_target_regions(df):
    kept = []

    for event_id, sub in df.groupby("event_id"):
        targets = EVENT_TARGET_REGIONS.get(event_id)

        if targets is None:
            print(f"[Warning] No target region config for event: {event_id}, keep all known regions.")
            kept.append(sub)
            continue

        before = len(sub)
        sub = sub[sub["country_group_final"].isin(targets)].copy()
        after = len(sub)

        print(f"[Target regions] {event_id}: {before} -> {after}")
        kept.append(sub)

    return pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()


def cap_domain_event_region(df, max_per_domain=80, seed=42):
    parts = []

    for (event_id, region, domain), sub in df.groupby(["event_id", "country_group_final", "domain_norm"]):
        if len(sub) > max_per_domain:
            sub = sub.sample(max_per_domain, random_state=seed)
        parts.append(sub)

    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    print("After domain cap:", len(out))
    return out


def sample_event_region(df, target_per_event_region=600, min_region_rows=80, seed=42):
    samples = []
    low_resource = []

    for (event_id, region), sub in df.groupby(["event_id", "country_group_final"]):
        n = len(sub)

        if n < min_region_rows:
            low_resource.append({
                "event_id": event_id,
                "country_group_final": region,
                "available_rows": n,
                "note": "below_min_region_rows_but_kept"
            })
            take = n
        else:
            take = min(target_per_event_region, n)

        sampled = sub.sample(take, random_state=seed) if n > take else sub.copy()
        samples.append(sampled)

    sample = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame()
    low_df = pd.DataFrame(low_resource)

    print("Sample rows:", len(sample))
    return sample, low_df


def save_stats(df, out_path):
    if df.empty:
        pd.DataFrame().to_csv(out_path, index=False)
        return pd.DataFrame()

    stats = (
        df.groupby(["event_id", "country_group_final"])
        .agg(
            rows=("url", "count"),
            domains=("domain_norm", "nunique")
        )
        .reset_index()
        .sort_values(["event_id", "rows"], ascending=[True, False])
    )
    stats.to_csv(out_path, index=False, encoding="utf-8-sig")
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--domain_country", default=DEFAULT_DOMAIN_COUNTRY)
    parser.add_argument("--out_dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--target_per_event_region", type=int, default=DEFAULT_TARGET_PER_EVENT_REGION)
    parser.add_argument("--max_per_domain_event_region", type=int, default=DEFAULT_MAX_PER_DOMAIN_EVENT_REGION)
    parser.add_argument("--min_region_rows", type=int, default=DEFAULT_MIN_REGION_ROWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_known_refined = out_dir / "known_refined_url_pool.csv"
    out_target_refined = out_dir / "target_region_refined_url_pool.csv"
    out_sample = out_dir / "all_events_crawl_sample_v3.csv"
    out_stats_refined = out_dir / "target_region_refined_stats.csv"
    out_stats_sample = out_dir / "sample_stats_by_event_region_v3.csv"
    out_low = out_dir / "low_resource_event_regions.csv"

    # 1. 加载 domain -> country 映射
    domain_country_map = load_domain_country_map(args.domain_country)

    # 2. 加载并清洗
    df = load_and_basic_clean(args.input, domain_country_map)

    # 3. 分离 known / unknown
    known, unknown = split_known_unknown(df, out_dir)
    known.to_csv(out_known_refined, index=False, encoding="utf-8-sig")
    print("Saved known refined:", out_known_refined)

    # 4. 筛选目标地区
    target_df = keep_event_target_regions(known)

    # 5. Domain 上限
    target_df = cap_domain_event_region(
        target_df,
        max_per_domain=args.max_per_domain_event_region,
        seed=args.seed
    )

    target_df.to_csv(out_target_refined, index=False, encoding="utf-8-sig")
    print("Saved target refined:", out_target_refined)

    stats_refined = save_stats(target_df, out_stats_refined)
    print("\n[Target refined stats]")
    print(stats_refined.head(80))
    print("Saved:", out_stats_refined)

    # 6. 采样
    sample, low_df = sample_event_region(
        target_df,
        target_per_event_region=args.target_per_event_region,
        min_region_rows=args.min_region_rows,
        seed=args.seed
    )

    crawl_cols = [
        "event_id", "event_start", "event_end", "day", "gdelt_timestamp",
        "country_group_final", "region_from_country", "domain_norm", "url",
        "url_country_code", "url_country_name",
        "themes", "v2_themes", "locations", "v2_locations",
        "persons", "v2_persons", "organizations", "v2_organizations",
        "all_names", "v2_tone", "actor_hits", "event_hits", "total_hits"
    ]
    sample = sample[[c for c in crawl_cols if c in sample.columns]].copy()
    sample = sample.drop_duplicates(subset=["event_id", "url"]).reset_index(drop=True)

    sample.to_csv(out_sample, index=False, encoding="utf-8-sig")
    print("Saved crawl sample:", out_sample, "rows=", len(sample))

    stats_sample = save_stats(sample, out_stats_sample)
    print("\n[Sample stats]")
    print(stats_sample.head(100))
    print("Saved:", out_stats_sample)

    low_df.to_csv(out_low, index=False, encoding="utf-8-sig")
    print("Saved low-resource event regions:", out_low)

    print("\nRows by event:")
    print(sample["event_id"].value_counts())

    print("\nRows by region:")
    print(sample["country_group_final"].value_counts())

    print("\nDone.")


if __name__ == "__main__":
    main()

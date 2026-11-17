# scripts/config.py

QUERY = '''
("United States" OR US OR America OR Washington OR Pentagon)
AND
(Iran OR Iranian OR Tehran OR IRGC)
'''

# GDELT DOC API
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# 建议先抓最近 30 天，后面再扩到 90 天
# 注意：GDELT DOC API 的 STARTDATETIME / ENDDATETIME 只能查最近 3 个月
MAX_RECORDS = 50

# 限流相关
REQUEST_SLEEP_SECONDS = 20
HTTP_TIMEOUT = 60
MAX_RETRIES = 5

# 全文抓取
MIN_WORDS = 120

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcademicResearchBot/1.0)"
}
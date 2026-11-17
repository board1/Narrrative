import json
import re
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests
from tqdm import tqdm


# =========================
# 配置
# =========================
INPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_clean_expanded.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_region_inferred_expanded.csv"

VLLM_BASE_URL = "http://127.0.0.1:8125/v1"
MODEL_NAME = "qwen3-4b-2507"

MAX_TEXT_CHARS = 1200
TEMPERATURE = 0.0
MAX_TOKENS = 260
TIMEOUT = 120
SAVE_EVERY = 20

ALLOWED_REGIONS = {
    "US",
    "Israel",
    "Iran",
    "Europe",
    "MiddleEast",
    "SouthAsia",
    "EastAsia",
    "Global",
}


# =========================
# 工具函数
# =========================
def clean_text(text: Any) -> str:
    if pd.isna(text):
        return ""
    text = str(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def safe_get(row: pd.Series, key: str) -> str:
    return clean_text(row[key]) if key in row else ""


def build_input_payload(row: pd.Series) -> Dict[str, str]:
    domain = safe_get(row, "domain")
    url = safe_get(row, "url")
    title = safe_get(row, "title")
    text = safe_get(row, "text")[:MAX_TEXT_CHARS]

    return {
        "domain": domain,
        "url": url,
        "title": title,
        "text_excerpt": text,
    }


def build_prompt(payload: Dict[str, str]) -> str:
    return f"""
You are a media source analyst.

Task:
Infer the most likely REGION of the NEWS OUTLET, not the event location.

Use these clues:
- domain
- url
- article title
- text excerpt

Important:
1. Infer the outlet's media-region, not where the war happened.
2. Prefer the outlet's institutional origin or primary audience region.
3. Return JSON only.
4. If the outlet is global or cross-regional (for example Reuters, AP, Euronews), use "Global".
5. If uncertain, choose the most likely region and lower confidence.

Allowed values for region_group:
- "US"
- "Israel"
- "Iran"
- "Europe"
- "MiddleEast"
- "SouthAsia"
- "EastAsia"
- "Global"

Helpful guidance:
- US: US-based mainstream or political outlets
- Israel: Israeli outlets
- Iran: Iranian outlets
- Europe: UK and continental European outlets
- MiddleEast: Qatar, UAE, Saudi, Turkey, Arab regional outlets
- SouthAsia: India, Pakistan, Bangladesh, etc.
- EastAsia: China, Japan, Korea, etc.
- Global: Reuters, AP, Euronews, transnational outlets without a single national identity

JSON schema:
{{
  "region_group": "...",
  "country_or_origin": "...",
  "confidence": 1,
  "reason": "short reason"
}}

Input:
domain: {payload["domain"]}
url: {payload["url"]}
title: {payload["title"]}
text_excerpt: {payload["text_excerpt"]}
""".strip()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{{.*\}}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def call_vllm(prompt: str) -> Dict[str, Any]:
    url = f"{VLLM_BASE_URL}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise classifier. Return JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
    }

    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = extract_json(content)

    if parsed is None:
        return {
            "region_group": "Global",
            "country_or_origin": "",
            "confidence": 1,
            "reason": f"JSON parse failed: {content[:200]}"
        }

    region = str(parsed.get("region_group", "Global")).strip()
    if region not in ALLOWED_REGIONS:
        region = "Global"

    origin = str(parsed.get("country_or_origin", "")).strip()

    try:
        confidence = int(parsed.get("confidence", 1))
    except Exception:
        confidence = 1
    confidence = max(1, min(5, confidence))

    reason = str(parsed.get("reason", "")).strip()

    return {
        "region_group": region,
        "country_or_origin": origin,
        "confidence": confidence,
        "reason": reason,
    }


# =========================
# 主流程
# =========================
def main():
    df = pd.read_csv(INPUT_CSV, low_memory=False)

    if "country_group" not in df.columns:
        raise ValueError("Input CSV must contain a 'country_group' column.")

    # 新增输出列
    for col in ["pred_region_group", "pred_origin", "pred_confidence", "pred_reason"]:
        if col not in df.columns:
            df[col] = ""

    unknown_mask = df["country_group"].astype(str).str.strip().eq("Unknown")
    unknown_indices = df[unknown_mask].index.tolist()

    print(f"Total rows: {len(df)}")
    print(f"Unknown rows to infer: {len(unknown_indices)}")

    processed = 0

    for idx in tqdm(unknown_indices, desc="Inferring region_group"):
        row = df.loc[idx]

        existing = str(df.at[idx, "pred_region_group"]).strip()
        if existing in ALLOWED_REGIONS:
            continue

        payload = build_input_payload(row)
        prompt = build_prompt(payload)

        try:
            result = call_vllm(prompt)
        except Exception as e:
            result = {
                "region_group": "Global",
                "country_or_origin": "",
                "confidence": 1,
                "reason": f"request_failed: {e}"
            }

        df.at[idx, "pred_region_group"] = result["region_group"]
        df.at[idx, "pred_origin"] = result["country_or_origin"]
        df.at[idx, "pred_confidence"] = result["confidence"]
        df.at[idx, "pred_reason"] = result["reason"]

        processed += 1

        if processed % SAVE_EVERY == 0:
            df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"\n[Checkpoint] saved after {processed} unknown rows")

        time.sleep(0.05)
    
    def map_existing_to_region(x: str) -> str:
        x = str(x).strip()
        if x in {"US", "Israel", "Iran"}:
            return x
        if x == "ThirdParty":
            return "Global"
        return ""

    df["region_group_final"] = ""

    known_mask = df["country_group"].astype(str).isin(["US", "Israel", "Iran", "ThirdParty"])
    df.loc[known_mask, "region_group_final"] = df.loc[known_mask, "country_group"].apply(map_existing_to_region)

    unknown_mask = df["country_group"].astype(str).str.strip().eq("Unknown")
    df.loc[unknown_mask, "region_group_final"] = df.loc[unknown_mask, "pred_region_group"]
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("\nDone.")
    print(f"Saved to: {OUTPUT_CSV}")

    inferred = df.loc[unknown_mask, "pred_region_group"].value_counts(dropna=False)
    print("\nInferred distribution on Unknown rows:")
    print(inferred)


if __name__ == "__main__":
    main()
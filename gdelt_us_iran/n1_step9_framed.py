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
INPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_region_inferred.csv"
OUTPUT_CSV = "/data_ssd2/zbh/Narrrative/gdelt_us_iran/data/article_texts_framed.csv"

VLLM_BASE_URL = "http://127.0.0.1:8125/v1"
MODEL_NAME = "qwen3-4b-2507"

TEMPERATURE = 0.0
MAX_TOKENS = 320
TIMEOUT = 120

# 只截取前一部分正文，够做 framing 判断
MAX_TEXT_CHARS = 2200

# 断点保存
SAVE_EVERY = 10

# 如果只想先试跑，改成数字，比如 20
LIMIT = None


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


def build_payload(row: pd.Series) -> Dict[str, str]:
    return {
        "domain": safe_get(row, "domain"),
        "url": safe_get(row, "url"),
        "title": safe_get(row, "title"),
        "region_group_final": safe_get(row, "region_group_final"),
        "text_excerpt": safe_get(row, "text")[:MAX_TEXT_CHARS],
    }


def build_prompt(payload: Dict[str, str]) -> str:
    return f"""
You are a careful media-framing analyst.

Task:
Read the following news article and identify its narrative framing.

Important:
- Focus on how the article frames the conflict, not just what happened.
- Use only the article text.
- Return JSON only.

Allowed values:

main_frame:
- "military_operation"
- "ideological_regime"
- "energy_economic"
- "regional_spillover"
- "diplomatic_strategic"
- "humanitarian_victimhood"
- "mixed"

aggressor:
- "Iran"
- "Israel"
- "US"
- "Multiple"
- "Unclear"

victim:
- "Iran"
- "Israel"
- "US"
- "Civilians"
- "Multiple"
- "Unclear"

stance_toward_iran:
- "positive"
- "negative"
- "neutral"
- "mixed"
- "unclear"

stance_toward_israel:
- "positive"
- "negative"
- "neutral"
- "mixed"
- "unclear"

urgency_level:
- 1 to 5

confidence:
- 1 to 5

JSON schema:
{{
  "main_frame": "...",
  "aggressor": "...",
  "victim": "...",
  "stance_toward_iran": "...",
  "stance_toward_israel": "...",
  "urgency_level": 1,
  "confidence": 1,
  "frame_reason": "short explanation"
}}

Metadata:
domain: {payload["domain"]}
region_group_final: {payload["region_group_final"]}
url: {payload["url"]}
title: {payload["title"]}

Article:
{payload["text_excerpt"]}
""".strip()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def normalize_result(parsed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    defaults = {
        "main_frame": "mixed",
        "aggressor": "Unclear",
        "victim": "Unclear",
        "stance_toward_iran": "unclear",
        "stance_toward_israel": "unclear",
        "urgency_level": 3,
        "confidence": 1,
        "frame_reason": "",
    }

    if parsed is None:
        defaults["frame_reason"] = "json_parse_failed"
        return defaults

    allowed_main_frame = {
        "military_operation",
        "ideological_regime",
        "energy_economic",
        "regional_spillover",
        "diplomatic_strategic",
        "humanitarian_victimhood",
        "mixed",
    }
    allowed_actor = {"Iran", "Israel", "US", "Multiple", "Unclear"}
    allowed_stance = {"positive", "negative", "neutral", "mixed", "unclear"}

    out = {}

    out["main_frame"] = str(parsed.get("main_frame", "mixed")).strip()
    if out["main_frame"] not in allowed_main_frame:
        out["main_frame"] = "mixed"

    out["aggressor"] = str(parsed.get("aggressor", "Unclear")).strip()
    if out["aggressor"] not in allowed_actor:
        out["aggressor"] = "Unclear"

    out["victim"] = str(parsed.get("victim", "Unclear")).strip()
    if out["victim"] not in allowed_actor | {"Civilians"}:
        out["victim"] = "Unclear"

    out["stance_toward_iran"] = str(parsed.get("stance_toward_iran", "unclear")).strip()
    if out["stance_toward_iran"] not in allowed_stance:
        out["stance_toward_iran"] = "unclear"

    out["stance_toward_israel"] = str(parsed.get("stance_toward_israel", "unclear")).strip()
    if out["stance_toward_israel"] not in allowed_stance:
        out["stance_toward_israel"] = "unclear"

    try:
        out["urgency_level"] = int(parsed.get("urgency_level", 3))
    except Exception:
        out["urgency_level"] = 3
    out["urgency_level"] = max(1, min(5, out["urgency_level"]))

    try:
        out["confidence"] = int(parsed.get("confidence", 1))
    except Exception:
        out["confidence"] = 1
    out["confidence"] = max(1, min(5, out["confidence"]))

    out["frame_reason"] = str(parsed.get("frame_reason", "")).strip()

    return out


def call_vllm(prompt: str) -> Dict[str, Any]:
    url = f"{VLLM_BASE_URL}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": "You are a precise classifier. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
    }

    resp = requests.post(url, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = extract_json(content)
    return normalize_result(parsed)


# =========================
# 主流程
# =========================
def main():
    df = pd.read_csv(INPUT_CSV, low_memory=False)

    # 只保留正文可用样本
    df = df[
        (df["success"] == True) &
        (df["text"].notna()) &
        (df["word_count"] > 100)
    ].copy()

    # 去重
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    if LIMIT is not None:
        df = df.head(LIMIT).copy()

    # 初始化输出列
    out_cols = [
        "main_frame",
        "aggressor",
        "victim",
        "stance_toward_iran",
        "stance_toward_israel",
        "urgency_level",
        "frame_confidence",
        "frame_reason",
    ]
    for col in out_cols:
        if col not in df.columns:
            df[col] = ""

    print("Rows to annotate:", len(df))

    processed = 0

    for idx in tqdm(df.index, desc="Annotating frames"):
        # 已有结果就跳过
        existing = str(df.at[idx, "main_frame"]).strip()
        if existing:
            continue

        row = df.loc[idx]
        payload = build_payload(row)
        prompt = build_prompt(payload)

        try:
            result = call_vllm(prompt)
        except Exception as e:
            result = {
                "main_frame": "mixed",
                "aggressor": "Unclear",
                "victim": "Unclear",
                "stance_toward_iran": "unclear",
                "stance_toward_israel": "unclear",
                "urgency_level": 3,
                "confidence": 1,
                "frame_reason": f"request_failed: {e}",
            }

        df.at[idx, "main_frame"] = result["main_frame"]
        df.at[idx, "aggressor"] = result["aggressor"]
        df.at[idx, "victim"] = result["victim"]
        df.at[idx, "stance_toward_iran"] = result["stance_toward_iran"]
        df.at[idx, "stance_toward_israel"] = result["stance_toward_israel"]
        df.at[idx, "urgency_level"] = result["urgency_level"]
        df.at[idx, "frame_confidence"] = result["confidence"]
        df.at[idx, "frame_reason"] = result["frame_reason"]

        processed += 1

        if processed % SAVE_EVERY == 0:
            df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"\n[Checkpoint] saved after {processed} rows")

        time.sleep(0.05)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("\nDone.")
    print("Saved to:", OUTPUT_CSV)

    print("\n[main_frame distribution]")
    print(df["main_frame"].value_counts(dropna=False))

    print("\n[aggressor distribution]")
    print(df["aggressor"].value_counts(dropna=False))

    print("\n[victim distribution]")
    print(df["victim"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
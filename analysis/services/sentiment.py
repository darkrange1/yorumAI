import json
import logging
import os
from typing import Any

from langchain.prompts import PromptTemplate

from .constants import DEFAULT_LLM_BATCH_SIZE, JSON_FENCE_RE, SENTIMENTS
from .llm import get_llm, invoke_llm_with_prompt

logger = logging.getLogger(__name__)


def dummy_sentiment_model(text: str) -> tuple[str, float]:
    normalized = text.lower()
    negative_terms = ["kötü", "berbat", "bozuk", "geç", "kırık", "iade", "şikayet"]
    positive_terms = ["güzel", "mükemmel", "hızlı", "kaliteli", "memnun", "harika", "iyi"]

    if any(t in normalized for t in negative_terms):
        return "Negatif", 0.70
    if any(t in normalized for t in positive_terms):
        return "Pozitif", 0.70
    return "Nötr", 0.55


def safe_json_loads(text: str) -> Any:
    candidate = JSON_FENCE_RE.sub("", (text or "").strip()).strip()
    return json.loads(candidate)


def classify_comments_batch_with_llm(llm, indexed_batch: list[tuple[int, str]]) -> list[dict[str, Any]]:
    prompt = PromptTemplate.from_template(
        """
        Aşağıdaki yorumları yalnızca metin içeriğine göre sentiment olarak sınıflandır.
        Zorunlu sentiment etiketleri: Negatif, Nötr, Pozitif.
        Sonucu SADECE geçerli JSON olarak döndür.

        JSON formatı:
        {{
          "results": [
            {{"index": 0, "sentiment": "Negatif|Nötr|Pozitif", "score": 0.0-1.0}}
          ]
        }}

        Kurallar:
        - Tüm index'ler için tek bir sonuç üret.
        - score güven skorudur (0 ile 1 arası float).
        - Ek açıklama, markdown, kod bloğu yazma.

        Veri:
        {batch_json}
        """
    )

    raw = invoke_llm_with_prompt(
        prompt=prompt,
        llm=llm,
        payload={
            "batch_json": json.dumps(
                [{"index": idx, "text": text} for idx, text in indexed_batch],
                ensure_ascii=False,
            )
        },
    )
    parsed = safe_json_loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("LLM batch output is not a JSON object.")
    rows = parsed.get("results")
    if not isinstance(rows, list):
        raise ValueError("LLM batch output is missing 'results' list.")

    valid: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        sentiment = str(row.get("sentiment", "")).strip()
        if sentiment not in SENTIMENTS:
            continue
        try:
            score = float(row.get("score", 0.55))
        except (TypeError, ValueError):
            score = 0.55
        score = max(0.0, min(score, 1.0))
        valid[idx] = {"sentiment": sentiment, "score": round(score, 4)}

    results: list[dict[str, Any]] = []
    for idx, text in indexed_batch:
        if idx in valid:
            results.append({"text": text, **valid[idx]})
            continue
        sentiment, score = dummy_sentiment_model(text)
        results.append({"text": text, "sentiment": sentiment, "score": score})
    return results


def classify_comments(comments: list[str]) -> list[dict[str, Any]]:
    llm = get_llm()
    if llm is None:
        fallback: list[dict[str, Any]] = []
        for text in comments:
            sentiment, score = dummy_sentiment_model(text)
            fallback.append({"text": text, "sentiment": sentiment, "score": score})
        return fallback

    try:
        batch_size = int(os.getenv("LLM_CLASSIFY_BATCH_SIZE", str(DEFAULT_LLM_BATCH_SIZE)))
    except ValueError:
        batch_size = DEFAULT_LLM_BATCH_SIZE
    batch_size = max(10, min(batch_size, 150))

    output: list[dict[str, Any]] = []
    for start in range(0, len(comments), batch_size):
        batch = comments[start : start + batch_size]
        indexed = list(enumerate(batch, start=start))
        try:
            output.extend(classify_comments_batch_with_llm(llm, indexed))
        except Exception as exc:
            logger.exception("LLM sentiment batch failed, keyword fallback will be used: %s", exc)
            for text in batch:
                sentiment, score = dummy_sentiment_model(text)
                output.append({"text": text, "sentiment": sentiment, "score": score})
    return output


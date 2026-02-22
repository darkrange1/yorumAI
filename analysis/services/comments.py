import os
import re
from collections import Counter
from html import unescape
from typing import Any
from urllib.parse import urlparse

from .constants import (
    DEFAULT_DECISION_SHORTLIST_SIZE,
    HARD_MAX_REVIEWS,
    LOGISTIC_TERMS,
    LOW_SIGNAL_TERMS,
    NOISE_PHRASES,
    PRODUCT_TERMS,
    TURKISH_COMMON_WORDS,
    TURKISH_SPECIFIC_CHARS,
    WHITESPACE_RE,
)


def validate_product_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL http/https ile başlamalıdır.")
    if not parsed.netloc:
        raise ValueError("URL domain bilgisi içermelidir.")


def scrape_comments_by_domain(url: str, max_comments: int = HARD_MAX_REVIEWS) -> list[str]:
    validate_product_url(url)
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if "trendyol.com" in domain:
        from trendyol_scraper import trendyol_yorum_scrape

        data = trendyol_yorum_scrape(url, max_comments)
        reviews = data.get("reviews", []) if isinstance(data, dict) else []
        texts = [str(r.get("comment", "")).strip() for r in reviews if isinstance(r, dict)]
        return [t for t in texts if t]

    if "hepsiburada.com" in domain:
        from hepsiburada_scraper import run as hepsiburada_run

        data = hepsiburada_run(url, max_comments)
        if not data or not isinstance(data, dict):
            return []
        reviews = data.get("reviews", [])
        texts = [str(r.get("content", "")).strip() for r in reviews if isinstance(r, dict)]
        return [t for t in texts if t]

    raise ValueError(f"Desteklenmeyen domain: {domain}. Şu an Trendyol ve Hepsiburada destekleniyor.")


def is_turkish(text: str) -> bool:
    if any(c in TURKISH_SPECIFIC_CHARS for c in text):
        return True
    words = set(re.sub(r"[^\w\s]", " ", text.lower()).split())
    return bool(words & TURKISH_COMMON_WORDS)


def normalize_for_dedup(text: str) -> str:
    lowered = text.lower().replace("İ", "i").replace("I", "ı")
    lowered = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    lowered = WHITESPACE_RE.sub(" ", lowered).strip()
    return lowered


def clean_comment_text(text: str) -> str | None:
    cleaned = unescape(text or "")
    cleaned = cleaned.replace("\u200b", " ").replace("\xa0", " ")
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip(" -|")
    if len(cleaned) < 15 or len(cleaned) > 1500:
        return None

    lower = cleaned.lower()
    if any(phrase in lower for phrase in NOISE_PHRASES):
        return None

    alpha_count = sum(1 for c in cleaned if c.isalpha())
    digit_count = sum(1 for c in cleaned if c.isdigit())
    if alpha_count < 8:
        return None
    if digit_count > alpha_count:
        return None
    if "http://" in lower or "https://" in lower:
        return None

    if not is_turkish(cleaned):
        return None

    return cleaned


def prepare_comments_for_model(raw_comments: list[str], max_comments: int) -> list[str]:
    prepared: list[str] = []
    seen_counts: Counter[str] = Counter()
    try:
        max_duplicate_per_comment = int(os.getenv("MAX_DUPLICATE_PER_COMMENT", "2"))
    except ValueError:
        max_duplicate_per_comment = 2
    max_duplicate_per_comment = max(1, min(max_duplicate_per_comment, 8))

    for text in raw_comments:
        cleaned = clean_comment_text(text)
        if not cleaned:
            continue

        dedup_key = normalize_for_dedup(cleaned)
        if seen_counts[dedup_key] >= max_duplicate_per_comment:
            continue
        seen_counts[dedup_key] += 1
        prepared.append(cleaned)

        if len(prepared) >= max_comments:
            break

    return prepared


def normalized_repeat_counts(raw_comments: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for text in raw_comments:
        cleaned = clean_comment_text(text)
        if not cleaned:
            continue
        counts[normalize_for_dedup(cleaned)] += 1
    return dict(counts)


def duplicate_comment_insights(raw_comments: list[str], max_items: int = 5) -> dict[str, Any]:
    normalized_counts: Counter[str] = Counter()
    sample_by_key: dict[str, str] = {}

    for text in raw_comments:
        cleaned = clean_comment_text(text)
        if not cleaned:
            continue
        key = normalize_for_dedup(cleaned)
        normalized_counts[key] += 1
        sample_by_key.setdefault(key, cleaned)

    repeated = [(key, cnt) for key, cnt in normalized_counts.items() if cnt >= 2]
    repeated.sort(key=lambda x: x[1], reverse=True)

    total_repeated_groups = len(repeated)
    total_repeated_instances = sum(cnt - 1 for _, cnt in repeated)
    suspected_bot_groups = sum(1 for _, cnt in repeated if cnt >= 4)
    suspected_bot_instances = sum(cnt for _, cnt in repeated if cnt >= 4)

    top_repeated_comments: list[dict[str, Any]] = []
    for key, cnt in repeated[:max_items]:
        top_repeated_comments.append(
            {
                "comment": sample_by_key.get(key, "")[:220],
                "count": cnt,
            }
        )

    return {
        "repeated_comment_groups": total_repeated_groups,
        "repeated_comment_instances": total_repeated_instances,
        "suspected_bot_groups": suspected_bot_groups,
        "suspected_bot_instances": suspected_bot_instances,
        "top_repeated_comments": top_repeated_comments,
    }


def detect_comment_theme(text_lower: str) -> str:
    if any(t in text_lower for t in ("kargo", "teslimat", "paket", "satıcı")):
        return "lojistik"
    if any(t in text_lower for t in ("fiyat", "pahalı", "ucuz", "performans")):
        return "fiyat_performans"
    if any(t in text_lower for t in ("kalite", "dayan", "bozul", "kırık")):
        return "kalite_dayaniklilik"
    if any(t in text_lower for t in ("koku", "doku", "renk", "tat", "his")):
        return "duyusal_denemim"
    if any(t in text_lower for t in ("saç", "cilt", "etki", "sonuç", "işe yar")):
        return "urun_etkisi"
    return "genel"


def score_comment_for_decision(text: str, repeat_count: int) -> tuple[float, list[str], str]:
    lower = text.lower()
    score = 0.0
    reasons: list[str] = []

    if 35 <= len(text) <= 600:
        score += 1.2
        reasons.append("yeterli detay")
    if re.search(r"\d", text):
        score += 0.8
        reasons.append("sayısal/somut ifade")
    if any(w in lower for w in ("ama", "fakat", "ancak", "öte yandan")):
        score += 0.8
        reasons.append("dengeleyici değerlendirme")
    if any(term in lower for term in PRODUCT_TERMS):
        score += 1.5
        reasons.append("ürün odaklı içerik")
    if any(
        term in lower
        for term in (
            "bozuk",
            "iade",
            "yan etki",
            "kızarıklık",
            "dökülme",
            "memnun",
            "etkili",
            "küçük geldi",
            "büyük geldi",
            "kısa geldi",
            "uzun geldi",
            "yırtık",
            "defolu",
            "kusurlu",
            "sökük",
            "lekeli",
            "koku",
            "tam oldu",
            "tam kalıp",
            "beklediğim gibi",
            "beğendim",
            "çok memnun",
            "tavsiye ederim",
            "kaliteli duruyor",
        )
    ):
        score += 1.0
        reasons.append("karar etkileyen sinyal")

    logistic_hits = sum(1 for t in LOGISTIC_TERMS if t in lower)
    product_hits = sum(1 for t in PRODUCT_TERMS if t in lower)
    if logistic_hits > 0 and product_hits == 0:
        score -= 1.8
        reasons.append("lojistik ağırlıklı")

    short_low_signal = len(text) < 30 and any(t in lower for t in LOW_SIGNAL_TERMS)
    if short_low_signal:
        score -= 1.8
        reasons.append("düşük bilgi değeri")

    if repeat_count >= 4:
        score -= 0.6
        reasons.append("yüksek tekrar")
    elif repeat_count == 1:
        score += 0.2

    return score, reasons[:3], detect_comment_theme(lower)


def build_decision_comment_shortlist(comments: list[str], repeat_counts: dict[str, int], shortlist_size: int | None = None) -> tuple[list[str], dict[str, Any]]:
    if not comments:
        return [], {"candidate_count": 0, "selected_comment_count": 0}

    if shortlist_size is None:
        try:
            shortlist_size = int(os.getenv("DECISION_SHORTLIST_SIZE", str(DEFAULT_DECISION_SHORTLIST_SIZE)))
        except ValueError:
            shortlist_size = DEFAULT_DECISION_SHORTLIST_SIZE
    shortlist_size = max(80, min(shortlist_size, 1000))

    scored: list[dict[str, Any]] = []
    for text in comments:
        key = normalize_for_dedup(text)
        repeat_count = int(repeat_counts.get(key, 1))
        score, reasons, theme = score_comment_for_decision(text, repeat_count=repeat_count)
        scored.append(
            {
                "text": text,
                "score": round(score, 3),
                "theme": theme,
                "repeat_count": repeat_count,
                "why": reasons or ["genel içerik"],
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    min_score = float(os.getenv("DECISION_MIN_SCORE", "0.6"))
    filtered = [item for item in scored if item["score"] >= min_score]
    pool = filtered if filtered else scored

    selected: list[dict[str, Any]] = []
    theme_quota: Counter[str] = Counter()
    for item in pool:
        if len(selected) >= shortlist_size:
            break
        if item["theme"] != "genel" and theme_quota[item["theme"]] >= 40:
            continue
        selected.append(item)
        theme_quota[item["theme"]] += 1

    shortlist = [item["text"] for item in selected]
    selection_insights = {
        "candidate_count": len(comments),
        "selected_comment_count": len(shortlist),
        "dropped_low_signal_count": max(len(comments) - len(shortlist), 0),
        "score_threshold": min_score,
        "theme_distribution": dict(Counter(item["theme"] for item in selected)),
        "top_decision_comments": [
            {
                "comment": item["text"][:240],
                "score": item["score"],
                "repeat_count": item["repeat_count"],
                "why_selected": item["why"],
            }
            for item in selected[:8]
        ],
    }
    return shortlist, selection_insights

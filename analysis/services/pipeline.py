from typing import Any

from .comments import (
    build_decision_comment_shortlist,
    duplicate_comment_insights,
    normalized_repeat_counts,
    prepare_comments_for_model,
    scrape_comments_by_domain,
)
from .summary import build_langchain_summary
from .sentiment import classify_comments


def execute_analysis_pipeline(url: str, max_reviews: int, shortlist_size: int | None = None) -> tuple[dict[str, Any], str]:
    scraped_comments = scrape_comments_by_domain(url=url, max_comments=max_reviews)
    comments = prepare_comments_for_model(scraped_comments, max_comments=max_reviews)
    repeat_counts = normalized_repeat_counts(scraped_comments)
    duplicate_insights = duplicate_comment_insights(scraped_comments)
    selected_comments, selection_insights = build_decision_comment_shortlist(comments, repeat_counts, shortlist_size=shortlist_size)
    if not comments:
        raise RuntimeError("Yorumlar alındı ancak model için uygun yorum bulunamadı. CSS selector ve filtreleri kontrol edin.")
    if not selected_comments:
        selected_comments = comments[:240]
        selection_insights = {
            "candidate_count": len(comments),
            "selected_comment_count": len(selected_comments),
            "dropped_low_signal_count": max(len(comments) - len(selected_comments), 0),
            "score_threshold": "fallback",
            "theme_distribution": {},
            "top_decision_comments": [],
        }

    classified = classify_comments(selected_comments)
    summary = build_langchain_summary(
        classified,
        duplicate_insights=duplicate_insights,
        selection_insights=selection_insights,
    )

    raw_payload: dict[str, Any] = {
        "scraped_count": len(scraped_comments),
        "prepared_count": len(comments),
        "selected_count": len(selected_comments),
        "filtered_out_count": max(len(scraped_comments) - len(comments), 0),
        "comment_count": len(classified),
        "comments": classified,
        "duplicate_comment_insights": duplicate_insights,
        "decision_comment_selection": selection_insights,
    }
    return raw_payload, summary


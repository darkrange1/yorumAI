import logging
import os

from celery import shared_task
from django.db import transaction

from .models import Analysis
from .services.constants import DEFAULT_MAX_REVIEWS, HARD_MAX_REVIEWS
from .services.pipeline import execute_analysis_pipeline

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="analysis.process_product_reviews")
def process_product_reviews(self, analysis_id: str, url: str, max_reviews: int | None = None, shortlist_size: int | None = None) -> str:
    try:
        analysis = Analysis.objects.get(id=analysis_id)
    except Analysis.DoesNotExist as exc:
        logger.error("Analysis not found: %s", analysis_id)
        raise ValueError("Analysis bulunamadı") from exc

    analysis.status = Analysis.Status.PROCESSING
    analysis.save(update_fields=["status"])

    try:
        if max_reviews is None:
            max_reviews = int(os.getenv("MAX_REVIEWS", str(DEFAULT_MAX_REVIEWS)))
        max_reviews = max(100, min(max_reviews, HARD_MAX_REVIEWS))

        raw_payload, summary = execute_analysis_pipeline(url=url, max_reviews=max_reviews, shortlist_size=shortlist_size)

        with transaction.atomic():
            analysis.raw_comments = raw_payload
            analysis.summary_result = summary
            analysis.status = Analysis.Status.COMPLETED
            analysis.save(update_fields=["raw_comments", "summary_result", "status"])

        return str(analysis.id)

    except Exception as exc:
        logger.exception("Analysis task failed for %s: %s", analysis_id, exc)
        analysis.status = Analysis.Status.FAILED
        analysis.raw_comments = {
            "error": str(exc),
            "comment_count": 0,
            "comments": [],
        }
        analysis.summary_result = ""
        analysis.save(update_fields=["status", "raw_comments", "summary_result"])
        raise

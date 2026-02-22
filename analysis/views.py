import json
import logging
from urllib.parse import urlparse

from celery.result import AsyncResult
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Analysis
from .tasks import process_product_reviews

logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


@require_GET
def home_view(request: HttpRequest):
    return render(request, "analysis/index.html")


@csrf_exempt
@require_POST
def analysis_submit_view(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Geçersiz JSON payload."}, status=400)

    url = str(payload.get("url", "")).strip()
    if not _is_valid_url(url):
        return JsonResponse({"error": "Geçerli bir ürün URL'i gönderin."}, status=400)

    max_reviews = payload.get("max_reviews")
    shortlist_size = payload.get("shortlist_size")

    try:
        max_reviews = int(max_reviews) if max_reviews is not None else None
        shortlist_size = int(shortlist_size) if shortlist_size is not None else None
    except (TypeError, ValueError):
        return JsonResponse({"error": "max_reviews ve shortlist_size tam sayı olmalı."}, status=400)

    try:
        analysis = Analysis.objects.create(url=url, status=Analysis.Status.PENDING)
        task = process_product_reviews.delay(str(analysis.id), url, max_reviews, shortlist_size)

        analysis.task_id = task.id
        analysis.save(update_fields=["task_id"])

        return JsonResponse(
            {
                "analysis_id": str(analysis.id),
                "task_id": task.id,
                "status": analysis.status,
            },
            status=202,
        )
    except Exception as exc:
        logger.exception("Failed to create analysis: %s", exc)
        return JsonResponse({"error": "Analiz başlatılamadı."}, status=500)


@require_GET
def analysis_detail_view(request: HttpRequest, analysis_id) -> JsonResponse:
    try:
        analysis = Analysis.objects.get(id=analysis_id)
    except Analysis.DoesNotExist:
        return JsonResponse({"error": "Analiz bulunamadı."}, status=404)

    task_state = None
    if analysis.task_id:
        task_state = AsyncResult(analysis.task_id).state

    response = {
        "analysis_id": str(analysis.id),
        "url": analysis.url,
        "status": analysis.status,
        "task_state": task_state,
        "created_at": analysis.created_at.isoformat(),
    }

    if analysis.status == Analysis.Status.COMPLETED:
        response["raw_comments"] = analysis.raw_comments
        response["summary_result"] = analysis.summary_result
    elif analysis.status == Analysis.Status.FAILED:
        response["error"] = analysis.raw_comments.get("error", "Bilinmeyen hata")

    return JsonResponse(response, status=200)

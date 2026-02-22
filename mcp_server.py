import asyncio
import os
import time

import httpx
from fastmcp import FastMCP

DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://web:8000")
POLL_INTERVAL = int(os.getenv("MCP_POLL_INTERVAL", "5"))
MAX_POLL_SECONDS = int(os.getenv("MCP_MAX_POLL_SECONDS", "600"))

mcp = FastMCP(
    name="Ürün Yorum Analizi",
    instructions=(
        "Trendyol ve Hepsiburada ürün yorumlarını analiz eden bir araç. "
        "analyze_product() ile URL ver, LLM destekli sentiment analizi ve özet rapor al. "
        "Desteklenen siteler: trendyol.com, hepsiburada.com"
    ),
)


@mcp.tool()
async def analyze_product(
    url: str,
    max_reviews: int = 1500,
    shortlist_size: int = 300,
) -> str:
    """
    Trendyol veya Hepsiburada ürün URL'sini alır, yorumları çekip
    LLM ile sentiment analizi yapar ve Türkçe özet rapor döndürür.
    İşlem ürüne göre 2-10 dakika sürebilir.

    Args:
        url: Ürün sayfası linki (trendyol.com veya hepsiburada.com)
        max_reviews: Kaç yorum çekilsin (100-3000, varsayılan 1500)
        shortlist_size: LLM'e kaç yorum gönderilsin (80-1000, varsayılan 300).
                        Düşük = daha hızlı, Yüksek = daha kapsamlı analiz.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{DJANGO_BASE_URL}/api/analyses/",
                json={
                    "url": url,
                    "max_reviews": max_reviews,
                    "shortlist_size": shortlist_size,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"Analiz başlatılamadı: HTTP {e.response.status_code} — {e.response.text[:200]}"
        except httpx.RequestError as e:
            return f"Bağlantı hatası (Django servisi çalışıyor mu?): {e}"

        data = resp.json()
        analysis_id = data.get("analysis_id")
        if not analysis_id:
            return f"Analiz ID alınamadı. Yanıt: {data}"

    deadline = time.monotonic() + MAX_POLL_SECONDS
    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                resp = await client.get(f"{DJANGO_BASE_URL}/api/analyses/{analysis_id}/")
                resp.raise_for_status()
                status_data = resp.json()
            except Exception:
                continue

            status = status_data.get("status")

            if status == "Completed":
                summary = status_data.get("summary_result", "")
                raw = status_data.get("raw_comments", {})
                scraped = raw.get("scraped_count", 0)
                prepared = raw.get("prepared_count", 0)
                analyzed = raw.get("comment_count", 0)
                return (
                    f"## Analiz Tamamlandı\n\n"
                    f"- Çekilen yorum: {scraped}\n"
                    f"- Filtrelenmiş geçerli yorum: {prepared}\n"
                    f"- LLM ile analiz edilen: {analyzed}\n\n"
                    f"---\n\n{summary}"
                )

            if status == "Failed":
                error = status_data.get("error", "Bilinmeyen hata")
                return f"Analiz başarısız: {error}"

    timeout_min = MAX_POLL_SECONDS // 60
    return (
        f"Analiz zaman aşımına uğradı ({timeout_min} dakika). "
        f"Şu komutla durumu kontrol edebilirsin: check_analysis('{analysis_id}')"
    )


@mcp.tool()
async def check_analysis(analysis_id: str) -> str:
    """
    Daha önce başlatılmış bir analizin durumunu ve sonucunu döndürür.
    analyze_product() zaman aşımına uğrarsa bu araçla takip edebilirsin.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{DJANGO_BASE_URL}/api/analyses/{analysis_id}/")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return "Analiz bulunamadı. ID'yi kontrol et."
            return f"HTTP hatası: {e.response.status_code}"
        except httpx.RequestError as e:
            return f"Bağlantı hatası: {e}"

    status = data.get("status")

    if status == "Completed":
        summary = data.get("summary_result", "")
        raw = data.get("raw_comments", {})
        scraped = raw.get("scraped_count", 0)
        analyzed = raw.get("comment_count", 0)
        return (
            f"## Durum: Tamamlandı\n\n"
            f"- Çekilen: {scraped} yorum\n"
            f"- Analiz edilen: {analyzed} yorum\n\n"
            f"---\n\n{summary}"
        )

    if status == "Failed":
        error = data.get("error", "Bilinmeyen hata")
        return f"Durum: Başarısız\nHata: {error}"

    if status in ("Pending", "Processing"):
        return f"Durum: {status} — Analiz devam ediyor, biraz bekle ve tekrar dene."

    return f"Bilinmeyen durum: {status}"


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8001"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)

import json
import logging
from collections import Counter
from typing import Any

from langchain.prompts import PromptTemplate

from .llm import get_llm, invoke_llm_with_prompt

logger = logging.getLogger(__name__)


def reason_insights(classified: list[dict[str, Any]]) -> dict[str, Any]:
    tokens_negative: Counter[str] = Counter()
    tokens_positive: Counter[str] = Counter()

    stop_words = {
        "ve",
        "ama",
        "çok",
        "bir",
        "bu",
        "için",
        "ile",
        "de",
        "da",
        "the",
        "for",
        "and",
    }

    for item in classified:
        words = [w.strip(".,!?;:()[]{}\"'").lower() for w in item["text"].split()]
        words = [w for w in words if len(w) > 2 and w not in stop_words]
        if item["sentiment"] == "Negatif":
            tokens_negative.update(words)
        elif item["sentiment"] == "Pozitif":
            tokens_positive.update(words)

    return {
        "negative_keywords": [k for k, _ in tokens_negative.most_common(8)],
        "positive_keywords": [k for k, _ in tokens_positive.most_common(8)],
    }


def build_langchain_summary(
    classified: list[dict[str, Any]],
    duplicate_insights: dict[str, Any] | None = None,
    selection_insights: dict[str, Any] | None = None,
) -> str:
    counts = Counter(item["sentiment"] for item in classified)
    reasons = reason_insights(classified)
    duplicate_insights = duplicate_insights or {}

    payload = {
        "total_comments": len(classified),
        "sentiment_distribution": {
            "Negatif": counts.get("Negatif", 0),
            "Nötr": counts.get("Nötr", 0),
            "Pozitif": counts.get("Pozitif", 0),
        },
        "negative_keywords": reasons["negative_keywords"],
        "positive_keywords": reasons["positive_keywords"],
        "duplicate_comment_insights": duplicate_insights,
        "decision_comment_selection": selection_insights or {},
    }

    prompt = PromptTemplate.from_template(
        """
        Sen bir e-ticaret yorum analisti olarak çalışıyorsun.
        Hedef kitlen ürünü satın almayı düşünen son kullanıcılar.
        Sadece verilen JSON verisine dayanarak Türkçe, satın alma kararına yardımcı bir özet üret.
        Veri dışı bilgi ekleme, uydurma yapma.

        Amaç:
        - Kullanıcıların şikayet ve memnuniyet nedenlerini anlaşılır temalarda toplamak
        - Satın alma riski ve güçlü tarafları net, sade ve dürüst anlatmak
        - Aynı yorum tekrarları veya bot şüphesi varsa bunu sayısal olarak belirtmek

        Yazım kuralları:
        - Kısa, net, güven veren Türkçe kullan.
        - Çıktıyı düz metin ver; markdown vurgusu kullanma.
        - `**` dahil hiçbir kalın/italik işareti kullanma.
        - "etki: düşük/orta/yüksek" kalıbını KULLANMA.
        - Her tema maddesinde bunun ne kadar sık geçtiğini doğal cümleyle söyle.
        - Örnek ifade: "Bu konu yorumlarda çokça bahsedilmiş."
        - Veride belirgin sinyal yoksa bunu açıkça belirt.
        - Toplam yorum dağılımını (Negatif/Nötr/Pozitif) tek satırda ver.
        - decision_comment_selection alanını kullanarak bu analizin seçili yorumlar ile üretildiğini not et.

        Çıktı formatı (bu sırayı koru):
        1) Şikayet Nedenleri
        - En fazla 5 madde.
        - Her madde: "Tema: kısa açıklama + görülme sıklığı ifadesi"

        2) Memnuniyet Nedenleri
        - En fazla 5 madde.
        - Her madde: "Tema: kısa açıklama + görülme sıklığı ifadesi"

        3) Tekrarlanan Yorum ve Bot Şüphesi
        - duplicate_comment_insights alanına bakarak değerlendir.
        - Kaç farklı yorum tekrar ettiği ve toplam tekrar adedini sayı ile yaz.
        - Bot şüphesi varsa "kesin bot" deme; "bot benzeri tekrar paterni" olarak belirt.

        4) Satın Alma Önerisi
        - En fazla 4 madde.
        - Ürünü almayı düşünen kullanıcı için somut öneri yaz.
        - Kimler için uygun/uygunsuz olabileceğini kısa belirt.

        5) Kısa Özet
        - 2-3 cümlelik genel değerlendirme.

        6) Dağılım
        - "Negatif/Nötr/Pozitif: X/Y/Z" formatında tek satır.

        Veri:
        {analysis_json}
        """
    )

    fallback_text = (
        "Kullanıcıların şikayet ettiği başlıca noktalar: "
        f"{', '.join(reasons['negative_keywords']) or 'belirgin negatif tema yok'}. "
        "Kullanıcıların memnun kaldığı başlıca noktalar: "
        f"{', '.join(reasons['positive_keywords']) or 'belirgin pozitif tema yok'}. "
        f"Tekrarlanan yorum sayısı: {duplicate_insights.get('repeated_comment_instances', 0)}. "
        f"Dağılım Negatif/Nötr/Pozitif: {counts.get('Negatif', 0)}/{counts.get('Nötr', 0)}/{counts.get('Pozitif', 0)}."
    )

    llm = get_llm()
    if llm is None:
        return fallback_text

    try:
        return invoke_llm_with_prompt(
            prompt=prompt,
            llm=llm,
            payload={"analysis_json": json.dumps(payload, ensure_ascii=False)},
        )
    except Exception as exc:
        logger.exception("LLM summary failed, fallback summary will be used: %s", exc)
        return fallback_text


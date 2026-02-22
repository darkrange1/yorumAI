import re

WHITESPACE_RE = re.compile(r"\s+")
JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE)

SENTIMENTS = {"Negatif", "Nötr", "Pozitif"}

DEFAULT_LLM_BATCH_SIZE = 75
DEFAULT_DECISION_SHORTLIST_SIZE = 300
DEFAULT_MAX_REVIEWS = 2500
HARD_MAX_REVIEWS = 3000

NOISE_PHRASES = {
    "indirim kupon",
    "satış yap",
    "hakkımızda",
    "ürün, kategori veya marka ara",
    "hemen al, fırsatı kaçırma",
    "sepete eklendi",
    "kargoya teslim",
    "adresini seç",
    "iade koşulları",
    "teslimat",
    "satıcı puanı",
    "kampanya",
}

LOW_SIGNAL_TERMS = {
    "güzel",
    "iyi",
    "harika",
    "berbat",
    "kötü",
    "eh işte",
    "idare eder",
    "tavsiye ederim",
}

LOGISTIC_TERMS = {
    "kargo",
    "teslimat",
    "teslim",
    "gecikti",
    "geç geldi",
    "kargoda",
    "teslim edildi",
    "paket",
    "kutu",
    "paketleme",
    "paket hasarlı",
    "hasarlı kargo",
    "satıcı",
    "kurye",
    "şube",
    "iade süreci",
}

TURKISH_SPECIFIC_CHARS = frozenset("şğıŞĞ")

TURKISH_COMMON_WORDS = frozenset({
    "ve", "bir", "bu", "da", "de", "için", "ile", "olan", "var", "çok",
    "gibi", "daha", "ama", "fakat", "ancak", "ben", "benim", "ürün",
    "güzel", "iyi", "kötü", "aldım", "geldi", "beğendim", "tavsiye",
    "kalite", "fiyat", "renk", "kullandım", "memnun", "iade", "kargo",
    "değil", "oldu", "bence", "gayet", "hiç", "zaten", "artık",
    "cok", "guzel", "urun", "kotü", "kotu", "begendim", "aldim",
    "geldi", "gelmedi", "urunun", "kaliteli", "tavsiye", "memnunum",
})

PRODUCT_TERMS = {
    "ürün",
    "etki",
    "performans",
    "kalite",
    "kalitesiz",
    "dokusu",
    "kokusu",
    "koku",
    "saç",
    "cilt",
    "boya",
    "dayanıkl",
    "dayanıklı",
    "kullanım",
    "kullanışlı",
    "rahat",
    "konfor",
    "fiyat",
    "fiyat performans",
    "fiyat/performans",
    "parasını hak",
    "içerik",
    "beden",
    "kalıp",
    "dar",
    "bol",
    "tam oldu",
    "tam kalıp",
    "kumaş",
    "dikiş",
    "esnek",
    "yumuşak",
    "sert",
    "renk",
    "solma",
    "çekme",
    "tüylenme",
}

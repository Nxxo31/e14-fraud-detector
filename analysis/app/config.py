"""E14 Analysis — Configuration."""

import os

# Shared with acquisition service (environment variable names match)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://e14user:***@db:5432/e14acquisition"
)
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://:redispass@redis:6379/0"
)

# MinIO (shared with acquisition)
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_HOT = os.getenv("MINIO_BUCKET_HOT", "e14-pdfs-hot")

# Celery
CELERY_BROKER_URL    = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL + "/2"   # separate DB from acquisition

# Rendering
RENDER_DPI = int(os.getenv("E14_RENDER_DPI", "300"))
MAX_RENDER_MP = float(os.getenv("E14_MAX_RENDER_MP", "50.0"))  # megapixels cap

# OCR
OCR_USE_GPU = os.getenv("E14_OCR_USE_GPU", "0") == "1"
OCR_LANGUAGE = os.getenv("E14_OCR_LANGUAGE", "en")  # digits are language-agnostic

# Signature detection
SIGNATURE_BOXES = [
    {"id": 1, "x": 0.15, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 2, "x": 0.40, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 3, "x": 0.65, "y": 0.62, "w": 0.22, "h": 0.10},
]
SIGNATURE_INK_THRESHOLD = float(os.getenv("E14_SIG_INK_THRESHOLD", "0.05"))   # below this = EMPTY
SIGNATURE_INK_CONFIRMED = float(os.getenv("E14_SIG_INK_CONFIRMED", "0.15"))  # above this = PRESENT

# Risk scoring weights
RISK_WEIGHTS = {
    "signature_missing": 50.0,
    "signature_incomplete": 30.0,
    "sum_mismatch": 40.0,
    "overvote": 35.0,
    "negative_votes": 35.0,
    "exceeds_3_digits": 15.0,
    "ocr_low_confidence": 15.0,
    "correction_detected": 20.0,
}

# Election candidate names (presidential 2026)
CANDIDATE_NAMES = {
    1: "Iván Cepeda",
    2: "Claudia López",
    3: "Santiago Botero",
    4: "Abelardo de la Espriella",
    5: "Mauricio Lizcano",
    6: "Miguel Ángel Uribe",
    7: "Sondra Macollins",
    8: "Roy Barreras",
    9: "Eduardo Caicedo",
    10: "Gustavo Matamoros",
    11: "Paloma Valencia",
    12: "Sergio Fajardo",
    13: "Gilberto Murillo",
}
CANDIDATE_COUNT = 13
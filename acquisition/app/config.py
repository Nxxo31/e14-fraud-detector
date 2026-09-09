"""E14 Acquisition Service — Configuration"""

import os

# ── Registraduría CDN ────────────────────────────────────────────────────────
CDN_BASE_URL = os.getenv(
    "E14_CDN_BASE_URL",
    "https://divulgacione14presidente.registraduria.gov.co"
)
CDN_JSON_BASE = f"{CDN_BASE_URL}/assets/temis/divipol_json"
CDN_PDF_BASE  = f"{CDN_BASE_URL}/assets/temis/pdf"

JSON_FILES = {
    "transmission_codes": "allTransmissionCodes.json",
    "corporations":       "allCorporations.json",
    "departments_tree":   "departmentsTree.json",
    "departments":        "allDepartments.json",
}

# ── Akamai / curl_cffi ───────────────────────────────────────────────────────
CURL_CFFI_IMPERSONATE = os.getenv("E14_CURL_IMPERSONATE", "chrome")
CDN_PRIME_TIMEOUT     = int(os.getenv("E14_CDN_PRIME_TIMEOUT", "30"))
PDF_DOWNLOAD_TIMEOUT  = int(os.getenv("E14_PDF_DOWNLOAD_TIMEOUT", "30"))
JSON_TIMEOUT          = int(os.getenv("E14_JSON_TIMEOUT", "15"))

# ── Rate Limiting ─────────────────────────────────────────────────────────────
GLOBAL_RATE_LIMIT = float(os.getenv("E14_RATE_LIMIT", "8.0"))  # req/s
MAX_CONCURRENT    = int(os.getenv("E14_MAX_CONCURRENT", "6"))

# ── PDF URL template ──────────────────────────────────────────────────────────
# /assets/temis/pdf/{dep:02}/{muni:03}/{zona:03}/{puesto:02}/{mesa:03}/PRE/{expectedName}
PDF_URL_TEMPLATE = (
    CDN_PDF_BASE + "/{dep}/{muni}/{zona}/{puesto}/PRE/{expected_name}"
)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://e14user:***@db:5432/e14acquisition"
)

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://redis:***@db:5432/e14acquisition"
)

# ── MinIO ─────────────────────────────────────────────────────────────────────
MINIO_ENDPOINT        = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY      = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY      = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_HOT      = os.getenv("MINIO_BUCKET_HOT", "e14-pdfs-hot")
MINIO_BUCKET_COLD     = os.getenv("MINIO_BUCKET_COLD", "e14-pdfs-cold")

# ── Storage ───────────────────────────────────────────────────────────────────
PDF_CACHE_TTL_SECONDS = int(os.getenv("E14_PDF_CACHE_TTL", "604800"))  # 7 days
PDF_DOWNLOAD_MAX_RETRIES = int(os.getenv("E14_PDF_MAX_RETRIES", "5"))
PDF_RETRY_DELAY_BASE = int(os.getenv("E14_PDF_RETRY_DELAY", "60"))  # seconds

# ── Celery ────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL  = REDIS_URL + "/0"
CELERY_RESULT_BACKEND = REDIS_URL + "/1"

# ── Monitoring ────────────────────────────────────────────────────────────────
PROMETHEUS_PORT = int(os.getenv("E14_PROMETHEUS_PORT", "9090"))
"""Configuración del ingestion layer."""

from pydantic_settings import BaseSettings


class IngestionSettings(BaseSettings):
    """Configuración para la capa de ingestión."""

    # CDN Source
    CDN_BASE_URL: str = "https://divulgacione14presidente.registraduria.gov.co"
    PDF_PATH_TEMPLATE: str = "/assets/temis/pdf/{dep:02}/{muni:03}/{zona:03}/{puesto:02}/{mesa:03}/PRE/{expected_name}"
    TRANSMISSION_CODES_URL: str = "https://divulgacione14presidente.registraduria.gov.co/assets/temis/allTransmissionCodes.json"

    # Rate limiting
    MAX_REQUESTS_PER_SECOND: int = 8
    RATE_LIMIT_WINDOW: float = 1.0  # seconds

    # Retry configuration
    MAX_RETRIES: int = 5
    RETRY_BASE_DELAY: int = 60  # seconds
    RETRY_MAX_DELAY: int = 240  # seconds

    # Worker configuration
    WORKER_CONCURRENCY: int = 6
    WORKER_POOL: str = "prefork"

    # Celery configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Queue names
    QUEUE_UNIVERSE: str = "allTransmission"
    QUEUE_PDF_DOWNLOAD: str = "pdf_download"
    QUEUE_FALLBACK_RETRY: str = "fallback_retry"
    QUEUE_DEAD_LETTER: str = "dead_letter"

    # Cookie refresh
    COOKIE_REFRESH_INTERVAL: int = 1800  # 30 minutes in seconds

    # Download settings
    DOWNLOAD_TIMEOUT: int = 30  # seconds
    PDF_VALIDATION_ENABLED: bool = True

    # Storage paths
    TEMP_DOWNLOAD_PATH: str = "/tmp/e14/downloads"
    PERMANENT_STORAGE_PATH: str = "/data/e14/pdfs"

    class Config:
        env_prefix = "E14_INGESTION_"
        case_sensitive = True


# Global settings instance
settings = IngestionSettings()
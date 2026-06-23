"""E14 Acquisition — Celery application configuration."""

from celery import Celery
from kombu import Queue

from app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery("e14acquisition")

celery_app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,

    # Task queues
    task_queues={
        Queue("refresh_universe", routing_key="refresh_universe", max_priority=10),
        Queue("download_batch",   routing_key="download_batch",   max_priority=5),
        Queue("retry_failed",     routing_key="retry_failed",     max_priority=3),
        Queue("health_check",     routing_key="health_check",    max_priority=1),
    },
    task_default_queue="download_batch",
    task_default_routing_key="download_batch",

    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=5,
    task_default_retry_delay=60,
    task_retry_backoff=True,
    task_retry_backoff_max=600,

    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Result expiry
    result_expires=3600,

    # Beat schedule
    beat_schedule={
        "refresh-universe": {
            "task": "worker.tasks.refresh_universe",
            "schedule": 1800.0,  # 30 minutes
            "options": {"queue": "refresh_universe", "routing_key": "refresh_universe"},
        },
        "retry-failed": {
            "task": "worker.tasks.retry_failed_downloads",
            "schedule": 900.0,   # 15 minutes
            "options": {"queue": "retry_failed", "routing_key": "retry_failed"},
        },
        "evict-expired": {
            "task": "worker.tasks.evict_expired_pdfs",
            "schedule": 3600.0,  # 1 hour
            "options": {"queue": "health_check", "routing_key": "health_check"},
        },
    },
)
"""E14 Analysis — Celery application."""

from celery import Celery
from kombu import Queue

from app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery("e14analysis")

celery_app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,

    task_queues={
        Queue("analysis",  routing_key="analysis",  max_priority=5),
        Queue("health",    routing_key="health",    max_priority=1),
    },
    task_default_queue="analysis",
    task_default_routing_key="analysis",

    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    task_default_retry_delay=120,

    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
)
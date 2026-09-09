"""Ingestion queue management using Celery and Redis.

Manages the download queue for E-14 PDFs with multiple queue priorities,
dead letter queue for failed downloads, and automatic retry logic.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from celery import Celery
from celery.apps.worker import Worker
from kombu import Queue

from ..config import settings

logger = logging.getLogger(__name__)


class QueuePriority(str, Enum):
    """Queue priority levels."""

    HIGH = "high"  # Universe enumeration (allTransmission)
    NORMAL = "normal"  # PDF downloads
    LOW = "low"  # Retry/fallback


@dataclass
class ActaIdentifier:
    """Unique identifier for an E-14 electoral record (acta)."""

    dep: int  # Department code (0-99)
    muni: int  # Municipality code (0-999)
    zona: int  # Zone code (0-999)
    puesto: int  # Voting station code (0-99)
    mesa: int  # Table code (0-999)
    expected_name: str  # Expected filename from transmission codes

    def to_dict(self) -> dict:
        """Convert to dictionary for queue serialization."""
        return {
            "dep": self.dep,
            "muni": self.muni,
            "zona": self.zona,
            "puesto": self.puesto,
            "mesa": self.mesa,
            "expected_name": self.expected_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActaIdentifier":
        """Create from dictionary."""
        return cls(
            dep=int(data["dep"]),
            muni=int(data["muni"]),
            zona=int(data["zona"]),
            puesto=int(data["puesto"]),
            mesa=int(data["mesa"]),
            expected_name=data["expected_name"],
        )

    def cache_key(self) -> str:
        """Generate cache key for Redis storage."""
        return f"acta:{self.dep:02}/{self.muni:03}/{self.zona:03}/{self.puesto:02}/{self.mesa:03}"


@dataclass
class DownloadTask:
    """A download task for a single E-14 PDF."""

    acta: ActaIdentifier
    priority: QueuePriority = QueuePriority.NORMAL
    retry_count: int = 0
    max_retries: int = settings.MAX_RETRIES
    created_at: datetime = field(default_factory=datetime.utcnow)
    task_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for queue serialization."""
        return {
            "acta": self.acta.to_dict(),
            "priority": self.priority.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "task_id": self.task_id,
        }


def create_celery_app(name: str = "e14_ingestion") -> Celery:
    """Create and configure Celery application.

    Args:
        name: Celery app name

    Returns:
        Configured Celery app instance
    """
    app = Celery(name)

    # Configure from settings
    app.conf.broker_url = settings.CELERY_BROKER_URL
    app.conf.result_backend = settings.CELERY_RESULT_BACKEND

    # Define queues with priorities
    app.conf.task_queues = (
        Queue(settings.QUEUE_UNIVERSE, routing_key="universe.#"),
        Queue(settings.QUEUE_PDF_DOWNLOAD, routing_key="download.#"),
        Queue(settings.QUEUE_FALLBACK_RETRY, routing_key="retry.#"),
        Queue(settings.QUEUE_DEAD_LETTER, routing_key="dlq.#"),
    )

    # Task routing
    app.conf.task_routes = {
        "ingestion.workers.tasks.download_pdf": {
            "queue": settings.QUEUE_PDF_DOWNLOAD,
            "routing_key": "download.pdf",
        },
        "ingestion.workers.tasks.refresh_universe": {
            "queue": settings.QUEUE_UNIVERSE,
            "routing_key": "universe.refresh",
        },
        "ingestion.workers.tasks.retry_failed": {
            "queue": settings.QUEUE_FALLBACK_RETRY,
            "routing_key": "retry.failed",
        },
    }

    # Retry configuration
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True

    # Result expiration
    app.conf.result_expires = 3600  # 1 hour

    # Serializer
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"
    app.conf.accept_content = ["json"]

    return app


class IngestionQueue:
    """High-level queue management for E-14 ingestion.

    Provides methods to enqueue download tasks, check queue status,
    and manage the dead letter queue.
    """

    def __init__(self, celery_app: Optional[Celery] = None):
        """Initialize ingestion queue.

        Args:
            celery_app: Celery app instance (creates default if not provided)
        """
        self.celery_app = celery_app or create_celery_app()

    def enqueue_download(self, task: DownloadTask) -> str:
        """Enqueue a PDF download task.

        Args:
            task: Download task to enqueue

        Returns:
            Celery task ID
        """
        from .workers.tasks import download_pdf

        result = download_pdf.apply_async(
            kwargs={"acta_data": task.acta.to_dict()},
            queue=settings.QUEUE_PDF_DOWNLOAD,
            retry=False,
        )

        logger.info(f"Enqueued download task {result.id} for {task.acta.cache_key()}")
        return result.id

    def enqueue_batch(self, tasks: list[DownloadTask]) -> list[str]:
        """Enqueue multiple download tasks as a batch.

        Args:
            tasks: List of download tasks

        Returns:
            List of Celery task IDs
        """
        task_ids = []
        for task in tasks:
            task_id = self.enqueue_download(task)
            task_ids.append(task_id)
        return task_ids

    def enqueue_universe_refresh(self) -> str:
        """Enqueue a universe refresh task.

        Returns:
            Celery task ID
        """
        from .workers.tasks import refresh_universe

        result = refresh_universe.apply_async(
            queue=settings.QUEUE_UNIVERSE,
        )
        logger.info(f"Enqueued universe refresh task {result.id}")
        return result.id

    def enqueue_retry_failed(self) -> str:
        """Enqueue a retry task for failed downloads.

        Returns:
            Celery task ID
        """
        from .workers.tasks import retry_failed

        result = retry_failed.apply_async(
            queue=settings.QUEUE_FALLBACK_RETRY,
        )
        logger.info(f"Enqueued retry failed task {result.id}")
        return result.id

    def move_to_dlq(self, task: DownloadTask, error_message: str) -> str:
        """Move a failed task to the dead letter queue.

        Args:
            task: Failed download task
            error_message: Error that caused the failure

        Returns:
            Celery task ID
        """
        from .workers.tasks import dlq_handler

        dlq_payload = {
            **task.to_dict(),
            "error_message": error_message,
            "failed_at": datetime.utcnow().isoformat(),
        }

        result = dlq_handler.apply_async(
            kwargs={"dlq_data": dlq_payload},
            queue=settings.QUEUE_DEAD_LETTER,
        )

        logger.warning(
            f"Moved {task.acta.cache_key()} to DLQ: {error_message}"
        )
        return result.id

    def get_queue_stats(self) -> dict[str, Any]:
        """Get statistics about queue depths.

        Returns:
            Dict with queue name and approximate size
        """
        inspect = self.celery_app.control.inspect()

        stats = {
            "queues": {},
            "workers": {},
            "active_tasks": 0,
        }

        # Get queue statistics via Redis
        try:
            redis_client = self.celery_app.backend.client
            for queue_name in [
                settings.QUEUE_UNIVERSE,
                settings.QUEUE_PDF_DOWNLOAD,
                settings.QUEUE_FALLBACK_RETRY,
                settings.QUEUE_DEAD_LETTER,
            ]:
                key = f"celery.{queue_name}.q"
                size = redis_client.llen(key)
                stats["queues"][queue_name] = size
        except Exception as e:
            logger.warning(f"Could not get queue stats: {e}")

        # Get worker info
        try:
            active = inspect.active()
            if active:
                for worker, tasks in active.items():
                    stats["workers"][worker] = len(tasks)
                    stats["active_tasks"] += len(tasks)
        except Exception as e:
            logger.warning(f"Could not get active tasks: {e}")

        return stats

    def purge_queue(self, queue_name: str) -> int:
        """Purge all tasks from a queue.

        WARNING: This cannot be undone.

        Args:
            queue_name: Name of queue to purge

        Returns:
            Number of tasks purged
        """
        queue = self.celery_app.amqp.queues[queue_name]
        return queue.purge()

    def revoke_task(self, task_id: str, terminate: bool = False) -> bool:
        """Revoke a task by ID.

        Args:
            task_id: Celery task ID
            terminate: If True, kill running task

        Returns:
            True if task was revoked
        """
        self.celery_app.control.revoke(task_id, terminate=terminate)
        logger.info(f"Revoked task {task_id}")
        return True


# Convenience function to get default queue
def get_queue() -> IngestionQueue:
    """Get default ingestion queue instance."""
    return IngestionQueue()
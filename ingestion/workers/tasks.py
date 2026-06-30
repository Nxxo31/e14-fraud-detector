"""Celery tasks for E14 ingestion layer.

Defines the core download tasks: PDF download, universe refresh,
retry logic, and dead letter queue handler.
"""

import logging
from typing import Any

from celery import shared_task
from tenacity import retry_after, stop_after_attempt, wait_exponential

from ..config import settings
from ..services.downloader import E14Downloader
from ..services.queue import ActaIdentifier

logger = logging.getLogger(__name__)


# Create celery app for this module
celery_app = None  # Will be set by the module that initializes the app


def get_celery_app():
    """Get or create the Celery app."""
    global celery_app
    if celery_app is None:
        from ..services.queue import create_celery_app

        celery_app = create_celery_app()
    return celery_app


@shared_task(
    bind=True,
    max_retries=settings.MAX_RETRIES,
    default_retry_delay=settings.RETRY_BASE_DELAY,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=settings.RETRY_MAX_DELAY,
    retry_jitter=True,
)
def download_pdf(self, acta_data: dict[str, Any]) -> dict[str, Any]:
    """Download a single E-14 PDF from the Registraduria CDN.

    This task downloads a single PDF, validates it, and stores it.
    On failure, it retries with exponential backoff.

    Args:
        acta_data: Dict with dep, muni, zona, puesto, mesa, expected_name

    Returns:
        Dict with status, sha256, size_bytes, and task info
    """
    acta = ActaIdentifier.from_dict(acta_data)

    logger.info(f"Starting download for {acta.cache_key()} (attempt {self.request.retries + 1})")

    try:
        downloader = E14Downloader(impersonate="chrome")

        result = downloader.download_pdf(
            dep=acta.dep,
            muni=acta.muni,
            zona=acta.zona,
            puesto=acta.puesto,
            mesa=acta.mesa,
            expected_name=acta.expected_name,
        )

        downloader.close()

        if result.status == "success":
            logger.info(
                f"Successfully downloaded {acta.cache_key()}: "
                f"sha256={result.sha256[:16]}..., size={result.size_bytes}"
            )
            return {
                "status": "success",
                "acta": acta_data,
                "sha256": result.sha256,
                "size_bytes": result.size_bytes,
                "retries": self.request.retries,
            }
        else:
            # Download failed - will retry if retries remaining
            raise ValueError(f"Download failed: {result.error_message}")

    except Exception as exc:
        logger.warning(
            f"Download failed for {acta.cache_key()} "
            f"(attempt {self.request.retries + 1}/{settings.MAX_RETRIES}): {exc}"
        )
        raise self.retry(exc=exc)


@shared_task(bind=True)
def refresh_universe(self) -> dict[str, Any]:
    """Refresh the universe by downloading allTransmissionCodes.json.

    This task fetches the complete list of all electoral records,
    parsing it to identify new or missing actas.

    Returns:
        Dict with total count, new count, and download status
    """
    logger.info("Starting universe refresh task")

    try:
        downloader = E14Downloader(impersonate="chrome")
        transmission_codes = downloader.download_transmission_codes()
        downloader.close()

        if transmission_codes is None:
            raise ValueError("Failed to download transmission codes")

        # Parse and count
        # Structure: { "transmissioncodes": [ ... ] } or similar
        actas_list = transmission_codes.get("transmissioncodes", [])
        total_count = len(actas_list)

        logger.info(f"Universe refresh complete: {total_count} actas found")

        return {
            "status": "success",
            "total_actas": total_count,
            "transmission_codes": transmission_codes,
        }

    except Exception as exc:
        logger.error(f"Universe refresh failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True)
def retry_failed(self, batch_size: int = 100) -> dict[str, Any]:
    """Retry failed downloads from the fallback retry queue.

    This task processes the dead letter queue and retry queue to
    re-attempt downloads that previously failed.

    Args:
        batch_size: Maximum number of failed tasks to retry

    Returns:
        Dict with retry statistics
    """
    logger.info(f"Starting retry of failed downloads (batch_size={batch_size})")

    # This would typically:
    # 1. Query the database for failed downloads
    # 2. Re-enqueue them to the download queue
    # 3. Track retry statistics

    # Implementation depends on storage layer (not yet implemented)
    logger.info("Retry task executed (placeholder - storage layer not yet implemented)")

    return {
        "status": "success",
        "retried_count": 0,
        "batch_size": batch_size,
    }


@shared_task(bind=True)
def dlq_handler(self, dlq_data: dict[str, Any]) -> dict[str, Any]:
    """Handle items in the dead letter queue.

    This task is triggered when a download has exceeded max retries.
    It logs the failure and potentially alerts or stores for manual review.

    Args:
        dlq_data: Dict with acta info and error details

    Returns:
        Dict with DLQ handling result
    """
    acta_data = dlq_data.get("acta", {})
    error_message = dlq_data.get("error_message", "Unknown error")
    failed_at = dlq_data.get("failed_at", "Unknown")

    acta = ActaIdentifier.from_dict(acta_data) if acta_data else None
    acta_str = acta.cache_key() if acta else "unknown"

    logger.error(
        f"DLQ: {acta_str} failed permanently at {failed_at}. "
        f"Error: {error_message}"
    )

    # In a full implementation, this would:
    # 1. Store the failure in the database
    # 2. Send alert/notification
    # 3. Possibly trigger manual intervention

    return {
        "status": "dlq_recorded",
        "acta": acta_data,
        "error_message": error_message,
        "failed_at": failed_at,
    }


@shared_task
def enqueue_batch_downloads(actas: list[dict[str, Any]]) -> dict[str, Any]:
    """Enqueue a batch of download tasks.

    Helper task to enqueue multiple downloads at once.
    This is typically called by a scheduler.

    Args:
        actas: List of acta data dicts

    Returns:
        Dict with enqueue statistics
    """
    enqueued = 0
    failed = 0

    for acta_data in actas:
        try:
            download_pdf.apply_async(
                kwargs={"acta_data": acta_data},
                queue=settings.QUEUE_PDF_DOWNLOAD,
            )
            enqueued += 1
        except Exception as e:
            logger.warning(f"Failed to enqueue {acta_data}: {e}")
            failed += 1

    logger.info(f"Batch enqueue complete: {enqueued} enqueued, {failed} failed")

    return {
        "status": "complete",
        "enqueued": enqueued,
        "failed": failed,
        "total": len(actas),
    }
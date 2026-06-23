"""E14 Acquisition — Celery tasks.

Tasks are designed around GEOGRAPHIC BATCHES, not individual PDFs:
  - refresh_universe: fetches allTransmissionCodes.json, seeds DB
  - download_batch_by_municipality: all tables in ONE municipio
  - retry_failed_downloads: failed tables from last N hours

This avoids 122K individual jobs in the queue — each task processes
50-500 mesas in a single municipality.
"""

import logging
from datetime import datetime, timezone, timedelta

from celery import group, chord, chain
from sqlalchemy import func

from .celery_app import celery_app
from app.database import SessionLocal
from app.models import Table, Pdf, DownloadJob, JobStatus, AuditLog
from app.services.metadata import refresh_universe as _refresh_universe
from app.services.downloader import download_batch
from app.services.storage import StorageService
from app.monitoring.metrics import (
    universe_tables, universe_refresh_duration, download_requests,
    download_bytes, download_duration, download_errors, jobs_total,
    queue_depth,
)

log = logging.getLogger(__name__)


# ── 1. Universe Refresh ─────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    queue="refresh_universe",
    max_retries=3,
    retry_backoff=300,
    retry_jitter=True,
)
def refresh_universe(self):
    """Fetch allTransmissionCodes.json and upsert all table metadata.

    This is the ONLY task that populates the universe.
    Runs every 30 minutes during election night.
    """
    start = datetime.now(timezone.utc)
    log.info("Starting universe refresh")

    try:
        result = _refresh_universe()

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        universe_refresh_duration.observe(elapsed)
        universe_tables.set(result["total"])
        jobs_total.labels(job_type="refresh_universe", status="success").inc()

        # Record job
        _record_job("refresh_universe", "success", metadata={
            "total": result["total"],
            "inserted": result["inserted"],
            "updated": result["updated"],
            "duration_s": elapsed,
        })

        log.info(
            "Universe refresh complete: %d tables (inserted=%d, updated=%d, took=%.1fs)",
            result["total"], result["inserted"], result["updated"], elapsed,
        )
        return result

    except Exception as exc:
        log.error("Universe refresh failed: %s", exc)
        jobs_total.labels(job_type="refresh_universe", status="failure").inc()
        _record_job("refresh_universe", "failed", error_message=str(exc))
        raise self.retry(exc=exc)


# ── 2. Batch Download by Municipality ──────────────────────────────────────

@celery_app.task(
    bind=True,
    queue="download_batch",
    max_retries=2,
    retry_backoff=120,
)
def download_batch_by_municipality(self, dep_code: str, muni_code: str) -> dict:
    """Download ALL PDFs for one municipality.

    This is the atomic unit of work — a single celery task = one municipality.
    Typical municipalities have 50-500 mesas. At 8 req/s that's 6-60 seconds.

    Returns: {"dep": "01", "muni": "004", "downloaded": N, "failed": N, "bytes": N}
    """
    start = datetime.now(timezone.utc)
    task_id = self.request.id
    log.info("Starting municipality batch: dep=%s muni=%s", dep_code, muni_code)

    db = SessionLocal()
    try:
        tables = db.query(Table).filter(
            Table.dep_code == dep_code.zfill(2),
            Table.muni_code == muni_code.zfill(3),
            Table.pdf_status.in_(["pending", "error"]),
        ).all()

        if not tables:
            log.info("No pending tables for dep=%s muni=%s", dep_code, muni_code)
            return {"dep": dep_code, "muni": muni_code, "downloaded": 0, "failed": 0}

        log.info("Processing %d tables in dep=%s muni=%s", len(tables), dep_code, muni_code)

        result = download_batch(tables, max_workers=6)

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        download_duration.observe(elapsed)
        download_bytes.inc(result.total_bytes)
        download_requests.labels(status="success").inc(result.downloaded)
        download_requests.labels(status="failure").inc(result.failed)
        download_requests.labels(status="skipped").inc(result.skipped)

        jobs_total.labels(job_type="download_batch", status="success").inc()

        _record_job("download_batch", "success", metadata={
            "dep": dep_code,
            "muni": muni_code,
            "downloaded": result.downloaded,
            "failed": result.failed,
            "skipped": result.skipped,
            "bytes": result.total_bytes,
            "duration_s": elapsed,
        })

        log.info(
            "Municipality batch done: dep=%s muni=%s downloaded=%d failed=%d elapsed=%.1fs",
            dep_code, muni_code, result.downloaded, result.failed, elapsed,
        )
        return {
            "dep": dep_code,
            "muni": muni_code,
            "downloaded": result.downloaded,
            "failed": result.failed,
            "skipped": result.skipped,
            "bytes": result.total_bytes,
            "errors": [(tid, err) for tid, err in result.errors[:5]],
        }

    except Exception as exc:
        log.error("Municipality batch failed: dep=%s muni=%s: %s", dep_code, muni_code, exc)
        jobs_total.labels(job_type="download_batch", status="failure").inc()
        _record_job("download_batch", "failed", error_message=str(exc))
        raise self.retry(exc=exc)

    finally:
        db.close()


@celery_app.task(
    bind=True,
    queue="download_batch",
    max_retries=2,
)
def download_batch_by_department(self, dep_code: str) -> dict:
    """Download ALL PDFs for one department.

    Dispatches N municipality tasks and waits for all to complete.
    A department has 1-50 municipalities.
    """
    start = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        # Get all municipalities in this department
        muni_codes = db.query(Table.muni_code).filter(
            Table.dep_code == dep_code.zfill(2),
        ).distinct().all()

        muni_codes = [m[0] for m in muni_codes]
        log.info("Department %s has %d municipalities", dep_code, len(muni_codes))

        # Dispatch one municipality task per municipality
        dispatch_time = datetime.now(timezone.utc)
        muni_tasks = [
            download_batch_by_municipality.s(dep_code.zfill(2), m)
            for m in muni_codes
        ]

        # Execute all municipality tasks in parallel
        # Using chord so we wait for all to complete before returning
        # But we don't block the main process — we return immediately
        # The actual download happens asynchronously in workers

        # Actually, we want to WAIT for results in this task
        # so we can aggregate the results
        from celery import group as celery_group
        job = celery_group(muni_tasks)
        results = job.apply_async()

        # Wait for all municipality tasks to complete (with timeout)
        results.get(timeout=3600, disable_sync_subtasks=False)

        # Aggregate results
        total_downloaded = 0
        total_failed = 0
        total_bytes = 0
        for r in results.results:
            if r.ready() and r.successful():
                result = r.result
                total_downloaded += result.get("downloaded", 0)
                total_failed += result.get("failed", 0)
                total_bytes += result.get("bytes", 0)

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        log.info(
            "Department batch done: dep=%s downloaded=%d failed=%d elapsed=%.1fs",
            dep_code, total_downloaded, total_failed, elapsed,
        )
        return {
            "dep": dep_code,
            "downloaded": total_downloaded,
            "failed": total_failed,
            "bytes": total_bytes,
            "duration_s": elapsed,
        }

    except Exception as exc:
        log.error("Department batch failed: dep=%s: %s", dep_code, exc)
        raise self.retry(exc=exc)

    finally:
        db.close()


@celery_app.task(
    bind=True,
    queue="download_batch",
)
def dispatch_all_pending(self, limit: int = 5000) -> dict:
    """Dispatch download tasks for all pending tables, grouped by municipality.

    This is the MAIN entry point for bulk downloads.
    It finds all municipalities with pending tables and dispatches one
    municipality task per municipality (not per table!).

    This is the key design: 122K tables → ~1100 municipality tasks,
    not 122K individual tasks.
    """
    db = SessionLocal()
    try:
        # Find municipalities with pending/error tables
        pending = db.query(
            Table.dep_code,
            Table.muni_code,
            func.count(Table.id).label("pending_count"),
        ).filter(
            Table.pdf_status.in_(["pending", "error"]),
        ).group_by(
            Table.dep_code, Table.muni_code
        ).limit(limit).all()

        if not pending:
            log.info("No pending tables to dispatch")
            return {"dispatched": 0, "municipalities": 0}

        # Dispatch one task per municipality
        tasks = [
            download_batch_by_municipality.s(row.dep_code, row.muni_code)
            for row in pending
        ]

        from celery import group as celery_group
        job = celery_group(tasks)
        result = job.apply_async()

        log.info(
            "Dispatched %d municipality tasks for %d pending tables",
            len(tasks), sum(row.pending_count for row in pending),
        )

        queue_depth.labels(queue="download_batch").set(len(tasks))

        return {
            "dispatched": len(tasks),
            "total_pending_tables": sum(row.pending_count for row in pending),
        }

    finally:
        db.close()


# ── 3. Retry Failed ─────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    queue="retry_failed",
    max_retries=2,
)
def retry_failed_downloads(self, hours: int = 24, limit: int = 1000) -> dict:
    """Retry failed downloads from the last N hours.

    Groups failed tables by municipality and re-dispatches.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        failed = db.query(
            Table.dep_code,
            Table.muni_code,
            func.count(Table.id).label("failed_count"),
        ).filter(
            Table.pdf_status == "error",
            Table.updated_at >= cutoff,
        ).group_by(
            Table.dep_code, Table.muni_code
        ).limit(limit).all()

        if not failed:
            log.info("No failed downloads to retry")
            return {"retried": 0}

        tasks = [
            download_batch_by_municipality.s(row.dep_code, row.muni_code)
            for row in failed
        ]

        from celery import group as celery_group
        job = celery_group(tasks)
        job.apply_async()

        log.info("Dispatched %d retry tasks for %d failed tables", len(tasks), sum(r.failed_count for r in failed))
        return {"retried": len(tasks), "total_failed_tables": sum(r.failed_count for r in failed)}

    finally:
        db.close()


# ── 4. Evict Expired PDFs ───────────────────────────────────────────────────

@celery_app.task(bind=True, queue="health_check")
def evict_expired_pdfs(self) -> dict:
    """Delete expired PDFs from hot storage and update database."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        expired = db.query(Pdf).filter(
            Pdf.expires_at < now,
            Pdf.storage_backend == "minio",
        ).limit(1000).all()

        if not expired:
            return {"evicted": 0}

        storage = StorageService()
        evicted = 0
        for pdf in expired:
            try:
                storage.delete(pdf.storage_path, bucket="hot")
                pdf.expires_at = None  # Mark as evicted
                db.add(pdf)
                evicted += 1
            except Exception as exc:
                log.warning("Failed to evict PDF %s: %s", pdf.storage_path, exc)

        db.commit()
        log.info("Evicted %d expired PDFs from hot storage", evicted)
        return {"evicted": evicted}

    finally:
        db.close()


# ── 5. Health Check ─────────────────────────────────────────────────────────

@celery_app.task(bind=True, queue="health_check")
def health_check(self) -> dict:
    """Periodic health check — verifies DB + storage connectivity."""
    from app.database import engine
    db = SessionLocal()
    try:
        db.execute("SELECT 1")
        storage = StorageService()
        storage.client.bucket_exists("e14-pdfs-hot")
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        log.error("Health check failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _record_job(job_type: str, status: str, error_message: str = None, metadata: dict = None):
    """Record a job in the job_status table."""
    db = SessionLocal()
    try:
        job = JobStatus(
            job_type=job_type,
            status=status,
            metadata=metadata,
            error_message=error_message,
        )
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
"""E14 Analysis — Celery tasks."""

import logging
from celery import chord, group
from datetime import datetime, timezone
from sqlalchemy import func

from .celery_app import celery_app
from .database import SessionLocal
from .models import Table, AnalysisResult
from .services.pipeline import run_analysis_pipeline

log = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 120


@celery_app.task(
    bind=True,
    queue="analysis",
    max_retries=MAX_RETRIES,
    retry_backoff=RETRY_DELAY,
    retry_jitter=True,
)
def analyze_single(self, table_id: int) -> dict:
    """Analyze one E-14. Returns risk score and anomaly count."""
    start = datetime.now(timezone.utc)
    log.info("Analyzing table %d [attempt %d]", table_id, self.request.retries + 1)

    try:
        result = run_analysis_pipeline(table_id)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        log.info(
            "Analysis done: table=%d risk=%s score=%.1f anomalies=%d elapsed=%.1fs",
            table_id, result.risk_score.level, result.risk_score.score,
            result.validation_result.anomaly_count, elapsed,
        )

        return {
            "table_id": table_id,
            "risk_level": result.risk_score.level,
            "risk_score": result.risk_score.score,
            "anomaly_count": result.validation_result.anomaly_count,
            "signature_status": result.signature_result.overall_status,
            "ocr_confidence": (result.page1_ocr.overall_confidence + result.page2_ocr.overall_confidence) / 2,
            "elapsed_s": round(elapsed, 1),
            "analysis_id": result.analysis_db_id,
        }

    except Exception as exc:
        log.error("Analysis failed: table=%d: %s", table_id, exc)
        if self.request.retries < MAX_RETRIES - 1:
            raise self.retry(exc=exc)
        # Max retries reached — record failure in DB
        _record_analysis_failure(table_id, str(exc))
        return {"table_id": table_id, "error": str(exc)}


@celery_app.task(
    bind=True,
    queue="analysis",
)
def analyze_batch(self, table_ids: list[int]) -> dict:
    """Analyze a batch of E-14s in parallel.

    This is the entry point for bulk analysis. Dispatches N analyze_single
    tasks and waits for all to complete.
    """
    if not table_ids:
        return {"analyzed": 0, "errors": 0}

    log.info("Analyzing batch of %d tables", len(table_ids))

    # Dispatch all in parallel
    tasks = [analyze_single.s(tid) for tid in table_ids]
    job = group(tasks)
    results = job.apply_async()

    # Wait for all (with 10-minute timeout per 100 tables)
    timeout = max(600, len(table_ids) * 6)  # 6s per table estimate
    results.get(timeout=timeout, disable_sync_subtasks=False)

    # Aggregate
    analyzed = sum(1 for r in results.results if r.ready() and r.successful())
    errors = len(table_ids) - analyzed

    return {"analyzed": analyzed, "errors": errors, "total": len(table_ids)}


@celery_app.task(
    bind=True,
    queue="analysis",
)
def analyze_department(self, dep_code: str) -> dict:
    """Analyze all tables in a department.

    Finds all tables without analysis results and dispatches in batches.
    """
    db = SessionLocal()
    try:
        # Find tables in this department without analysis
        unanalyzed = db.query(Table.id).filter(
            Table.dep_code == dep_code.zfill(2),
            Table.pdf_status == "cached",
        ).outerjoin(
            AnalysisResult, Table.id == AnalysisResult.table_id
        ).filter(
            AnalysisResult.id.is_(None)
        ).limit(5000).all()

        table_ids = [t[0] for t in unanalyzed]
        if not table_ids:
            return {"dep": dep_code, "analyzed": 0, "message": "No pending tables"}

        log.info("Department %s: %d tables to analyze", dep_code, len(table_ids))

        # Process in sub-batches of 50 for better parallelism
        batch_size = 50
        batches = [table_ids[i:i+batch_size] for i in range(0, len(table_ids), batch_size)]

        for i, batch in enumerate(batches):
            analyze_batch.delay(batch)
            log.info("Dispatched batch %d/%d for dep %s", i+1, len(batches), dep_code)

        return {
            "dep": dep_code,
            "dispatched": len(table_ids),
            "batches": len(batches),
        }

    finally:
        db.close()


@celery_app.task(bind=True, queue="health")
def analyze_health_check(self) -> dict:
    """Verify analysis pipeline health."""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _record_analysis_failure(table_id: int, error: str):
    """Record a permanent failure in the analysis_results table."""
    db = SessionLocal()
    try:
        # Check if we already have a failure record
        existing = db.query(AnalysisResult).filter(
            AnalysisResult.table_id == table_id
        ).first()
        if existing:
            return  # Already recorded

        result = AnalysisResult(
            table_id=table_id,
            pdf_sha256="ERROR",
            risk_score=100.0,
            risk_level="CRITICAL",
            anomaly_count=1,
            math_valid=False,
        )
        db.add(result)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
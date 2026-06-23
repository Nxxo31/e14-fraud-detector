"""E14 Analysis — Full analysis pipeline.

Orchestrates: fetch PDF → render pages → signature detection → OCR → validation → score → store.

This is the core service used by Celery workers. It receives a table_id from the acquisition
queue and runs the complete analysis pipeline.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..config import DATABASE_URL
from ..database import SessionLocal
from .models import AnalysisResult, Anomaly as DBAnomaly, SignatureResult
from .services.pdf_renderer import render_pdf_pages, validate_image_quality, PdfRenderError
from .services.signature_detector import detect_signatures
from .services.ocr_engine import extract_page_votes
from .services.validation import validate_mathematics, calculate_risk_score, Anomaly as ValAnomaly
from .services.storage import AnalysisStorage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisOutput:
    """Complete output from the analysis pipeline for one E-14."""
    table_id          : int
    pdf_sha256         : str
    signature_result   : object      # SignatureValidationResult
    page1_ocr          : object      # OcrResult
    page2_ocr          : object      # OcrResult
    validation_result  : object      # ValidationResult
    risk_score         : object      # RiskScore
    analysis_db_id     : int         # database primary key of stored result


def run_analysis_pipeline(table_id: int) -> AnalysisOutput:
    """Main entry point: run complete analysis on one E-14.

    1. Fetch PDF from MinIO storage
    2. Render all 3 pages (300 DPI)
    3. Run signature detection on page 3
    4. Run OCR on pages 1-2
    5. Validate mathematics
    6. Calculate risk score
    7. Store results in PostgreSQL

    Returns:
        AnalysisOutput with all results and the database record ID

    Raises:
        Various exceptions on failure — caller handles retries.
    """
    db = SessionLocal()
    try:
        # ── Step 1: Get table and PDF ─────────────────────────────────────────
        from .models import Table
        from .database import engine as acq_engine

        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            raise ValueError(f"Table {table_id} not found")
        if not table.pdf_sha256:
            raise ValueError(f"No PDF available for table {table_id}")

        # Get the storage path from the acquisition database
        with acq_engine.connect() as acq_conn:
            result = acq_conn.execute(
                f"SELECT storage_path FROM pdfs WHERE sha256 = '{table.pdf_sha256}' LIMIT 1"
            )
            row = result.fetchone()
            if not row:
                raise ValueError(f"PDF not in acquisition storage: sha256={table.pdf_sha256}")
            storage_path = row[0]

        storage = AnalysisStorage()
        pdf_bytes = storage.get_pdf_by_path(storage_path)
        if not pdf_bytes:
            raise ValueError(f"PDF not in storage: sha256={table.pdf_sha256}")

        # ── Step 2: Render all 3 pages ────────────────────────────────────────
        try:
            pages = render_pdf_pages(pdf_bytes, pages=[1, 2, 3], dpi=300)
        except PdfRenderError as exc:
            raise RuntimeError(f"PDF render failed: {exc}") from exc

        page_images = {p.page_number: p.image for p in pages}

        # ── Step 3: Signature detection (page 3) ───────────────────────────────
        sig_result = detect_signatures(page_images[3])

        # ── Step 4: OCR (pages 1 and 2) ───────────────────────────────────────
        page1_ocr = extract_page_votes(page_images[1], page_number=1)
        page2_ocr = extract_page_votes(page_images[2], page_number=2)

        # ── Step 5: Mathematical validation ───────────────────────────────────
        validation_result = validate_mathematics(page1_ocr, page2_ocr)

        # ── Step 6: Risk scoring ───────────────────────────────────────────────
        avg_ocr_conf = (page1_ocr.overall_confidence + page2_ocr.overall_confidence) / 2
        risk_score = calculate_risk_score(sig_result, validation_result, avg_ocr_conf)

        # ── Step 7: Persist results ────────────────────────────────────────────
        result_id = _persist_results(
            db, table_id, table.pdf_sha256, sig_result,
            page1_ocr, page2_ocr, validation_result, risk_score,
        )

        log.info(
            "Analysis complete: table=%d risk=%s score=%.1f anomalies=%d",
            table_id, risk_score.level, risk_score.score, validation_result.anomaly_count,
        )

        return AnalysisOutput(
            table_id=table_id,
            pdf_sha256=table.pdf_sha256,
            signature_result=sig_result,
            page1_ocr=page1_ocr,
            page2_ocr=page2_ocr,
            validation_result=validation_result,
            risk_score=risk_score,
            analysis_db_id=result_id,
        )

    finally:
        db.close()


def _persist_results(
    db: Session,
    table_id: int,
    pdf_sha256: str,
    sig_result,
    page1_ocr,
    page2_ocr,
    validation_result,
    risk_score,
) -> int:
    """Store analysis output in PostgreSQL."""
    now = datetime.now(timezone.utc)

    # Candidate votes
    all_candidates = list(page1_ocr.candidates) + list(page2_ocr.candidates)

    # Summary (from page 2)
    summary = page2_ocr.summary

    # Create analysis result record
    result = AnalysisResult(
        table_id=table_id,
        pdf_sha256=pdf_sha256,
        signature_status=sig_result.overall_status,
        signatures_found=sig_result.signatures_found,
        signatures_expected=sig_result.signatures_expected,
        signature_ink_densities=[b.ink_density for b in sig_result.boxes],
        signature_risk=sig_result.max_risk,
        ocr_confidence=round((page1_ocr.overall_confidence + page2_ocr.overall_confidence) / 2, 4),
        total_votes=summary.total_votes if summary else None,
        blank_votes=summary.blank_votes if summary else None,
        null_votes=summary.null_votes if summary else None,
        unmarked_votes=summary.unmarked_votes if summary else None,
        candidate_votes={
            c.candidate_number: _slots_to_int(c.slots)
            for c in all_candidates
        },
        candidate_confidences={
            c.candidate_number: c.total_confidence
            for c in all_candidates
        },
        risk_score=risk_score.score,
        risk_level=risk_score.level,
        anomaly_count=risk_score.anomaly_count,
        math_valid=validation_result.valid,
        processed_at=now,
    )
    db.add(result)
    db.flush()  # get result.id

    # Store anomalies
    for anomaly in validation_result.anomalies:
        db_anomaly = DBAnomaly(
            analysis_id=result.id,
            table_id=table_id,
            rule=anomaly.rule,
            severity=anomaly.severity,
            message=anomaly.message,
            confidence=anomaly.confidence,
            page_number=anomaly.page,
            details=anomaly.details,
        )
        db.add(db_anomaly)

    # Update table's risk level
    from .models import Table
    table = db.query(Table).filter(Table.id == table_id).first()
    if table:
        table.risk_level = risk_score.level
        table.risk_score = risk_score.score

    db.commit()
    return result.id


def _slots_to_int(slots) -> int:
    """Convert VoteSlot tuple to integer."""
    digits = []
    for slot in slots:
        if slot.digit is not None:
            digits.append(str(slot.digit))
        else:
            digits.append('0')
    return int(''.join(digits)) if digits else 0
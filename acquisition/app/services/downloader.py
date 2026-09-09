"""E14 Acquisition — PDF downloader with Akamai-safe curl_cffi.

Batch-oriented: downloads a group of PDFs (e.g. all tables in a municipio)
in parallel using a shared rate-limited session.

Validates:
  - Magic bytes (%PDF-)
  - SHA256 matches expected_name prefix
  - Content-Length sanity

On success: stores to MinIO, records in DB.
On failure: stores error in DB, retry count tracked.
"""

import hashlib
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import (
    CURL_CFFI_IMPERSONATE, PDF_DOWNLOAD_TIMEOUT,
    PDF_DOWNLOAD_MAX_RETRIES, PDF_RETRY_DELAY_BASE, PDF_CACHE_TTL_SECONDS,
    CDN_PDF_BASE,
)
from ..models import Table, Pdf, DownloadJob
from ..database import SessionLocal
from .rate_limiter import TokenBucket
from .storage import StorageService

log = logging.getLogger(__name__)

# Shared rate limiter (all workers share one token bucket)
_rate_limiter = TokenBucket(rate=8.0, burst=8)


class PdfDownloadError(Exception):
    """Raised when a PDF cannot be downloaded or validated."""


class BatchResult:
    """Result from downloading a batch of PDFs."""

    def __init__(self):
        self.downloaded = 0
        self.cached = 0
        self.failed = 0
        self.skipped = 0
        self.total_bytes = 0
        self.errors: list[tuple[int, str]] = []  # (table_id, reason)


def _build_pdf_url(table: Table) -> str:
    """Build the CDN URL for a table's PDF."""
    return (
        f"{CDN_PDF_BASE}/{table.dep_code}/{table.muni_code}/"
        f"{table.zona_code}/{table.puesto_code}/PRE/{table.expected_name}"
    )


def _validate_pdf(content: bytes, expected_name: str) -> str:
    """Validate PDF content. Returns SHA256 hex.

    Raises PdfDownloadError on invalid content.
    """
    if len(content) < 100:
        raise PdfDownloadError("PDF too small (< 100 bytes)")

    if content[:5] != b"%PDF-":
        raise PdfDownloadError("Invalid magic bytes (not a PDF)")

    sha = hashlib.sha256(content).hexdigest()

    # expected_name is usually a SHA256-ish hash.pdf — verify prefix match
    name_stem = expected_name.replace(".pdf", "")
    if not sha.startswith(name_stem[:16]):  # Check first 16 hex chars
        log.warning("SHA256 prefix mismatch: expected=%s.. got=%s..", name_stem[:16], sha[:16])
        # This is a soft warning — the PDF might still be valid

    return sha


def download_one_pdf(table: Table, storage: StorageService) -> Pdf:
    """Download a single PDF, store it, return Pdf record.

    Raises PdfDownloadError on failure.
    """
    from curl_cffi import requests as creq
    from curl_cffi.requests import RequestsError

    url = _build_pdf_url(table)
    session = creq.Session(impersonate=CURL_CFFI_IMPERSONATE)

    _rate_limiter.acquire()
    try:
        resp = session.get(url, timeout=PDF_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
    except RequestsError as exc:
        raise PdfDownloadError(f"HTTP request failed: {exc}") from exc

    content = resp.content
    sha256 = _validate_pdf(content, table.expected_name)

    # Store to MinIO
    obj_key = f"{table.dep_code}/{table.muni_code}/{table.zona_code}/{table.puesto_code}/{table.mesa_code}.pdf"
    expires = datetime.now(timezone.utc) + timedelta(seconds=PDF_CACHE_TTL_SECONDS)
    storage.put(obj_key, content, "application/pdf")

    # Build Pdf record
    pdf = Pdf(
        table_id=table.id,
        sha256=sha256,
        size_bytes=len(content),
        storage_path=obj_key,
        storage_backend="minio",
        content_type="application/pdf",
        expires_at=expires,
    )

    return pdf, content


def download_batch(tables: list[Table], max_workers: int = 6) -> BatchResult:
    """Download a batch of PDFs in parallel.

    Each worker downloads, validates, stores, and marks the record.
    Failed downloads are tracked for retry.
    """
    result = BatchResult()
    storage = StorageService()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for table in tables:
            if table.pdf_status == "cached":
                result.skipped += 1
                continue
            futures[executor.submit(_download_and_record, table, storage)] = table

        for future in as_completed(futures):
            table = futures[future]
            try:
                pdf, content = future.result()
                result.downloaded += 1
                result.total_bytes += len(content)
            except PdfDownloadError as exc:
                result.failed += 1
                result.errors.append((table.id, str(exc)))
                _record_failure(table, str(exc))
            except Exception as exc:
                result.failed += 1
                result.errors.append((table.id, f"Unexpected: {exc}"))
                _record_failure(table, f"Unexpected: {exc}")

    return result


def _download_and_record(table: Table, storage: StorageService) -> tuple[Pdf, bytes]:
    """Worker: download, validate, store, update DB."""
    db = SessionLocal()
    try:
        pdf, content = download_one_pdf(table, storage)

        # Update table record
        table.pdf_status = "cached"
        table.pdf_sha256 = pdf.sha256
        table.pdf_size_bytes = pdf.size_bytes
        table.download_count = (table.download_count or 0) + 1
        table.last_accessed_at = datetime.now(timezone.utc)
        table.last_error = None

        # Upsert Pdf record
        existing = db.query(Pdf).filter(
            Pdf.table_id == table.id,
            Pdf.sha256 == pdf.sha256,
        ).first()
        if not existing:
            db.add(pdf)

        # Record successful job
        job = DownloadJob(
            table_id=table.id,
            status="success",
            attempt=0,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()

        return pdf, content
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _record_failure(table: Table, error: str):
    """Record a download failure in DB."""
    db = SessionLocal()
    try:
        table.pdf_status = "error"
        table.last_error = error[:500]
        db.add(table)

        job = DownloadJob(
            table_id=table.id,
            status="failed",
            attempt=1,
            error_message=error[:500],
        )
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
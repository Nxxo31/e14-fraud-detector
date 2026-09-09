"""E14 Acquisition — PDF download/serve endpoint."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Table, Pdf
from ..services.downloader import download_one_pdf
from ..services.storage import StorageService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/tables", tags=["pdfs"])


@router.get("/{table_id}/pdf")
def serve_pdf(table_id: int, db: Session = Depends(get_db)):
    """Serve a table's PDF. Returns from cache if available, downloads if not.

    Response headers:
      Content-Type: application/pdf
      X-Cache: HIT or MISS
      X-SHA256: hex digest
    """
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    # Try cache first
    if table.pdf_status == "cached" and table.pdf_sha256:
        pdf_record = db.query(Pdf).filter(
            Pdf.table_id == table.id,
            Pdf.sha256 == table.pdf_sha256,
        ).first()
        if pdf_record and pdf_record.expires_at and pdf_record.expires_at > datetime.now(timezone.utc):
            storage = StorageService()
            data = storage.get(pdf_record.storage_path)
            if data:
                table.last_accessed_at = datetime.now(timezone.utc)
                db.commit()
                return Response(
                    content=data,
                    media_type="application/pdf",
                    headers={
                        "X-Cache": "HIT",
                        "X-SHA256": table.pdf_sha256,
                        "Content-Length": str(len(data)),
                    },
                )
        # Cache expired or missing from storage — re-download
        log.info("Cache miss or expired for table %d, re-downloading", table_id)

    # Uncacheable or first-time: download now
    try:
        storage = StorageService()
        pdf_record, content = download_one_pdf(table, storage)

        # Update table
        table.pdf_status = "cached"
        table.pdf_sha256 = pdf_record.sha256
        table.pdf_size_bytes = pdf_record.size_bytes
        table.download_count = (table.download_count or 0) + 1
        table.last_accessed_at = datetime.now(timezone.utc)

        # Store Pdf record if new
        existing = db.query(Pdf).filter(
            Pdf.table_id == table.id,
            Pdf.sha256 == pdf_record.sha256,
        ).first()
        if not existing:
            db.add(pdf_record)
        db.commit()

        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "X-Cache": "MISS",
                "X-SHA256": pdf_record.sha256,
                "Content-Length": str(len(content)),
            },
        )

    except Exception as exc:
        log.error("Failed to download PDF for table %d: %s", table_id, exc)
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}")
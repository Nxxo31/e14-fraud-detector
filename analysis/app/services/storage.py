"""E14 Analysis — Database connection and storage service."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import io
import logging

from .config import DATABASE_URL, MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET_HOT

# ── Database ─────────────────────────────────────────────────────────────────
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Storage ──────────────────────────────────────────────────────────────────
_log = logging.getLogger(__name__)

_minio = None


def _get_minio():
    global _minio
    if _minio is None:
        from minio import Minio
        _minio = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return _minio


class AnalysisStorage:
    """Read PDFs from MinIO (hot storage)."""

    def get_pdf(self, sha256: str) -> bytes:
        """Get PDF by SHA256. Returns None if not found."""
        client = _get_minio()
        # PDF path in MinIO: {dep}/{muni}/{zona}/{puesto}/{mesa}.pdf
        # We need to search by SHA256... but the path doesn't contain SHA.
        # This is a design problem: we stored by path, not by SHA.
        # Fix: query DB for storage_path first, then fetch.
        #
        # This method is only called with sha256 as key, so we need
        # to scan. For MVP, we require storage_path in the PDF record.
        raise NotImplementedError("Use get_pdf_by_path()")

    def get_pdf_by_path(self, storage_path: str) -> bytes:
        """Get PDF by MinIO object key."""
        client = _get_minio()
        try:
            response = client.get_object(MINIO_BUCKET_HOT, storage_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as exc:
            _log.debug("PDF not found in MinIO: %s: %s", storage_path, exc)
            return None

    def pdf_exists(self, storage_path: str) -> bool:
        """Check if PDF exists in storage."""
        client = _get_minio()
        try:
            client.stat_object(MINIO_BUCKET_HOT, storage_path)
            return True
        except Exception:
            return False
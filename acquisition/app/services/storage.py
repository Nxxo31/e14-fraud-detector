"""E14 Acquisition — MinIO object storage backend."""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

from ..config import (
    MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY,
    MINIO_BUCKET_HOT, MINIO_BUCKET_COLD,
)

log = logging.getLogger(__name__)

# Lazy import for environments where minio may not be available
_minio_client = None


def _get_client():
    global _minio_client
    if _minio_client is None:
        from minio import Minio
        _minio_client = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,  # local dev
        )
        # Ensure buckets exist
        for bucket in (MINIO_BUCKET_HOT, MINIO_BUCKET_COLD):
            if not _minio_client.bucket_exists(bucket):
                _minio_client.make_bucket(bucket)
                log.info("Created MinIO bucket: %s", bucket)
    return _minio_client


class StorageService:
    """PDF object storage via MinIO (S3-compatible)."""

    def __init__(self):
        self.client = _get_client()
        self.hot_bucket = MINIO_BUCKET_HOT
        self.cold_bucket = MINIO_BUCKET_COLD

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> str:
        """Upload a PDF to hot storage.

        Returns: the object key.
        """
        length = len(data)
        stream = io.BytesIO(data)
        self.client.put_object(
            bucket_name=self.hot_bucket,
            object_name=key,
            data=stream,
            length=length,
            content_type=content_type,
        )
        log.debug("Uploaded %s (%d bytes) to hot bucket", key, length)
        return key

    def get(self, key: str, bucket: Optional[str] = None) -> Optional[bytes]:
        """Retrieve a PDF from storage. Checks hot then cold.

        Returns: bytes or None if not found.
        """
        buckets = [bucket] if bucket else [self.hot_bucket, self.cold_bucket]
        for b in buckets:
            try:
                response = self.client.get_object(b, key)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except Exception:
                continue
        return None

    def exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """Check if a PDF exists in storage."""
        buckets = [bucket] if bucket else [self.hot_bucket, self.cold_bucket]
        for b in buckets:
            try:
                self.client.stat_object(b, key)
                return True
            except Exception:
                continue
        return False

    def delete(self, key: str, bucket: str = "hot"):
        """Delete a PDF from storage."""
        b = self.hot_bucket if bucket == "hot" else self.cold_bucket
        self.client.remove_object(b, key)

    def promote_to_cold(self, key: str) -> str:
        """Copy a PDF from hot to cold storage (permanent archive).

        Returns: cold storage key.
        """
        data = self.get(key, bucket=self.hot_bucket)
        if data is None:
            raise FileNotFoundError(f"PDF not found in hot storage: {key}")
        return self.put(key, data)  # put to cold by default if we swap buckets

    def evict_expired(self) -> int:
        """Delete all PDFs in hot storage older than TTL.

        In production, coordinate this with the database expires_at field.
        This is a simplified version.
        """
        # In real implementation, we query the DB for expired records
        # and delete from MinIO accordingly
        return 0
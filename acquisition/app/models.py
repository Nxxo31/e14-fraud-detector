"""E14 Acquisition — Database models"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, BigInteger, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Table(Base):
    """E14 electoral table (mesa). Core entity: one row per mesa."""

    __tablename__ = "tables"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    dep_code        = Column(String(2), nullable=False)
    muni_code       = Column(String(3), nullable=False)
    zona_code       = Column(String(3), nullable=False)
    puesto_code     = Column(String(2), nullable=False)
    mesa_code       = Column(String(3), nullable=False)
    corp_code       = Column(String(3), nullable=False, default="001")
    expected_name   = Column(String(64), nullable=False)
    id_stand        = Column(String(20))
    id_transmission = Column(BigInteger)
    transmission_status = Column(Integer)

    pdf_url         = Column(Text)

    # Denormalized names (from departmentsTree.json)
    dep_name        = Column(String(255))
    muni_name       = Column(String(255))
    zona_name       = Column(String(255))
    puesto_name     = Column(String(255))

    # Tracking
    pdf_status      = Column(String(20), nullable=False, default="pending")
    pdf_sha256      = Column(String(64))
    pdf_size_bytes  = Column(Integer)
    download_count  = Column(Integer, nullable=False, default=0)
    last_error      = Column(Text)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_accessed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("dep_code", "muni_code", "zona_code", "puesto_code", "mesa_code"),
    )


class Pdf(Base):
    """PDF storage record. One per successful download."""

    __tablename__ = "pdfs"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id        = Column(BigInteger, ForeignKey("tables.id"), nullable=False)
    sha256          = Column(String(64), nullable=False)
    size_bytes      = Column(Integer, nullable=False)
    storage_path    = Column(Text, nullable=False)
    storage_backend = Column(String(20), nullable=False, default="minio")
    content_type    = Column(String(50), default="application/pdf")
    expires_at      = Column(DateTime(timezone=True))

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    table = relationship("Table")


class DownloadJob(Base):
    """Download job tracking. One per download attempt."""

    __tablename__ = "download_jobs"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id        = Column(BigInteger, ForeignKey("tables.id"), nullable=False)
    celery_task_id  = Column(String(64))

    status          = Column(String(20), nullable=False, default="queued")
    attempt         = Column(Integer, nullable=False, default=0)
    max_attempts    = Column(Integer, nullable=False, default=5)

    started_at      = Column(DateTime(timezone=True))
    completed_at    = Column(DateTime(timezone=True))
    duration_ms     = Column(Integer)

    error_message   = Column(Text)
    worker_id       = Column(String(64))

    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("table_id", "attempt"),
    )


class JobStatus(Base):
    """High-level job status (universe refresh, batch downloads)."""

    __tablename__ = "job_status"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    job_type        = Column(String(50), nullable=False)
    celery_task_id  = Column(String(64))

    status          = Column(String(20), nullable=False, default="queued")
    progress_total  = Column(Integer)
    progress_done   = Column(Integer)

    started_at      = Column(DateTime(timezone=True))
    completed_at    = Column(DateTime(timezone=True))
    error_message   = Column(Text)

    metadata        = Column(JSON)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Audit trail."""

    __tablename__ = "audit_logs"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type      = Column(String(50), nullable=False)
    table_id        = Column(BigInteger, ForeignKey("tables.id"))
    details         = Column(JSON)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
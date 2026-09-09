"""E14 Acquisition — Pydantic schemas"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TableOut(BaseModel):
    """Table response schema."""

    id              : int
    dep_code        : str
    dep_name        : Optional[str] = None
    muni_code       : str
    muni_name       : Optional[str] = None
    zona_code       : str
    zona_name       : Optional[str] = None
    puesto_code     : str
    puesto_name     : Optional[str] = None
    mesa_code       : str
    expected_name   : str
    pdf_status      : str
    pdf_sha256      : Optional[str] = None
    pdf_size_bytes  : Optional[int] = None
    created_at      : datetime

    class Config:
        from_attributes = True


class TableDetail(TableOut):
    """Detailed table response with download history."""

    download_count  : int
    last_error      : Optional[str] = None
    updated_at      : datetime
    last_accessed_at: Optional[datetime] = None


class TableList(BaseModel):
    """Paginated table list."""

    total   : int
    page    : int
    per_page: int
    tables  : list[TableOut]


class JobStatusOut(BaseModel):
    """Job status response."""

    id              : int
    job_type        : str
    status          : str
    progress_total  : Optional[int] = None
    progress_done   : Optional[int] = None
    started_at      : Optional[datetime] = None
    completed_at    : Optional[datetime] = None
    error_message   : Optional[str] = None
    created_at      : datetime


class StatsOut(BaseModel):
    """System statistics."""

    total_tables        : int
    pdfs_downloaded     : int
    pdfs_pending        : int
    pdfs_failed         : int
    total_size_bytes    : int
    active_jobs         : int
    download_rate_hourly: float


class DownloadJobOut(BaseModel):
    """Download job tracking response."""

    id              : int
    table_id        : int
    status          : str
    attempt         : int
    max_attempts    : int
    started_at      : Optional[datetime] = None
    completed_at    : Optional[datetime] = None
    error_message   : Optional[str] = None
    created_at      : datetime
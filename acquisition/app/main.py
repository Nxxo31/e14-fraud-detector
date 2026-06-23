"""E14 Acquisition — FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .database import engine, Base
from .routers import tables, pdfs
from . import monitoring

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    Base.metadata.create_all(bind=engine)
    log.info("Database tables ensured")
    yield
    # Shutdown
    log.info("Shutting down E14 Acquisition API")


app = FastAPI(
    title="E14 Acquisition API",
    description="Data infrastructure for E14 electoral form acquisition",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tables.router, prefix="/api/v1")
app.include_router(pdfs.router, prefix="/api/v1")

# Prometheus metrics
monitoring.setup_metrics(app)


@app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "e14-acquisition"}


@app.get("/api/v1/stats")
async def stats():
    """System statistics."""
    from .database import SessionLocal
    from .models import Table, Pdf, DownloadJob, JobStatus

    db = SessionLocal()
    try:
        total = db.query(Table).count()
        cached = db.query(Table).filter(Table.pdf_status == "cached").count()
        pending = db.query(Table).filter(Table.pdf_status == "pending").count()
        error = db.query(Table).filter(Table.pdf_status == "error").count()

        total_size = db.query(text("COALESCE(SUM(pdf_size_bytes), 0)")).select_from(Pdf).scalar() or 0

        active_jobs = db.query(JobStatus).filter(
            JobStatus.status.in_(["queued", "running"])
        ).count()

        recent_jobs = db.query(JobStatus).order_by(JobStatus.created_at.desc()).limit(5).all()

        return {
            "total_tables": total,
            "pdfs_downloaded": cached,
            "pdfs_pending": pending,
            "pdfs_failed": error,
            "total_size_bytes": int(total_size),
            "active_jobs": active_jobs,
            "recent_jobs": [
                {"id": j.id, "job_type": j.job_type, "status": j.status, "created_at": j.created_at}
                for j in recent_jobs
            ],
        }
    finally:
        db.close()
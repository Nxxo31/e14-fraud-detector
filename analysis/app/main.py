"""E14 Analysis — FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, Base

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    log.info("Analysis tables ensured")
    yield


app = FastAPI(
    title="E14 Analysis API",
    description="E14 electoral form analysis: signature detection, OCR, validation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "e14-analysis"}


@app.get("/api/v1/stats")
async def stats():
    """Analysis statistics."""
    from sqlalchemy import func, text
    from .database import SessionLocal
    from .models import AnalysisResult, Anomaly

    db = SessionLocal()
    try:
        total = db.query(AnalysisResult).count()
        critical = db.query(AnalysisResult).filter(AnalysisResult.risk_level == "CRITICAL").count()
        high = db.query(AnalysisResult).filter(AnalysisResult.risk_level == "HIGH").count()
        medium = db.query(AnalysisResult).filter(AnalysisResult.risk_level == "MEDIUM").count()
        low = db.query(AnalysisResult).filter(AnalysisResult.risk_level == "LOW").count()
        math_valid = db.query(AnalysisResult).filter(AnalysisResult.math_valid == True).count()
        anomalies_total = db.query(Anomaly).count()

        return {
            "total_analyzed": total,
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "math_valid": math_valid,
            "total_anomalies": anomalies_total,
        }
    finally:
        db.close()


@app.get("/api/v1/review/queue")
async def review_queue(limit: int = 100):
    """Prioritized review queue (highest risk first)."""
    from sqlalchemy import desc
    from .database import SessionLocal
    from .models import AnalysisResult

    db = SessionLocal()
    try:
        results = db.query(AnalysisResult).order_by(
            desc(AnalysisResult.risk_score)
        ).limit(limit).all()

        return [
            {
                "id": r.id,
                "table_id": r.table_id,
                "risk_level": r.risk_level,
                "risk_score": r.risk_score,
                "signature_status": r.signature_status,
                "ocr_confidence": r.ocr_confidence,
                "anomaly_count": r.anomaly_count,
                "math_valid": r.math_valid,
            }
            for r in results
        ]
    finally:
        db.close()
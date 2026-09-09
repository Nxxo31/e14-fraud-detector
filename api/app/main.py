"""E14 Audit Platform - FastAPI Backend"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from .database import engine, Base, get_db
from . import models, schemas, services

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="E14 Audit Platform API",
    description="Backend API for E14 electoral form auditing",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "e14-audit-api"}


@app.get("/api/actas")
async def list_actas(
    status: Optional[str] = Query(None, enum=["pending", "processing", "complete", "failed"]),
    risk_level: Optional[str] = Query(None, enum=["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List actas with filtering and pagination."""
    query = db.query(models.Acta)
    
    if status:
        query = query.filter(models.Acta.download_status == status)
    if risk_level:
        query = query.filter(models.Acta.risk_level == risk_level)
    
    total = query.count()
    actas = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "actas": [schemas.Acta.from_orm(a) for a in actas]
    }


@app.get("/api/actas/{acta_id}")
async def get_acta(acta_id: int, db: Session = Depends(get_db)):
    """Get single acta with all extractions and anomalies."""
    acta = db.query(models.Acta).filter(models.Acta.id == acta_id).first()
    if not acta:
        raise HTTPException(status_code=404, detail="Acta not found")
    
    return schemas.ActaDetail.from_orm(acta)


@app.get("/api/review/queue")
async def get_review_queue(
    risk_level: Optional[str] = Query(None, enum=["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
    db: Session = Depends(get_db),
):
    """Get prioritized review queue ordered by risk score."""
    query = db.query(models.Acta).filter(
        models.Acta.download_status == "complete"
    ).order_by(models.Acta.risk_score.desc())
    
    if risk_level:
        query = query.filter(models.Acta.risk_level == risk_level)
    
    actas = query.limit(100).all()
    
    return [schemas.ReviewItem.from_orm(a) for a in actas]


@app.post("/api/review/{acta_id}/submit")
async def submit_review(
    acta_id: int,
    review: schemas.ReviewSubmission,
    db: Session = Depends(get_db),
):
    """Submit human review decision."""
    acta = db.query(models.Acta).filter(models.Acta.id == acta_id).first()
    if not acta:
        raise HTTPException(status_code=404, detail="Acta not found")
    
    review_record = models.Review(
        acta_id=acta_id,
        decision=review.decision,
        reason=review.reason,
        notes=review.notes,
        # TODO: reviewer_id from auth
    )
    db.add(review_record)
    
    acta.review_status = review.decision
    db.commit()
    
    return {"status": "success", "acta_id": acta_id, "decision": review.decision}


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics."""
    total = db.query(models.Acta).count()
    processed = db.query(models.Acta).filter(models.Acta.download_status == "complete").count()
    pending = total - processed
    
    critical = db.query(models.Acta).filter(models.Acta.risk_level == "CRITICAL").count()
    high = db.query(models.Acta).filter(models.Acta.risk_level == "HIGH").count()
    medium = db.query(models.Acta).filter(models.Acta.risk_level == "MEDIUM").count()
    low = db.query(models.Acta).filter(models.Acta.risk_level == "LOW").count()
    
    return {
        "total": total,
        "processed": processed,
        "pending": pending,
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
    }


@app.get("/api/dashboard/anomalies-over-time")
async def get_anomalies_over_time(db: Session = Depends(get_db)):
    """Get anomaly detection over time for charts."""
    from sqlalchemy import func
    
    results = db.query(
        func.date(models.Acta.created_at).label("date"),
        func.count().filter(models.Acta.risk_level == "CRITICAL").label("critical"),
        func.count().filter(models.Acta.risk_level == "HIGH").label("high"),
        func.count().filter(models.Acta.risk_level == "MEDIUM").label("medium"),
        func.count().filter(models.Acta.risk_level == "LOW").label("low"),
    ).group_by(func.date(models.Acta.created_at)).all()
    
    return [
        {
            "date": str(r.date),
            "critical": r.critical,
            "high": r.high,
            "medium": r.medium,
            "low": r.low,
        }
        for r in results
    ]
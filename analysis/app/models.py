"""E14 Analysis — Database models."""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, BigInteger, JSON, Boolean, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class Table(Base):
    """E14 table — mirrors acquisition.tables.

    We reference it here so analysis can update risk_level.
    """
    __tablename__ = "tables"

    id              = Column(BigInteger, primary_key=True)
    dep_code        = Column(String(2))
    muni_code       = Column(String(3))
    zona_code       = Column(String(3))
    puesto_code     = Column(String(2))
    mesa_code       = Column(String(3))
    pdf_status      = Column(String(20))
    pdf_sha256      = Column(String(64))
    risk_level      = Column(String(20))
    risk_score      = Column(Float)

    # Disable autoflush during bulk operations
    __table_args__ = {"autoload_with": None}


class AnalysisResult(Base):
    """Complete analysis result for one E-14."""
    __tablename__ = "analysis_results"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    table_id        = Column(BigInteger, ForeignKey("tables.id"), nullable=False, index=True)
    pdf_sha256      = Column(String(64), nullable=False)

    # Signature
    signature_status    = Column(String(20))   # COMPLETE | INCOMPLETE | EMPTY
    signatures_found    = Column(Integer)
    signatures_expected = Column(Integer, default=3)
    signature_ink_densities = Column(JSON)     # [0.15, 0.20, 0.10]
    signature_risk      = Column(String(20))   # LOW | MEDIUM | CRITICAL

    # OCR
    ocr_confidence  = Column(Float)

    # Votes
    total_votes     = Column(Integer)
    blank_votes      = Column(Integer)
    null_votes       = Column(Integer)
    unmarked_votes  = Column(Integer)
    candidate_votes = Column(JSON)     # {1: 123, 2: 45, ...}
    candidate_confidences = Column(JSON)

    # Risk
    risk_score      = Column(Float, default=0)
    risk_level      = Column(String(20))   # CRITICAL | HIGH | MEDIUM | LOW
    anomaly_count   = Column(Integer, default=0)
    math_valid      = Column(Boolean)

    processed_at    = Column(DateTime(timezone=True), server_default=func.now())

    anomalies = relationship("Anomaly", back_populates="analysis_result")


class Anomaly(Base):
    """Detected mathematical anomaly."""
    __tablename__ = "anomalies"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id     = Column(BigInteger, ForeignKey("analysis_results.id"), nullable=False, index=True)
    table_id        = Column(BigInteger, ForeignKey("tables.id"), nullable=False, index=True)

    rule            = Column(String(50))    # e.g. SUM_MISMATCH
    severity        = Column(String(20))    # CRITICAL | HIGH | MEDIUM | LOW
    message         = Column(Text)
    confidence      = Column(Float)
    page_number     = Column(Integer)
    details         = Column(JSON)

    analysis_result = relationship("AnalysisResult", back_populates="anomalies")
"""E14 Audit Platform - Database Models"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Acta(Base):
    """E14 electoral form (acta)."""
    __tablename__ = "actas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dep_code = Column(String(2), nullable=False)
    muni_code = Column(String(3), nullable=False)
    zona_code = Column(String(3), nullable=False)
    puesto_code = Column(String(2), nullable=False)
    mesa_code = Column(String(3), nullable=False)
    expected_name = Column(String(64), nullable=False, unique=True)
    pdf_sha256 = Column(String(64))
    pdf_size_bytes = Column(Integer)
    download_status = Column(String(20), default="pending")
    download_attempts = Column(Integer, default=0)
    risk_level = Column(String(20))
    risk_score = Column(Float, default=0)
    review_status = Column(String(20), default="new")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    extractions = relationship("Extraction", back_populates="acta")
    anomaly_detections = relationship("AnomalyDetection", back_populates="acta")
    signature_validations = relationship("SignatureValidation", back_populates="acta")
    reviews = relationship("Review", back_populates="acta")


class Extraction(Base):
    """OCR extraction results."""
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acta_id = Column(Integer, ForeignKey("actas.id"), nullable=False)
    extracted_at = Column(DateTime(timezone=True), server_default=func.now())
    page1_image_url = Column(String(500))
    page2_image_url = Column(String(500))
    page3_image_url = Column(String(500))
    ocr_confidence = Column(Float)
    processing_status = Column(String(20), default="pending")
    worker_id = Column(String(64))
    duration_ms = Column(Integer)

    # Relationships
    acta = relationship("Acta", back_populates="extractions")
    vote_counts = relationship("VoteCount", back_populates="extraction")
    totals = relationship("Totals", back_populates="extraction")


class VoteCount(Base):
    """Individual candidate vote count."""
    __tablename__ = "vote_counts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=False)
    candidate_number = Column(Integer, nullable=False)
    candidate_name = Column(String(255))
    votes = Column(Integer)
    confidence = Column(Float)
    page_number = Column(Integer)
    status = Column(String(20))

    # Relationships
    extraction = relationship("Extraction", back_populates="vote_counts")


class Totals(Base):
    """Vote totals (blank, null, unmarked, total)."""
    __tablename__ = "totals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=False)
    blank_votes = Column(Integer)
    null_votes = Column(Integer)
    unmarked_votes = Column(Integer)
    total_votes = Column(Integer)
    confidence = Column(Float)

    # Relationships
    extraction = relationship("Extraction", back_populates="totals")


class AnomalyDetection(Base):
    """Detected anomaly in an acta."""
    __tablename__ = "anomaly_detections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acta_id = Column(Integer, ForeignKey("actas.id"), nullable=False)
    detection_type = Column(String(50))
    severity = Column(String(20))
    description = Column(Text)
    confidence = Column(Float)
    page_number = Column(Integer)
    coordinates = Column(JSON)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    acta = relationship("Acta", back_populates="anomaly_detections")


class SignatureValidation(Base):
    """Signature validation result."""
    __tablename__ = "signature_validations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acta_id = Column(Integer, ForeignKey("actas.id"), nullable=False)
    overall_status = Column(String(20))
    signatures_found = Column(Integer)
    signatures_expected = Column(Integer, default=3)
    ink_densities = Column(JSON)
    risk_level = Column(String(20))
    validated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    acta = relationship("Acta", back_populates="signature_validations")


class Review(Base):
    """Human review record."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acta_id = Column(Integer, ForeignKey("actas.id"), nullable=False)
    reviewer_id = Column(Integer)
    decision = Column(String(20))  # valid, suspicious, invalid
    reason = Column(Text)
    notes = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    acta = relationship("Acta", back_populates="reviews")


class Reviewer(Base):
    """Human reviewer account."""
    __tablename__ = "reviewers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    email = Column(String(255))
    role = Column(String(50))  # analyst, supervisor, legal
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Audit trail for all changes."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(64))
    record_id = Column(Integer)
    action = Column(String(20))  # INSERT, UPDATE, DELETE
    old_values = Column(JSON)
    new_values = Column(JSON)
    actor_id = Column(Integer)
    actor_ip = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
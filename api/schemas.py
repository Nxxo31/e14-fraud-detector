"""
F6 — Schemas Pydantic para ingesta de evidencia ciudadana.

Modelos de request/response para el endpoint POST /api/evidence/upload.
Incluye validación de tipos para los scores de Capa 1 (grosor, separador, tinta).
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


# ── Scores de Capa 1 (OpenCV) ─────────────────────────────────

class Capa1Scores(BaseModel):
    """Scores individuales de anomalía visual de Capa 1 (0=normal, 1=anómalo)."""
    score_grosor: float = Field(
        ..., ge=0.0, le=1.0,
        description="Grosor del trazo: 0=normal, 1=muy grueso/fino"
    )
    score_separador: float = Field(
        ..., ge=0.0, le=1.0,
        description="Forma del separador: 0=punto delgado, 1=círculo grande relleno"
    )
    score_tinta: float = Field(
        ..., ge=0.0, le=1.0,
        description="Densidad de tinta superpuesta: 0=normal, 1=sobreescritura densa"
    )
    score_global: float = Field(
        ..., ge=0.0, le=1.0,
        description="Score ponderado: 0.3*grosor + 0.4*separador + 0.3*tinta"
    )

    @field_validator("score_global")
    @classmethod
    def validate_global(cls, v, info):
        """Verifica consistencia: el global debe estar en rango plausible."""
        return round(v, 4)


class EvidenceDetail(BaseModel):
    """Detalles técnicos del procesamiento de la imagen."""
    image_shape: Optional[List[int]] = None
    image_size_bytes: Optional[int] = None
    processing_ms: Optional[float] = None


# ── Response del endpoint ──────────────────────────────────────

class EvidenceUploadResponse(BaseModel):
    """Respuesta del endpoint POST /api/evidence/upload."""
    success: bool = Field(..., description="Si el upload y procesamiento fueron exitosos")
    evidence_id: Optional[str] = Field(
        None, description="UUID del registro creado en evidence_ciudadana (Supabase)"
    )
    acta_id: Optional[str] = Field(
        None, description="UUID del acta oficial asociada (si se encontró)"
    )
    mesa_key: str = Field(..., description="Mesa key de la evidencia")
    scores_capa1: Capa1Scores = Field(..., description="Scores de Capa 1 (OpenCV)")
    enqueued_capa2: bool = Field(
        False, description="Si la foto fue encolada para Capa 2 (VLM) — score > 0.6"
    )
    capa2_reason: Optional[str] = Field(
        None, description="Razón por la que se encoló (o no) a Capa 2"
    )
    supabase_status: str = Field(
        "skipped",
        description="Estado de inserción en Supabase: saved, skipped, error"
    )
    supabase_error: Optional[str] = Field(
        None, description="Mensaje de error si falló la inserción en Supabase"
    )
    detail: Optional[EvidenceDetail] = None
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp del procesamiento"
    )


class EvidenceErrorResponse(BaseModel):
    """Respuesta de error estándar."""
    success: bool = False
    error: str
    detail: Optional[str] = None

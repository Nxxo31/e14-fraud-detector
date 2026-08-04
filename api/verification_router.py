"""
F8 — API Router para verificación ciudadana y consenso democrático.

Endpoints:
  POST /api/verification/vote                        — Registrar voto ciudadano
  GET  /api/verification/discrepancy/{id}            — Estado de una discrepancia
  GET  /api/verification/pending                     — Cola de discrepancias por verificar
  GET  /api/verification/summary                     — Estadísticas globales de consenso
  GET  /api/verification/config                      — Ver umbrales de consenso
  PUT  /api/verification/config                      — Actualizar umbrales (admin)

Parte de F8 (R-13): Flujo de verificación ciudadana y consenso democrático.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.consensus_db import (
    cast_vote,
    get_discrepancia_status,
    get_pending_discrepancias,
    get_consensus_summary,
    get_config,
    set_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verification", tags=["F8 — Verificación Ciudadana y Consenso"])


# ── Schemas ──────────────────────────────────────────────────────

class VoteRequest(BaseModel):
    """Request para registrar un voto ciudadano sobre una discrepancia."""
    discrepancia_id: str = Field(..., description="UUID de la discrepancia")
    voto: str = Field(
        ...,
        description="Tipo de voto: 'confirma_legitimo' o 'confirma_anomalo'",
    )
    votante_id: Optional[str] = Field(
        None, description="UUID del votante (si está autenticado)"
    )
    comentario: Optional[str] = Field(
        None, max_length=500,
        description="Comentario opcional del votante",
    )
    peso_reputacion: float = Field(
        1.0, ge=0.0, le=5.0,
        description="Multiplicador de peso por reputación del votante",
    )


class ConfigUpdateRequest(BaseModel):
    """Request para actualizar la configuración del sistema de consenso."""
    clave: str = Field(..., description="Clave de configuración")
    valor: str = Field(..., description="Nuevo valor")
    descripcion: Optional[str] = Field(None, description="Descripción opcional")


# ── Helper para extraer IP del request ────────────────────────────

def _get_client_ip(request: Request) -> Optional[str]:
    """Extrae la IP del cliente (respetando proxies)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Vote endpoint ─────────────────────────────────────────────────

@router.post(
    "/vote",
    summary="Registrar voto ciudadano sobre una discrepancia",
    description="""
Un ciudadano registra su verificación sobre una discrepancia. El sistema:

1. Valida que la discrepancia existe y no está congelada.
2. Verifica que el votante no haya votado ya (unique constraint).
3. Hashea la IP del votante (nunca se guarda en crudo).
4. Inserta el voto con su peso de reputación.
5. Evalúa el consenso: si votos ≥ umbral_min Y % en una dirección ≥ umbral_pct,
   congela la discrepancia como 'verificado_legitimo' o 'verificado_anomalo'.

El consenso democrático es el mecanismo de F8 que permite a múltiples ciudadanos
verificar una discrepancia antes de que se cierre definitivamente.
    """,
)
async def vote_endpoint(request: Request, body: VoteRequest):
    # Validar tipo de voto
    if body.voto not in ("confirma_legitimo", "confirma_anomalo"):
        raise HTTPException(
            status_code=400,
            detail="voto debe ser 'confirma_legitimo' o 'confirma_anomalo'",
        )

    client_ip = _get_client_ip(request)

    result = cast_vote(
        discrepancia_id=body.discrepancia_id,
        voto=body.voto,
        votante_id=body.votante_id,
        votante_ip=client_ip,
        comentario=body.comentario,
        peso_reputacion=body.peso_reputacion,
    )

    if result.get("error"):
        # Errores no fatales (ya votó, discrepancia congelada) → 409 Conflict
        if "ya" in result["error"].lower() or "congelada" in result["error"].lower():
            raise HTTPException(status_code=409, detail=result["error"])
        # Error fatal → 404 o 500
        if "no encontrada" in result["error"].lower():
            raise HTTPException(status_code=404, detail=result["error"])
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# ── Discrepancy status ────────────────────────────────────────────

@router.get(
    "/discrepancy/{discrepancia_id}",
    summary="Estado completo de una discrepancia y sus votos",
)
async def discrepancy_status_endpoint(discrepancia_id: str):
    result = get_discrepancia_status(discrepancia_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Pending queue ─────────────────────────────────────────────────

@router.get(
    "/pending",
    summary="Cola de discrepancias pendientes de verificación ciudadana",
    description="""
Lista las discrepancias en estado 'por_verificar', ordenadas por prioridad
(alta → media → baja) y luego por fecha de creación (más antigua primero).
Este es el feed que alimenta el dashboard de verificación ciudadana.
    """,
)
async def pending_endpoint(
    mesa_key: Optional[str] = Query(None, description="Filtrar por mesa_key"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return get_pending_discrepancias(
        mesa_key=mesa_key,
        limit=limit,
        offset=offset,
    )


# ── Consensus summary ─────────────────────────────────────────────

@router.get(
    "/summary",
    summary="Estadísticas globales del sistema de consenso democrático",
    description="""
Retorna métricas agregadas del sistema de verificación ciudadana:
- Total de discrepancias
- Discrepancias por verificar (cola activa)
- Verificadas como legítimas
- Verificadas como anómalas
- Congeladas (consenso alcanzado)
- Total de votos ciudadanos registrados
- Votantes únicos
- Configuración actual de umbrales
    """,
)
async def summary_endpoint():
    return get_consensus_summary()


# ── Config management ─────────────────────────────────────────────

@router.get(
    "/config",
    summary="Ver configuración de umbrales de consenso",
)
async def get_config_endpoint(
    clave: Optional[str] = Query(None, description="Clave específica. Si se omite, lista todas."),
):
    from api.consensus_db import _get_db, _ensure_tables

    conn = _get_db()
    _ensure_tables(conn)

    if clave:
        row = conn.execute(
            "SELECT clave, valor, descripcion, actualizado_en FROM configuracion_sistema WHERE clave = ?",
            (clave,),
        ).fetchone()
        conn.close()
        return dict(row) if row else {"error": "Clave no encontrada"}

    rows = conn.execute(
        "SELECT clave, valor, descripcion, actualizado_en FROM configuracion_sistema ORDER BY clave"
    ).fetchall()
    conn.close()
    return {"configuraciones": [dict(r) for r in rows]}


@router.put(
    "/config",
    summary="Actualizar umbrales de consenso (solo admin)",
    description="""
Actualiza un valor de configuración del sistema. Las claves conocidas:
- umbral_min_votos: número mínimo de votos para evaluar consenso (default 5)
- umbral_consenso_pct: porcentaje mínimo en una dirección (default 0.80)
- capa1_score_revision: score mínimo Capa 1 para enviar a Capa 2 (default 0.60)
- capa1_score_prioridad_alta: score mínimo para prioridad alta (default 0.85)
    """,
)
async def update_config_endpoint(body: ConfigUpdateRequest):
    # Validar claves conocidas
    allowed_keys = {
        "umbral_min_votos",
        "umbral_consenso_pct",
        "capa1_score_revision",
        "capa1_score_prioridad_alta",
    }
    if body.clave not in allowed_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Clave no permitida. Valores válidos: {allowed_keys}",
        )

    set_config(body.clave, body.valor, body.descripcion)
    return {"clave": body.clave, "valor": body.valor, "actualizado": True}

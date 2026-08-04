"""
F7 — API Router para motor de comparación oficial vs ciudadano.

Endpoints:
  POST /api/comparison/run/{mesa_key}   — Comparar una mesa específica
  POST /api/comparison/run-batch         — Comparar todas las mesas con evidencia
  GET  /api/comparison/discrepancies     — Listar discrepancias oficial vs ciudadano
  GET  /api/comparison/discrepancies/{id}— Detalle de una discrepancia
  POST /api/vlm/workers/run              — Lanzar VLM workers concurrentes

Parte de F7 (R-12, R-16): VLM workers dedicados + motor de comparación.
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

# Agregar el proyecto al path
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from engine.forensic.comparison_engine import (
    run_comparison_for_mesa,
    run_comparison_batch,
)
from engine.analyze.vlm_workers import run_vlm_workers, _get_available_keys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["F7 — Comparación Oficial vs Ciudadano + VLM Workers"])


# ── Schemas ──────────────────────────────────────────────────────

class ComparisonRequest(BaseModel):
    """Request para comparar una mesa."""
    mesa_key: str = Field(..., description="Clave de la mesa a comparar")
    tolerancia: int = Field(0, ge=0, le=100, description="Diferencia permitida sin generar discrepancia")


class BatchComparisonRequest(BaseModel):
    """Request para comparar un batch de mesas."""
    mesa_keys: Optional[list[str]] = Field(
        None, description="Lista de mesas a comparar. Si se omite, compara todas con evidencia."
    )
    tolerancia: int = Field(0, ge=0, le=100, description="Diferencia permitida")


class VLMWorkersRequest(BaseModel):
    """Request para lanzar VLM workers."""
    max_workers: int = Field(3, ge=1, le=10, description="Número de workers concurrentes")
    max_slots_per_worker: int = Field(20, ge=1, le=100, description="Máximo de slots por worker")


# ── Comparison endpoints ─────────────────────────────────────────

@router.post(
    "/comparison/run/{mesa_key}",
    summary="Comparar acta oficial vs evidencia ciudadana de una mesa",
    description="""
Compara los datos del acta oficial con la mejor evidencia ciudadana disponible
para una mesa específica y genera discrepancias con tipo 'discrepancia_oficial_vs_ciudadano'.
    """,
)
async def compare_mesa_endpoint(mesa_key: str, tolerancia: int = Query(0, ge=0, le=100)):
    try:
        result = run_comparison_for_mesa(mesa_key, tolerancia=tolerancia)
        return result
    except Exception as e:
        logger.error("Comparison error for mesa %s: %s", mesa_key, e)
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.post(
    "/comparison/run-batch",
    summary="Comparar todas las mesas con evidencia ciudadana",
    description="""
Ejecuta la comparación oficial vs ciudadano para todas las mesas que tienen
evidencia ciudadana procesada. Retorna un resumen con el total de discrepancias.
    """,
)
async def compare_batch_endpoint(request: BatchComparisonRequest):
    try:
        result = run_comparison_batch(
            mesa_keys=request.mesa_keys,
            tolerancia=request.tolerancia,
        )
        return result
    except Exception as e:
        logger.error("Batch comparison error: %s", e)
        raise HTTPException(status_code=500, detail=f"Error en batch: {str(e)}")


@router.get(
    "/comparison/discrepancies",
    summary="Listar discrepancias oficial vs ciudadano",
)
async def list_comparison_discrepancies(
    mesa_key: Optional[str] = Query(None, description="Filtrar por mesa_key"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Lista discrepancias de tipo 'discrepancia_oficial_vs_ciudadano'."""
    from api.consensus_db import _get_db, _ensure_tables

    conn = _get_db()
    _ensure_tables(conn)

    query = """
        SELECT id, mesa_key, campo_afectado, valor_oficial, valor_ciudadano,
               tipo_anomalia, score_capa0, score_capa1, score_capa2,
               razon_flag, prioridad, estado,
               votos_confirma, votos_rechaza, congelado,
               creado_en, actualizado_en
        FROM discrepancias
        WHERE tipo_anomalia = 'discrepancia_oficial_vs_ciudadano'
    """
    params: list = []
    if mesa_key:
        query += " AND mesa_key = ?"
        params.append(mesa_key)

    query += " ORDER BY creado_en DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE tipo_anomalia = 'discrepancia_oficial_vs_ciudadano'"
    ).fetchone()[0]
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(r) for r in rows],
    }


# ── VLM Workers endpoints ─────────────────────────────────────────

@router.post(
    "/vlm/workers/run",
    summary="Lanzar VLM workers concurrentes",
    description="""
Inicia N workers VLM dedicados que procesan slots pendientes de cola_procesamiento
(capa_actual=2). Cada worker usa una API key dedicada con rate limiting independiente.

Requiere variables de entorno: NVIDIA_API_KEY, NVIDIA_API_KEY_2, NVIDIA_API_KEY_3.
    """,
)
async def run_vlm_workers_endpoint(request: VLMWorkersRequest):
    available_keys = _get_available_keys()
    if not available_keys:
        raise HTTPException(
            status_code=503,
            detail="No hay API keys de NVIDIA NIM configuradas en variables de entorno",
        )

    try:
        result = run_vlm_workers(
            max_workers=request.max_workers,
            max_slots_per_worker=request.max_slots_per_worker,
        )
        return result
    except Exception as e:
        logger.error("VLM workers error: %s", e)
        raise HTTPException(status_code=500, detail=f"Error en VLM workers: {str(e)}")


@router.get(
    "/vlm/workers/status",
    summary="Estado de VLM workers y cola de procesamiento",
)
async def vlm_workers_status():
    """Retorna el estado actual de la cola de procesamiento VLM y las API keys disponibles."""
    from api.consensus_db import _get_db, _ensure_tables

    available_keys = _get_available_keys()

    conn = _get_db()
    _ensure_tables(conn)

    try:
        pending = conn.execute("""
            SELECT COUNT(*) FROM cola_procesamiento
            WHERE estado_slot = 'pendiente' AND capa_actual = 2
        """).fetchone()[0]
        processing = conn.execute("""
            SELECT COUNT(*) FROM cola_procesamiento
            WHERE estado_slot = 'procesando' AND capa_actual = 2
        """).fetchone()[0]
        completed = conn.execute("""
            SELECT COUNT(*) FROM cola_procesamiento
            WHERE estado_slot = 'completado' AND capa_actual = 2
        """).fetchone()[0]
        errors = conn.execute("""
            SELECT COUNT(*) FROM cola_procesamiento
            WHERE estado_slot = 'error' AND capa_actual = 2
        """).fetchone()[0]
    except Exception:
        pending = processing = completed = errors = 0
    finally:
        conn.close()

    return {
        "api_keys_available": len(available_keys),
        "max_concurrent_workers": min(len(available_keys), 10),
        "cola_capa2": {
            "pendientes": pending,
            "procesando": processing,
            "completados": completed,
            "errores": errors,
            "total": pending + processing + completed + errors,
        },
    }

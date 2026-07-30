"""
F6 — Endpoint de ingesta de evidencia ciudadana.

POST /api/evidence/upload
  - Recibe fotos (multipart/form-data, JPG/PNG, max 10MB)
  - Valida formato y tamaño
  - Procesa con Capa 1 (OpenCV) — scores reales: grosor, separador, tinta
  - Inserta registro en Supabase tabla `evidencia_ciudadana`
  - Encola para Capa 2 (VLM) si score_global > 0.6 — cola SQLite cola_procesamiento

Integrado en api/main.py como router.
"""

import sys
import os
import time
import base64
import json
import uuid
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
from io import BytesIO
from datetime import datetime, timezone

import cv2
import numpy as np

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from typing import Optional

from .schemas import (
    Capa1Scores,
    EvidenceDetail,
    EvidenceUploadResponse,
    EvidenceErrorResponse,
)

# ── Configuración ────────────────────────────────────────────────

router = APIRouter(prefix="/api/evidence", tags=["F6 — Evidencia Ciudadana"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/octet-stream",  # Algunos clientes no envían el MIME correcto
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Supabase (mismo patrón que fase4/capa1_opencv.py)
SUPABASE_PROJECT = "oawxinjygprnftkgcjyr"
SUPABASE_URL = f"https://{SUPABASE_PROJECT}.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_KEY", ""))

# SQLite (cola de procesamiento, mismo patrón que fase3/worker.py)
DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"

# Umbral para encolar a Capa 2 (VLM)
CAPA2_SCORE_THRESHOLD = 0.6

# Añadir el directorio raíz del proyecto al path para importar Capa 1
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Capa 1: Procesamiento OpenCV real ────────────────────────────

def _import_capa1_functions():
    """Importa las funciones de scoring de Capa 1 desde fase4/capa1_opencv.py."""
    try:
        from fase4.capa1_opencv import (
            score_grosor_trazo,
            score_forma_separador,
            score_densidad_tinta_superpuesta,
        )
        return score_grosor_trazo, score_forma_separador, score_densidad_tinta_superpuesta
    except ImportError:
        # Fallback: definir funciones inline (copiadas de fase4/capa1_opencv.py)
        # Esto garantiza que el endpoint funcione incluso si el import falla
        return _score_grosor_fallback, _score_separador_fallback, _score_tinta_fallback


def _score_grosor_fallback(celda_imagen: np.ndarray) -> float:
    """Copia de score_grosor_trazo de fase4/capa1_opencv.py."""
    if celda_imagen.size == 0:
        return 0.0
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    if len(nonzero) == 0:
        return 0.0
    avg_thickness = np.median(nonzero) * 2
    if avg_thickness < 2.0:
        return min(1.0, (2.0 - avg_thickness) / 2.0 * 0.5)
    elif avg_thickness > 8.0:
        return min(1.0, (avg_thickness - 8.0) / 8.0)
    return 0.0


def _score_separador_fallback(celda_imagen: np.ndarray) -> float:
    """Copia de score_forma_separador de fase4/capa1_opencv.py."""
    if celda_imagen.size == 0:
        return 0.0
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    max_score = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 20:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter ** 2)
        if circularity > 0.7 and 50 < area < 500:
            if area > 150:
                anomalia = min(1.0, (area - 150) / 200)
                max_score = max(max_score, anomalia)
        elif area > 100 and circularity < 0.5:
            max_score = max(max_score, min(1.0, (area - 100) / 150))
    return max_score


def _score_tinta_fallback(celda_imagen: np.ndarray) -> float:
    """Copia de score_densidad_tinta_superpuesta de fase4/capa1_opencv.py."""
    if celda_imagen.size == 0:
        return 0.0
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    dark_pixels = np.sum(gray < 120)
    total = gray.size
    if total == 0:
        return 0.0
    density = dark_pixels / total
    return max(0.0, min(1.0, (density - 0.15) / 0.25))


def process_image_capa1(image_bytes: bytes) -> tuple[Capa1Scores, EvidenceDetail, np.ndarray]:
    """
    Procesa la imagen completa con Capa 1 (OpenCV) y retorna scores reales.

    A diferencia de procesar_celda() que recorta celdas específicas del PDF,
    aquí procesamos la imagen completa subida por el ciudadano como un recorte.

    Returns:
        (Capa1Scores, EvidenceDetail, np.ndarray image)
    """
    t0 = time.time()

    # Decodificar imagen con OpenCV
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        raise HTTPException(
            status_code=422,
            detail="No se pudo decodificar la imagen. Verifique que sea un JPG o PNG válido."
        )

    # Para evidencia ciudadana, procesamos la imagen completa
    # (el ciudadano sube un recorte/foto de la celda o firma)
    score_grosor_fn, score_separador_fn, score_tinta_fn = _import_capa1_functions()

    s_grosor = float(score_grosor_fn(img))
    s_separador = float(score_separador_fn(img))
    s_tinta = float(score_tinta_fn(img))
    s_global = 0.3 * s_grosor + 0.4 * s_separador + 0.3 * s_tinta
    s_global = float(min(1.0, max(0.0, s_global)))

    elapsed_ms = (time.time() - t0) * 1000

    scores = Capa1Scores(
        score_grosor=round(s_grosor, 4),
        score_separador=round(s_separador, 4),
        score_tinta=round(s_tinta, 4),
        score_global=round(s_global, 4),
    )

    detail = EvidenceDetail(
        image_shape=list(img.shape[:2]),
        image_size_bytes=len(image_bytes),
        processing_ms=round(elapsed_ms, 2),
    )

    return scores, detail, img


# ── Supabase: Insertar en evidencia_ciudadana ────────────────────

def _supabase_insert(
    image_b64: str,
    mesa_key: str,
    scores: Capa1Scores,
    acta_id: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """
    Inserta un registro en la tabla evidencia_ciudadana de Supabase.

    Returns:
        ("saved", None) si OK
        ("error", error_msg) si falló
        ("skipped", "No Supabase key configured") si no hay clave
    """
    if not SUPABASE_KEY or SUPABASE_KEY == "REDACTED_SERVICE_KEY":
        return "skipped", "No Supabase service key configured (env SUPABASE_SERVICE_KEY)"

    evidence_id = str(uuid.uuid4())

    # Codificar scores como JSONB
    scores_json = {
        "score_grosor": scores.score_grosor,
        "score_separador": scores.score_separador,
        "score_tinta": scores.score_tinta,
        "score_global": scores.score_global,
    }

    payload = {
        "id": evidence_id,
        "mesa_key": mesa_key,
        "imagen_url": f"data:image/png;base64,{image_b64[:100]}...",  # Truncado para URL
        "imagen_storage_path": None,
        "votos_extraidos": scores_json,
        "metodo_extraccion": "vlm",  # Los scores vienen de visión
        "confianza_extraccion": scores.score_global,
        "estado_revision": "pendiente",
    }

    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/evidencia_ciudadana",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                return "saved", None
            return "error", f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return "error", f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return "error", str(e)


# ── Cola Capa 2: Encolar para VLM ────────────────────────────────

def _enqueue_capa2(
    evidence_id: str,
    mesa_key: str,
    scores: Capa1Scores,
    image_b64: str,
    acta_id: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Encola la evidencia para Capa 2 (VLM) en cola_procesamiento (SQLite).

    Sigue el mismo patrón que fase3/worker.py:
    INSERT INTO cola_procesamiento (id, mesa_key, acta_id, capa_actual, estado_slot)
    VALUES (?, ?, ?, 2, 'pendiente')

    Returns:
        (enqueued: bool, reason: str)
    """
    if scores.score_global <= CAPA2_SCORE_THRESHOLD:
        return False, f"score_global={scores.score_global:.2f} ≤ umbral {CAPA2_SCORE_THRESHOLD}"

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Crear tabla si no existe (fallback si la DB no tiene el schema)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cola_procesamiento (
                id TEXT PRIMARY KEY,
                mesa_key TEXT NOT NULL,
                acta_id TEXT,
                capa_actual INTEGER NOT NULL DEFAULT 0,
                estado_slot TEXT NOT NULL DEFAULT 'pendiente',
                worker_id TEXT,
                intentos INTEGER DEFAULT 0,
                max_intentos INTEGER DEFAULT 3,
                ultimo_error TEXT,
                tomado_en TEXT,
                completado_en TEXT,
                creado_en TEXT DEFAULT (datetime('now')),
                evidence_id TEXT,
                image_b64 TEXT
            )
        """)

        slot_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO cola_procesamiento
                (id, mesa_key, acta_id, capa_actual, estado_slot, evidence_id, image_b64)
            VALUES (?, ?, ?, 2, 'pendiente', ?, ?)
        """, (slot_id, mesa_key, acta_id, evidence_id, image_b64))

        conn.commit()
        conn.close()

        return True, f"Encolado en cola_procesamiento slot={slot_id[:8]}... para Capa 2 (VLM)"

    except Exception as e:
        return False, f"Error encolando Capa 2: {e}"


# ── Buscar acta_id por mesa_key en Supabase ──────────────────────

def _find_acta_id(mesa_key: str) -> Optional[str]:
    """Busca el UUID de un acta por mesa_key en Supabase."""
    if not SUPABASE_KEY or SUPABASE_KEY == "REDACTED_SERVICE_KEY":
        return None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/actas_oficiales?select=id,mesa_key&mesa_key=eq.{mesa_key}"
        )
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode())
            if rows:
                return rows[0]["id"]
    except Exception:
        pass
    return None


# ── Endpoint ─────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=EvidenceUploadResponse,
    responses={
        400: {"model": EvidenceErrorResponse, "description": "Archivo inválido"},
        422: {"model": EvidenceErrorResponse, "description": "Imagen no decodificable"},
        500: {"model": EvidenceErrorResponse, "description": "Error interno"},
    },
    summary="Subir foto de evidencia ciudadana",
    description="""
Sube una foto de evidencia ciudadana (JPG/PNG, max 10MB).

El endpoint:
1. Valida formato y tamaño del archivo
2. Procesa la imagen con Capa 1 (OpenCV) — scores reales de grosor, separador, tinta
3. Inserta un registro en Supabase `evidencia_ciudadana` con status='pendiente'
4. Encola para Capa 2 (VLM) si score_global > 0.6
    """,
)
async def upload_evidence(
    file: UploadFile = File(..., description="Archivo de imagen JPG o PNG (max 10MB)"),
    mesa_key: str = Form(..., description="Mesa key de la evidencia (ej: 01-280-00-000-015)"),
    aportante_id: Optional[str] = Form(None, description="UUID del aportante (opcional)"),
):
    t_start = time.time()

    # ── 1. Validar archivo ──
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo vacío")

    # Validar extensión
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {ext}. Solo se aceptan JPG y PNG."
        )

    # Leer contenido
    content = await file.read()

    # Validar tamaño (incluso archivos vacíos)
    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="El archivo está vacío (0 bytes)"
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Archivo demasiado grande: {len(content)} bytes. Máximo: {MAX_FILE_SIZE} bytes (10MB)"
        )

    # Validar content-type (con tolerancia para octet-stream)
    ct = (file.content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Content-Type no soportado: {ct}. Se esperaba image/jpeg o image/png."
        )

    # ── 2. Validar que es una imagen válida con OpenCV (magic bytes) ──
    # Verificar magic bytes antes de intentar decodificar
    # JPG: FF D8 FF | PNG: 89 50 4E 47
    is_jpg = content[:3] == b'\xff\xd8\xff'
    is_png = content[:8] == b'\x89PNG\r\n\x1a\n'

    if not is_jpg and not is_png:
        # Verificar si parece un PDF ( Starts with %PDF )
        if content[:4] == b'%PDF':
            raise HTTPException(
                status_code=400,
                detail="Se recibió un PDF. Solo se aceptan imágenes JPG y PNG."
            )
        raise HTTPException(
            status_code=400,
            detail="El archivo no es una imagen válida (magic bytes no coinciden con JPG o PNG)."
        )

    # ── 3. Procesar con Capa 1 (OpenCV) ──
    try:
        scores, detail, img = process_image_capa1(content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando imagen con OpenCV: {str(e)}"
        )

    # ── 4. Preparar base64 para persistencia ──
    image_b64 = base64.b64encode(content).decode("utf-8")

    # ── 5. Buscar acta_id en Supabase ──
    acta_id = _find_acta_id(mesa_key)

    # ── 6. Insertar en Supabase (evidencia_ciudadana) ──
    supabase_status, supabase_error = _supabase_insert(
        image_b64=image_b64,
        mesa_key=mesa_key,
        scores=scores,
        acta_id=acta_id,
    )

    # Generar evidence_id (usado para encolar incluso si Supabase falló)
    db_evidence_id = str(uuid.uuid4()) if supabase_status != "saved" else str(uuid.uuid4())

    # ── 7. Encolar para Capa 2 (VLM) si score > 0.6 ──
    enqueued, enqueue_reason = _enqueue_capa2(
        evidence_id=db_evidence_id,
        mesa_key=mesa_key,
        scores=scores,
        image_b64=image_b64,
        acta_id=acta_id,
    )

    elapsed_total = (time.time() - t_start) * 1000
    detail.processing_ms = round(elapsed_total, 2)

    return EvidenceUploadResponse(
        success=True,
        evidence_id=db_evidence_id,
        acta_id=acta_id,
        mesa_key=mesa_key,
        scores_capa1=scores,
        enqueued_capa2=enqueued,
        capa2_reason=enqueue_reason,
        supabase_status=supabase_status,
        supabase_error=supabase_error,
        detail=detail,
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/health",
    summary="Health check del endpoint de evidencia",
)
async def evidence_health():
    """Verifica que el endpoint de evidencia está operativo."""
    return {
        "status": "ok",
        "endpoint": "/api/evidence/upload",
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "allowed_formats": list(ALLOWED_EXTENSIONS),
        "capa2_threshold": CAPA2_SCORE_THRESHOLD,
        "supabase_configured": bool(SUPABASE_KEY and SUPABASE_KEY != "REDACTED_SERVICE_KEY"),
    }

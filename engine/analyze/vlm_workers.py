"""
F7 — VLM Workers dedicados con batches concurrentes.

Worker pool que procesa slots de cola_procesamiento (capa_actual=2) en paralelo,
rotando entre 3 API keys de NVIDIA NIM para maximizar throughput (~37 req/min/key).

Diseño:
  - Cada worker tiene su propia API key asignada (round-robin).
  - Los workers toman slots de la cola de forma atómica (SQLite transaction).
  - Después de procesar, persisten el resultado VLM y marcan el slot como 'completado'.
  - Rate limiting por worker con su propio timestamp.

Compatible con Python 3.14, asyncio + concurrent.futures.ThreadPoolExecutor.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.analyze.vlm_nim import (
    VLM_MODEL,
    VLM_API_URL,
    _call_vlm,
    analyze_cell_vlm,
)

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "e14_audit.db"

# API keys disponibles para rotación
_API_KEY_NAMES = ["NVIDIA_API_KEY", "NVIDIA_API_KEY_2", "NVIDIA_API_KEY_3"]


def _get_available_keys() -> List[str]:
    """Retorna las API keys que estén configuradas en el entorno."""
    keys = []
    for name in _API_KEY_NAMES:
        val = os.environ.get(name, "")
        if val.startswith("nvapi-"):
            keys.append(val)
    return keys


# ── Rate limiter por worker (thread-local) ───────────────────────

import threading

_rate_lock = threading.Lock()
_last_request_per_key: Dict[str, float] = {}
_MIN_INTERVAL = 1.6  # ~37 req/min por key


def _rate_limit_for_key(api_key: str):
    """Espera si es necesario para respetar el rate limit de una key específica."""
    with _rate_lock:
        elapsed = time.time() - _last_request_per_key.get(api_key, 0)
        wait = _MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    with _rate_lock:
        _last_request_per_key[api_key] = time.time()


# ── Slot management (atomic SQLite operations) ───────────────────

def _take_next_slot(worker_id: str, db_path: Path = _DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Toma atómicamente el siguiente slot pendiente de capa 2.

    Usa BEGIN IMMEDIATE para evitar race conditions entre workers.
    Returns dict con slot data, o None si no hay slots disponibles.
    """
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT id, mesa_key, acta_id, evidence_id, image_b64, intentos
            FROM cola_procesamiento
            WHERE estado_slot = 'pendiente' AND capa_actual = 2
            ORDER BY creado_en
            LIMIT 1
        """).fetchone()

        if row is None:
            conn.execute("ROLLBACK")
            return None

        slot = dict(row)
        conn.execute("""
            UPDATE cola_procesamiento
            SET estado_slot = 'procesando',
                worker_id = ?,
                tomado_en = datetime('now'),
                intentos = intentos + 1
            WHERE id = ?
        """, (worker_id, slot["id"]))
        conn.execute("COMMIT")
        return slot
    except sqlite3.OperationalError as e:
        # DB locked — otro worker ganó la carrera
        conn.execute("ROLLBACK")
        logger.debug("Slot race lost: %s", e)
        return None
    finally:
        conn.close()


def _mark_slot_completed(slot_id: str, result: Dict[str, Any], db_path: Path = _DB_PATH):
    """Marca un slot como completado y guarda el resultado VLM."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("""
            UPDATE cola_procesamiento
            SET estado_slot = 'completado',
                completado_en = datetime('now')
            WHERE id = ?
        """, (slot_id,))
        _save_vlm_result(slot_id, result, conn)
        conn.commit()
    except Exception as e:
        conn.execute("""
            UPDATE cola_procesamiento
            SET estado_slot = 'error', ultimo_error = ?
            WHERE id = ?
        """, (str(e)[:500], slot_id))
        conn.commit()
        logger.error("Error marking slot %s: %s", slot_id, e)
    finally:
        conn.close()


def _mark_slot_error(slot_id: str, error: str, db_path: Path = _DB_PATH):
    """Marca un slot como error tras agotar intentos."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("""
            UPDATE cola_procesamiento
            SET estado_slot = 'error', ultimo_error = ?
            WHERE id = ?
        """, (error[:500], slot_id))
        conn.commit()
    finally:
        conn.close()


def _save_vlm_result(slot_id: str, result: Dict[str, Any], conn: sqlite3.Connection):
    """
    Persiste el resultado VLM como discrepancia en la tabla discrepancias.

    Crea la tabla si no existe (dev runtime — el schema completo está en schema_sqlite.sql).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS discrepancias (
            id TEXT PRIMARY KEY,
            mesa_key TEXT NOT NULL,
            acta_oficial_id TEXT,
            evidencia_ciudadana_id TEXT,
            campo_afectado TEXT NOT NULL,
            valor_oficial TEXT,
            valor_ciudadano TEXT,
            tipo_anomalia TEXT NOT NULL,
            score_capa0 REAL,
            score_capa1 REAL,
            score_capa2 REAL,
            razon_flag TEXT,
            evidencia_imagen_recorte_url TEXT,
            prioridad TEXT DEFAULT 'media',
            estado TEXT NOT NULL DEFAULT 'por_verificar',
            votos_confirma INTEGER DEFAULT 0,
            votos_rechaza INTEGER DEFAULT 0,
            congelado INTEGER DEFAULT 0,
            creado_en TEXT DEFAULT (datetime('now')),
            actualizado_en TEXT DEFAULT (datetime('now'))
        )
    """)

    discrepancy_id = str(uuid.uuid4())
    cell_results = result.get("resultados", [])
    for cr in cell_results:
        anomalies = cr.get("anomalies", [])
        if not anomalies and cr.get("confidence", 0) < 0.5:
            continue

        razon = ", ".join(anomalies) if anomalies else f"VLM confidence: {cr.get('confidence', 0):.2f}"
        prioridad = "alta" if cr.get("confidence", 0) > 0.85 else "media"

        conn.execute("""
            INSERT INTO discrepancias
                (id, mesa_key, tipo_anomalia, campo_afectado,
                 score_capa2, razon_flag, prioridad, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'por_verificar')
        """, (
            str(uuid.uuid4()),
            result.get("mesa_key", "unknown"),
            "tachon_sobreescritura" if "tachón" in razon.lower() else "trazo_anomalo",
            f"celda_{cr.get('cell_index', 0)}",
            cr.get("confidence", 0.0),
            razon,
            prioridad,
        ))


# ── Worker function ──────────────────────────────────────────────

def _vlm_worker(
    worker_id: str,
    api_key: str,
    max_slots: int = 20,
    db_path: Path = _DB_PATH,
) -> Dict[str, Any]:
    """
    Un worker VLM que procesa slots hasta que no haya más o alcance max_slots.

    Returns:
        {"worker_id": str, "processed": int, "errors": int, "slots": [...]}
    """
    processed = 0
    errors = 0
    slot_results = []

    # Override temporal de la API key para este worker
    original_key = os.environ.get("NVIDIA_API_KEY", "")
    os.environ["NVIDIA_API_KEY"] = api_key

    try:
        for _ in range(max_slots):
            slot = _take_next_slot(worker_id, db_path)
            if slot is None:
                break

            slot_id = slot["id"]
            image_b64 = slot.get("image_b64", "")
            mesa_key = slot.get("mesa_key", "unknown")

            if not image_b64:
                _mark_slot_error(slot_id, "No image_b64 in slot")
                errors += 1
                continue

            # Rate limit por key
            _rate_limit_for_key(api_key)

            try:
                # Analizar la imagen con VLM (reutiliza analyze_cell_vlm)
                vlm_result = analyze_cell_vlm(
                    base64_image=image_b64,
                    cell_index=0,
                    context=f"Evidencia ciudadana mesa {mesa_key}",
                )

                result = {
                    "mesa_key": mesa_key,
                    "slot_id": slot_id,
                    "resultados": [vlm_result],
                    "errores": 1 if vlm_result.get("vlm_error") else 0,
                }

                _mark_slot_completed(slot_id, result, db_path)
                processed += 1
                slot_results.append({
                    "slot_id": slot_id[:8],
                    "mesa_key": mesa_key,
                    "confidence": vlm_result.get("confidence", 0),
                    "anomalies": vlm_result.get("anomalies", []),
                })

            except Exception as e:
                logger.error("Worker %s error on slot %s: %s", worker_id, slot_id, e)
                _mark_slot_error(slot_id, str(e))
                errors += 1
    finally:
        # Restaurar la key original
        os.environ["NVIDIA_API_KEY"] = original_key

    return {
        "worker_id": worker_id,
        "processed": processed,
        "errors": errors,
        "slots": slot_results,
    }


# ── Concurrent batch orchestrator ────────────────────────────────

def run_vlm_workers(
    max_workers: int = 3,
    max_slots_per_worker: int = 20,
    db_path: Path = _DB_PATH,
) -> Dict[str, Any]:
    """
    Lanza N workers VLM concurrentes, cada uno con una API key dedicada.

    Args:
        max_workers: Número de workers concurrentes (máximo = número de API keys).
        max_slots_per_worker: Máximo de slots que procesa cada worker.
        db_path: Ruta a la base de datos SQLite.

    Returns:
        {
            "workers_started": int,
            "total_processed": int,
            "total_errors": int,
            "worker_results": [...],
            "elapsed_seconds": float,
        }
    """
    t_start = time.time()

    available_keys = _get_available_keys()
    if not available_keys:
        return {
            "workers_started": 0,
            "total_processed": 0,
            "total_errors": 0,
            "error": "No NVIDIA API keys found in environment",
            "worker_results": [],
            "elapsed_seconds": 0,
        }

    n_workers = min(max_workers, len(available_keys))
    logger.info("Starting %d VLM workers with %d keys", n_workers, len(available_keys))

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures: List[Future] = []
        for i in range(n_workers):
            worker_id = f"vlm-worker-{i+1}"
            api_key = available_keys[i % len(available_keys)]
            futures.append(
                executor.submit(_vlm_worker, worker_id, api_key, max_slots_per_worker, db_path)
            )

        worker_results = []
        for fut in futures:
            try:
                result = fut.result(timeout=600)  # 10 min max per worker
                worker_results.append(result)
            except Exception as e:
                logger.error("Worker future failed: %s", e)
                worker_results.append({
                    "worker_id": "unknown",
                    "processed": 0,
                    "errors": 1,
                    "error": str(e),
                    "slots": [],
                })

    total_processed = sum(r.get("processed", 0) for r in worker_results)
    total_errors = sum(r.get("errors", 0) for r in worker_results)
    elapsed = time.time() - t_start

    summary = {
        "workers_started": n_workers,
        "total_processed": total_processed,
        "total_errors": total_errors,
        "worker_results": worker_results,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info("VLM workers done: %d processed, %d errors in %.2fs",
                total_processed, total_errors, elapsed)
    return summary


# ── CLI para pruebas ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_vlm_workers(max_workers=3, max_slots_per_worker=5)
    print(json.dumps(result, indent=2, ensure_ascii=False))

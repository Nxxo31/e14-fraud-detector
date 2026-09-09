"""
F8 — Puente de base de datos para verificación ciudadana y consenso democrático.

Gestiona:
  - Registro de votos ciudadanos sobre discrepancias.
  - Cálculo de consenso (umbral de votos + umbral de porcentaje).
  - Congelación automática de discrepancias verificadas.
  - Configuración del sistema (umbrales ajustables en runtime).

Usa SQLite para dev y Supabase para prod — mismo patrón que api/database.py.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"


def _get_db(db_path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    """Crea las tablas F8 si no existen (dev fallback)."""
    # Use individual execute() calls — executescript() implicitly commits
    # which interferes with the BEGIN IMMEDIATE in cast_vote().
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS votos_verificacion_ciudadana (
            id TEXT PRIMARY KEY,
            discrepancia_id TEXT NOT NULL,
            votante_id TEXT,
            votante_ip_hash TEXT,
            voto TEXT NOT NULL CHECK (voto IN ('confirma_legitimo','confirma_anomalo')),
            comentario TEXT,
            peso_reputacion REAL DEFAULT 1.00,
            anulado INTEGER DEFAULT 0,
            anulado_razon TEXT,
            creado_en TEXT DEFAULT (datetime('now')),
            UNIQUE (discrepancia_id, votante_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_sistema (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL,
            descripcion TEXT,
            actualizado_en TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_votos_discrepancia
        ON votos_verificacion_ciudadana (discrepancia_id)
    """)

    # Seed de configuración por defecto
    defaults = [
        ("umbral_min_votos", "5", "Número mínimo de votos ciudadanos para evaluar consenso"),
        ("umbral_consenso_pct", "0.80", "Porcentaje mínimo de consenso en una dirección"),
        ("capa1_score_revision", "0.60", "Score mínimo de Capa 1 para enviar a Capa 2"),
        ("capa1_score_prioridad_alta", "0.85", "Score mínimo para prioridad alta"),
    ]
    for clave, valor, desc in defaults:
        conn.execute("""
            INSERT OR IGNORE INTO configuracion_sistema (clave, valor, descripcion)
            VALUES (?, ?, ?)
        """, (clave, valor, desc))


def get_config(clave: str, db_path: Path = _DB_PATH) -> str:
    """Obtiene un valor de configuración del sistema."""
    conn = _get_db(db_path)
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT valor FROM configuracion_sistema WHERE clave = ?", (clave,)
    ).fetchone()
    conn.close()
    return row["valor"] if row else ""


def set_config(clave: str, valor: str, descripcion: Optional[str] = None,
               db_path: Path = _DB_PATH):
    """Actualiza un valor de configuración (solo admin)."""
    conn = _get_db(db_path)
    conn.execute("""
        INSERT INTO configuracion_sistema (clave, valor, descripcion, actualizado_en)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(clave) DO UPDATE SET
            valor = excluded.valor,
            descripcion = COALESCE(excluded.descripcion, configuracion_sistema.descripcion),
            actualizado_en = datetime('now')
    """, (clave, valor, descripcion))
    conn.commit()
    conn.close()


def _hash_ip(ip: str) -> str:
    """Genera un hash SHA-256 de una IP (nunca se guarda la IP en crudo)."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:64]


def _get_consenso_config(db_path: Path = _DB_PATH) -> Dict[str, float]:
    """Obtiene los umbrales de consenso desde configuracion_sistema."""
    umbral_min = int(get_config("umbral_min_votos", db_path) or "5")
    umbral_pct = float(get_config("umbral_consenso_pct", db_path) or "0.80")
    return {"umbral_min_votos": umbral_min, "umbral_consenso_pct": umbral_pct}


def _evaluate_consensus(discrepancia_id: str, conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Evalúa si una discrepancia puede ser congelada por consenso.

    No se debe llamar directamente — se invoca desde cast_vote()
    dentro de una transacción atómica.
    """
    # Recuentar votos (no anulados)
    rows = conn.execute("""
        SELECT voto, COUNT(*) as cnt, SUM(peso_reputacion) as peso_total
        FROM votos_verificacion_ciudadana
        WHERE discrepancia_id = ? AND anulado = 0
        GROUP BY voto
    """, (discrepancia_id,)).fetchall()

    confirma = 0
    rechaza = 0
    peso_confirma = 0.0
    peso_rechaza = 0.0

    for row in rows:
        if row["voto"] == "confirma_legitimo":
            confirma = row["cnt"]
            peso_confirma = row["peso_total"] or 0
        elif row["voto"] == "confirma_anomalo":
            rechaza = row["cnt"]
            peso_rechaza = row["peso_total"] or 0

    total = confirma + rechaza

    # Actualizar contadores en la discrepancia
    conn.execute("""
        UPDATE discrepancias
        SET votos_confirma = ?, votos_rechaza = ?, actualizado_en = datetime('now')
        WHERE id = ?
    """, (confirma, rechaza, discrepancia_id))

    # Leer configuración dentro de la MISMA conexión (evita deadlock por
    # abrir otra conexión mientras BEGIN IMMEDIATE tiene el lock de escritura)
    umbral_min_row = conn.execute(
        "SELECT valor FROM configuracion_sistema WHERE clave = 'umbral_min_votos'"
    ).fetchone()
    umbral_pct_row = conn.execute(
        "SELECT valor FROM configuracion_sistema WHERE clave = 'umbral_consenso_pct'"
    ).fetchone()

    umbral_min = int(umbral_min_row["valor"]) if umbral_min_row else 5
    umbral_pct = float(umbral_pct_row["valor"]) if umbral_pct_row else 0.80

    congelado = False
    estado_final: Optional[str] = None
    razon_consenso = ""

    if total >= umbral_min:
        disc_row = conn.execute(
            "SELECT congelado FROM discrepancias WHERE id = ?", (discrepancia_id,)
        ).fetchone()

        if disc_row and disc_row["congelado"] == 0:
            if total > 0 and confirma / total >= umbral_pct:
                conn.execute("""
                    UPDATE discrepancias
                    SET estado = 'verificado_legitimo', congelado = 1,
                        actualizado_en = datetime('now')
                    WHERE id = ?
                """, (discrepancia_id,))
                congelado = True
                estado_final = "verificado_legitimo"
                razon_consenso = f"Consenso legítimo: {confirma}/{total} ≥ {umbral_pct:.0%}"

            elif total > 0 and rechaza / total >= umbral_pct:
                conn.execute("""
                    UPDATE discrepancias
                    SET estado = 'verificado_anomalo', congelado = 1,
                        actualizado_en = datetime('now')
                    WHERE id = ?
                """, (discrepancia_id,))
                congelado = True
                estado_final = "verificado_anomalo"
                razon_consenso = f"Consenso anómalo: {rechaza}/{total} ≥ {umbral_pct:.0%}"

    return {
        "votos_confirma": confirma,
        "votos_rechaza": rechaza,
        "total_votos": total,
        "peso_confirma": round(peso_confirma, 2),
        "peso_rechaza": round(peso_rechaza, 2),
        "congelado": congelado,
        "estado_final": estado_final,
        "razon_consenso": razon_consenso,
        "umbral_min_votos": umbral_min,
        "umbral_consenso_pct": umbral_pct,
    }


def cast_vote(
    discrepancia_id: str,
    voto: str,
    votante_id: Optional[str] = None,
    votante_ip: Optional[str] = None,
    comentario: Optional[str] = None,
    peso_reputacion: float = 1.0,
    db_path: Path = _DB_PATH,
) -> Dict[str, Any]:
    """
    Registra un voto ciudadano sobre una discrepancia y evalúa el consenso.

    Args:
        discrepancia_id: UUID de la discrepancia.
        voto: 'confirma_legitimo' o 'confirma_anomalo'.
        votante_id: ID del votante (UUID o None para anónimo).
        votante_ip: IP del votante (se hashea, nunca se guarda en crudo).
        comentario: Texto opcional del votante.
        peso_reputacion: Multiplicador de peso (default 1.0).
        db_path: Ruta a la DB.

    Returns:
        {
            "voto_id": str,
            "discrepancia_id": str,
            "voto": str,
            "consenso": {...},
            "error": Optional[str],
        }

    Raises:
        ValueError si el voto es invalido o la discrepancia está congelada.
    """
    if voto not in ("confirma_legitimo", "confirma_anomalo"):
        raise ValueError(f"Voto inválido: {voto}. Debe ser 'confirma_legitimo' o 'confirma_anomalo'")

    conn = _get_db(db_path)
    _ensure_tables(conn)
    # Commit any implicit transactions opened by _ensure_tables DDL/DML
    # so BEGIN IMMEDIATE can start cleanly.
    conn.commit()

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Verificar que la discrepancia existe y no está congelada
        disc = conn.execute(
            "SELECT id, congelado, mesa_key FROM discrepancias WHERE id = ?",
            (discrepancia_id,)
        ).fetchone()

        if disc is None:
            conn.execute("ROLLBACK")
            return {
                "voto_id": None,
                "discrepancia_id": discrepancia_id,
                "voto": voto,
                "consenso": None,
                "error": "Discrepancia no encontrada",
            }

        if disc["congelado"] == 1:
            conn.execute("ROLLBACK")
            return {
                "voto_id": None,
                "discrepancia_id": discrepancia_id,
                "voto": voto,
                "consenso": None,
                "error": "Esta discrepancia ya fue verificada y está congelada",
            }

        # Generar IP hash
        ip_hash = _hash_ip(votante_ip) if votante_ip else None

        # Generar un votante_id anónimo si no se provee (para idempotencia)
        if not votante_id:
            votante_id = f"anon-{ip_hash}" if ip_hash else f"anon-{uuid.uuid4()}"[:36]

        # Verificar que no haya votado ya (unique constraint)
        existing = conn.execute("""
            SELECT id FROM votos_verificacion_ciudadana
            WHERE discrepancia_id = ? AND votante_id = ?
        """, (discrepancia_id, votante_id)).fetchone()

        if existing:
            conn.execute("ROLLBACK")
            return {
                "voto_id": existing["id"],
                "discrepancia_id": discrepancia_id,
                "voto": voto,
                "consenso": None,
                "error": "Este votante ya registró un voto sobre esta discrepancia",
            }

        # Insertar el voto
        voto_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO votos_verificacion_ciudadana
                (id, discrepancia_id, votante_id, votante_ip_hash,
                 voto, comentario, peso_reputacion, anulado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (voto_id, discrepancia_id, votante_id, ip_hash,
              voto, comentario, peso_reputacion))

        # Evaluar consenso
        consenso = _evaluate_consensus(discrepancia_id, conn)

        conn.execute("COMMIT")

        return {
            "voto_id": voto_id,
            "discrepancia_id": discrepancia_id,
            "voto": voto,
            "consenso": consenso,
            "error": None,
        }

    except sqlite3.IntegrityError as e:
        conn.execute("ROLLBACK")
        logger.warning("Vote integrity error: %s", e)
        return {
            "voto_id": None,
            "discrepancia_id": discrepancia_id,
            "voto": voto,
            "consenso": None,
            "error": f"Violación de integridad: {e}",
        }
    except Exception as e:
        conn.execute("ROLLBACK")
        logger.error("Vote error: %s", e)
        return {
            "voto_id": None,
            "discrepancia_id": discrepancia_id,
            "voto": voto,
            "consenso": None,
            "error": str(e),
        }
    finally:
        conn.close()


def get_discrepancia_status(discrepancia_id: str, db_path: Path = _DB_PATH) -> Dict[str, Any]:
    """Obtiene el estado completo de una discrepancia: votos, consenso, configuración."""
    conn = _get_db(db_path)
    _ensure_tables(conn)

    disc = conn.execute("""
        SELECT id, mesa_key, campo_afectado, valor_oficial, valor_ciudadano,
               tipo_anomalia, score_capa0, score_capa1, score_capa2,
               razon_flag, prioridad, estado,
               votos_confirma, votos_rechaza, congelado,
               creado_en, actualizado_en
        FROM discrepancias WHERE id = ?
    """, (discrepancia_id,)).fetchone()

    if disc is None:
        conn.close()
        return {"error": "Discrepancia no encontrada", "discrepancia_id": discrepancia_id}

    votes = conn.execute("""
        SELECT id, votante_id, voto, comentario, peso_reputacion,
               anulado, anulado_razon, creado_en
        FROM votos_verificacion_ciudadana
        WHERE discrepancia_id = ?
        ORDER BY creado_en DESC
    """, (discrepancia_id,)).fetchall()

    config = _get_consenso_config(db_path)
    conn.close()

    return {
        "discrepancia": dict(disc),
        "votos": [dict(v) for v in votes],
        "total_votos": len(votes),
        "configuracion": config,
    }


def get_pending_discrepancias(
    mesa_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Path = _DB_PATH,
) -> Dict[str, Any]:
    """
    Obtiene las discrepancias pendientes de verificación ciudadana (cola).

    Ordenadas por prioridad (alta → media → baja) y luego por fecha (más antigua primero).
    """
    conn = _get_db(db_path)
    _ensure_tables(conn)

    query = """
        SELECT id, mesa_key, campo_afectado, valor_oficial, valor_ciudadano,
               tipo_anomalia, score_capa0, score_capa1, score_capa2,
               razon_flag, prioridad, estado,
               votos_confirma, votos_rechaza,
               creado_en
        FROM discrepancias
        WHERE estado = 'por_verificar' AND congelado = 0
    """
    params: List[Any] = []
    if mesa_key:
        query += " AND mesa_key = ?"
        params.append(mesa_key)

    query += """
        ORDER BY CASE prioridad
            WHEN 'alta' THEN 1
            WHEN 'media' THEN 2
            WHEN 'baja' THEN 3
        END, creado_en ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE estado = 'por_verificar' AND congelado = 0"
    ).fetchone()[0]
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(r) for r in rows],
    }


def get_consensus_summary(db_path: Path = _DB_PATH) -> Dict[str, Any]:
    """Obtiene estadísticas globales del sistema de consenso democrático."""
    conn = _get_db(db_path)
    _ensure_tables(conn)

    total_disc = conn.execute("SELECT COUNT(*) FROM discrepancias").fetchone()[0]
    por_verificar = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE estado = 'por_verificar'"
    ).fetchone()[0]
    verificadas_legitimas = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE estado = 'verificado_legitimo'"
    ).fetchone()[0]
    verificadas_anomalas = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE estado = 'verificado_anomalo'"
    ).fetchone()[0]
    congeladas = conn.execute(
        "SELECT COUNT(*) FROM discrepancias WHERE congelado = 1"
    ).fetchone()[0]
    total_votos = conn.execute(
        "SELECT COUNT(*) FROM votos_verificacion_ciudadana WHERE anulado = 0"
    ).fetchone()[0]
    votos_unicos = conn.execute(
        "SELECT COUNT(DISTINCT votante_id) FROM votos_verificacion_ciudadana WHERE anulado = 0"
    ).fetchone()[0]

    config = _get_consenso_config(db_path)
    conn.close()

    return {
        "total_discrepancias": total_disc,
        "por_verificar": por_verificar,
        "verificadas_legitimas": verificadas_legitimas,
        "verificadas_anomalas": verificadas_anomalas,
        "congeladas": congeladas,
        "total_votos_ciudadanos": total_votos,
        "votantes_unicos": votos_unicos,
        "configuracion": config,
    }

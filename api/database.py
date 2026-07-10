"""Base de datos SQLite para la API E14."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"


def get_db() -> sqlite3.Connection:
    """Devuelve una conexión a la base de datos."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa/esquema la base de datos."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS actas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mesa_key TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            score_global REAL DEFAULT 0.0,
            score_arithmetical REAL DEFAULT 0.0,
            score_visual_promedio REAL DEFAULT 0.0,
            score_visual_max REAL DEFAULT 0.0,
            celdas_sospechosas INTEGER DEFAULT 0,
            total_celdas INTEGER DEFAULT 0,
            veredicto TEXT DEFAULT 'PENDIENTE',
            resultado_json TEXT,
            fecha_analisis TEXT,
            fecha_revision TEXT,
            revisado_por TEXT DEFAULT ''
        );
    """)

    conn.commit()
    conn.close()


def upsert_acta(data: dict) -> int:
    """Inserta o actualiza un acta en la base de datos."""
    conn = get_db()
    cursor = conn.cursor()

    import json

    # Extraer scores del resultado si existe
    resultado = data.get("resultado", {})
    score_components = resultado.get("score_components", {})
    visual_summary = resultado.get("visual_summary", {})

    cursor.execute("""
        INSERT INTO actas (
            mesa_key, filename, score_global,
            score_arithmetical, score_visual_promedio, score_visual_max,
            celdas_sospechosas, total_celdas,
            veredicto, resultado_json, fecha_analisis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mesa_key) DO UPDATE SET
            filename = excluded.filename,
            score_global = excluded.score_global,
            score_arithmetical = excluded.score_arithmetical,
            score_visual_promedio = excluded.score_visual_promedio,
            score_visual_max = excluded.score_visual_max,
            celdas_sospechosas = excluded.celdas_sospechosas,
            total_celdas = excluded.total_celdas,
            veredicto = excluded.veredicto,
            resultado_json = excluded.resultado_json,
            fecha_analisis = excluded.fecha_analisis
    """, (
        data["mesa_key"],
        data.get("filename", ""),
        resultado.get("score_global", 0.0),
        score_components.get("score_arithmetical", 0.0),
        score_components.get("score_visual_promedio", 0.0),
        score_components.get("score_visual_max", 0.0),
        score_components.get("celdas_sospechosas", 0),
        score_components.get("total_celdas", 0),
        resultado.get("veredicto", "PENDIENTE"),
        json.dumps(resultado, ensure_ascii=False) if resultado else None,
        resultado.get("analizado_en", "")
    ))

    conn.commit()
    acta_id = cursor.lastrowid
    conn.close()
    return acta_id


def get_all_actas() -> list:
    """Obtiene todas las actas."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, mesa_key, filename, score_global, veredicto,
               celdas_sospechosas, total_celdas, fecha_analisis, fecha_revision
        FROM actas ORDER BY fecha_analisis DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_acta(acta_id: int) -> dict | None:
    """Obtiene un acta por ID."""
    conn = get_db()
    row = conn.execute("SELECT * FROM actas WHERE id = ?", (acta_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_veredicto(acta_id: int, veredicto: str, revisor: str = ""):
    """Actualiza el veredicto de un acta (revisión humana)."""
    from datetime import datetime
    conn = get_db()
    conn.execute("""
        UPDATE actas SET veredicto = ?, fecha_revision = ?, revisado_por = ?
        WHERE id = ?
    """, (veredicto, datetime.now().isoformat(), revisor, acta_id))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Obtiene estadísticas del dashboard."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM actas").fetchone()[0]
    legitimas = conn.execute("SELECT COUNT(*) FROM actas WHERE veredicto = 'LEGITIMA'").fetchone()[0]
    sospechosas = conn.execute("SELECT COUNT(*) FROM actas WHERE veredicto = 'SOSPECHOSA'").fetchone()[0]
    ilegitimas = conn.execute("SELECT COUNT(*) FROM actas WHERE veredicto = 'ILEGITIMA'").fetchone()[0]
    pendientes = conn.execute("SELECT COUNT(*) FROM actas WHERE veredicto = 'PENDIENTE'").fetchone()[0]
    conn.close()

    return {
        "total": total,
        "legitimas": legitimas,
        "sospechosas": sospechosas,
        "ilegitimas": ilegitimas,
        "pendientes": pendientes
    }
"""
F7 — Motor de comparación oficial vs ciudadano.

Compara los datos extraídos de las actas oficiales (actas_oficiales)
con la evidencia ciudadana (evidencia_ciudadana) y genera discrepancias
tipadas con 'discrepancia_oficial_vs_ciudadano'.

Lógica de comparación:
  1. Para cada mesa_key, buscar el acta oficial (datos canónicos).
  2. Buscar evidencias ciudadanas (fotos de la misma mesa).
  3. Extraer votos_extraidos de la evidencia (JSON en votos_extraidos).
  4. Comparar campo por campo: votos_candidato_1, votos_candidato_2,
     votos_blanco, votos_nulos, votos_no_marcados, total_votos_urna.
  5. Generar discrepancia si el valor ciudadano difiere del oficial
     por encima de la tolerancia configurable (default: 0 votos).

Las discrepancias se insertan en la tabla `discrepancias` con
tipo_anomalia='discrepancia_oficial_vs_ciudadano'.
"""
from __future__ import annotations

import json
import sqlite3
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "e14_audit.db"

# Campos comparables y su etiqueta legible
COMPARABLE_FIELDS: Dict[str, str] = {
    "votos_candidato_1": "Votos candidato 1",
    "votos_candidato_2": "Votos candidato 2",
    "votos_blanco": "Votos en blanco",
    "votos_nulos": "Votos nulos",
    "votos_no_marcados": "Votos no marcados",
    "total_votos_urna": "Total votos urna",
    "total_votantes_e11": "Total votantes E-11",
    "total_votos_incinerados": "Votos incinerados",
}


@dataclass
class ComparisonResult:
    """Resultado de comparar un campo oficial vs ciudadano."""
    campo: str
    valor_oficial: Any
    valor_ciudadano: Any
    diferencia: Optional[int]
    es_discrepancia: bool
    score: float = 0.0
    prioridad: str = "media"


@dataclass
class MesaComparison:
    """Resultado de comparar una mesa completa."""
    mesa_key: str
    acta_oficial_id: Optional[str] = None
    evidencias_ciudadanas: int = 0
    discrepancias: List[ComparisonResult] = field(default_factory=list)
    total_campos_comparados: int = 0
    total_discrepancias: int = 0


def _parse_value(valor: Any) -> Optional[int]:
    """Intenta convertir un valor a int para comparación."""
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    if isinstance(valor, str):
        try:
            return int(valor.strip())
        except ValueError:
            return None
    return None


def _score_discrepancia(diferencia: int) -> Tuple[float, str]:
    """
    Calcula el score y prioridad de una discrepancia basado en la magnitud.

    Score de 0.0 a 1.0: 0=sin diff, 1=diff muy alta.
    Prioridad: baja (<5), media (5-20), alta (>20).
    """
    abs_diff = abs(diferencia)
    score = min(1.0, abs_diff / 50.0)
    if abs_diff > 20:
        prioridad = "alta"
    elif abs_diff > 5:
        prioridad = "media"
    else:
        prioridad = "baja"
    return round(score, 4), prioridad


def compare_field(
    campo: str,
    valor_oficial: Any,
    valor_ciudadano: Any,
    tolerancia: int = 0,
) -> ComparisonResult:
    """
    Compara un campo individual entre oficial y ciudadano.

    Args:
        campo: Nombre del campo (ej: "votos_candidato_1").
        valor_oficial: Valor del acta oficial.
        valor_ciudadano: Valor de la evidencia ciudadana.
        tolerancia: Diferencia permitida sin generar discrepancia (default 0).

    Returns:
        ComparisonResult con es_discrepancia=True si |diff| > tolerancia.
    """
    v_oficial = _parse_value(valor_oficial)
    v_ciudadano = _parse_value(valor_ciudadano)

    # Si alguno es None no se puede comparar
    if v_oficial is None or v_ciudadano is None:
        return ComparisonResult(
            campo=campo,
            valor_oficial=valor_oficial,
            valor_ciudadano=valor_ciudadano,
            diferencia=None,
            es_discrepancia=False,
            score=0.0,
            prioridad="baja",
        )

    diff = v_ciudadano - v_oficial
    es_disc = abs(diff) > tolerancia

    if es_disc:
        score, prioridad = _score_discrepancia(diff)
    else:
        score, prioridad = 0.0, "baja"

    return ComparisonResult(
        campo=campo,
        valor_oficial=v_oficial,
        valor_ciudadano=v_ciudadano,
        diferencia=diff,
        es_discrepancia=es_disc,
        score=score,
        prioridad=prioridad,
    )


def compare_mesa(
    mesa_key: str,
    datos_oficiales: Dict[str, Any],
    datos_ciudadanos: Dict[str, Any],
    tolerancia: int = 0,
) -> MesaComparison:
    """
    Compara todos los campos comparables de una mesa.

    Args:
        mesa_key: Clave de la mesa.
        datos_oficiales: Dict con campos del acta oficial.
        datos_ciudadanos: Dict con campos extraídos de evidencia ciudadana.
        tolerancia: Diferencia permitida.

    Returns:
        MesaComparison con lista de discrepancias.
    """
    result = MesaComparison(mesa_key=mesa_key)
    result.total_campos_comparados = 0

    for campo, _label in COMPARABLE_FIELDS.items():
        v_oficial = datos_oficiales.get(campo)
        v_ciudadano = datos_ciudadanos.get(campo)

        if v_oficial is None and v_ciudadano is None:
            continue  # Ningún dato para este campo

        comp = compare_field(campo, v_oficial, v_ciudadano, tolerancia)
        result.total_campos_comparados += 1

        if comp.es_discrepancia:
            result.discrepancias.append(comp)

    result.total_discrepancias = len(result.discrepancias)
    return result


# ── Database operations ──────────────────────────────────────────

def _get_db(db_path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_discrepancias_table(conn: sqlite3.Connection):
    """Crea la tabla discrepancias si no existe (dev fallback)."""
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
        CREATE TABLE IF NOT EXISTS actas_oficiales (
            id TEXT PRIMARY KEY,
            mesa_key TEXT NOT NULL,
            codigo_departamento TEXT,
            codigo_municipio TEXT,
            zona TEXT,
            puesto TEXT,
            mesa TEXT,
            lugar_votacion TEXT,
            tipo_ejemplar TEXT,
            pdf_url TEXT,
            pdf_storage_path TEXT,
            kit_numero TEXT,
            formulario_numero TEXT,
            version_formato TEXT,
            qr_raw_value TEXT,
            qr_decoded_match INTEGER,
            paginas_total INTEGER,
            paginas_esperadas INTEGER,
            pagina_2_vacia INTEGER,
            firmas_detectadas INTEGER,
            total_votantes_e11 INTEGER,
            total_votos_urna INTEGER,
            total_votos_incinerados INTEGER,
            votos_candidato_1 INTEGER,
            votos_candidato_2 INTEGER,
            votos_blanco INTEGER,
            votos_nulos INTEGER,
            votos_no_marcados INTEGER,
            suma_total_calculada INTEGER,
            flag_aritmetica_excede_total INTEGER DEFAULT 0,
            flag_aritmetica_no_coincide INTEGER DEFAULT 0,
            flag_nivelacion_inconsistente INTEGER DEFAULT 0,
            flag_paginas_incompletas INTEGER DEFAULT 0,
            flag_firmas_insuficientes INTEGER DEFAULT 0,
            flag_qr_metadata_mismatch INTEGER DEFAULT 0,
            capa_maxima_procesada INTEGER DEFAULT 0,
            estado_procesamiento TEXT DEFAULT 'pendiente',
            creado_en TEXT DEFAULT (datetime('now')),
            actualizado_en TEXT DEFAULT (datetime('now')),
            UNIQUE (mesa_key, tipo_ejemplar)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidencia_ciudadana (
            id TEXT PRIMARY KEY,
            mesa_key TEXT NOT NULL,
            imagen_url TEXT,
            imagen_storage_path TEXT,
            aportante_id TEXT,
            aportante_ip_hash TEXT,
            votos_extraidos TEXT,
            metodo_extraccion TEXT,
            confianza_extraccion REAL,
            estado_revision TEXT DEFAULT 'pendiente',
            creado_en TEXT DEFAULT (datetime('now'))
        )
    """)


def persist_discrepancias(comparison: MesaComparison, db_path: Path = _DB_PATH) -> List[str]:
    """
    Inserta las discrepancias de una MesaComparison en la DB.

    Returns:
        Lista de IDs de discrepancias creadas.
    """
    if not comparison.discrepancias:
        return []

    conn = _get_db(db_path)
    _ensure_discrepancias_table(conn)
    created_ids = []

    try:
        for disc in comparison.discrepancias:
            disc_id = str(uuid.uuid4())
            razon = (
                f"Diferencia de {abs(disc.diferencia or 0)} voto(s) en {COMPARABLE_FIELDS.get(disc.campo, disc.campo)}. "
                f"Oficial={disc.valor_oficial}, Ciudadano={disc.valor_ciudadano}"
            )

            conn.execute("""
                INSERT INTO discrepancias
                    (id, mesa_key, acta_oficial_id, evidencia_ciudadana_id,
                     campo_afectado, valor_oficial, valor_ciudadano,
                     tipo_anomalia, score_capa0, razon_flag, prioridad, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'por_verificar')
            """, (
                disc_id,
                comparison.mesa_key,
                comparison.acta_oficial_id,
                None,  # evidencia_ciudadana_id se asigna en batch
                disc.campo,
                str(disc.valor_oficial) if disc.valor_oficial is not None else None,
                str(disc.valor_ciudadano) if disc.valor_ciudadano is not None else None,
                "discrepancia_oficial_vs_ciudadano",
                disc.score,
                razon,
                disc.prioridad,
            ))
            created_ids.append(disc_id)

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Error persisting discrepancies: %s", e)
        raise
    finally:
        conn.close()

    return created_ids


def run_comparison_for_mesa(mesa_key: str, tolerancia: int = 0, db_path: Path = _DB_PATH) -> Dict[str, Any]:
    """
    Ejecuta la comparación oficial vs ciudadano para una mesa específica.

    1. Lee el acta oficial de SQLite.
    2. Lee todas las evidencias ciudadanas para esa mesa.
    3. Si hay evidencias con votos_extraidos, compara contra el oficial.
    4. Persiste las discrepancias encontradas.

    Returns:
        {
            "mesa_key": str,
            "acta_oficial_encontrada": bool,
            "evidencias_ciudadanas": int,
            "campos_comparados": int,
            "discrepancias_generadas": int,
            "discrepancia_ids": [str],
        }
    """
    conn = _get_db(db_path)
    _ensure_discrepancias_table(conn)

    # 1. Buscar acta oficial
    row_oficial = conn.execute("""
        SELECT * FROM actas_oficiales WHERE mesa_key = ?
        ORDER BY creado_en DESC LIMIT 1
    """, (mesa_key,)).fetchone()

    if row_oficial is None:
        conn.close()
        return {
            "mesa_key": mesa_key,
            "acta_oficial_encontrada": False,
            "evidencias_ciudadanas": 0,
            "campos_comparados": 0,
            "discrepancias_generadas": 0,
            "discrepancia_ids": [],
            "error": "No se encontró acta oficial para esta mesa_key",
        }

    datos_oficiales = dict(row_oficial)

    # 2. Buscar evidencias ciudadanas
    rows_evidencia = conn.execute("""
        SELECT * FROM evidencia_ciudadana
        WHERE mesa_key = ? AND estado_revision != 'rechazada_calidad'
        ORDER BY creado_en
    """, (mesa_key,)).fetchall()

    conn.close()

    if not rows_evidencia:
        return {
            "mesa_key": mesa_key,
            "acta_oficial_encontrada": True,
            "acta_oficial_id": datos_oficiales.get("id"),
            "evidencias_ciudadanas": 0,
            "campos_comparados": 0,
            "discrepancias_generadas": 0,
            "discrepancia_ids": [],
            "error": "No hay evidencias ciudadanas para comparar",
        }

    # 3. Agregar datos ciudadanos: tomar la evidencia con mayor confianza
    mejor_evidencia = None
    mejor_confianza = -1
    for row_ev in rows_evidencia:
        ev = dict(row_ev)
        confianza = ev.get("confianza_extraccion", 0)
        if confianza is not None and confianza > mejor_confianza:
            mejor_confianza = confianza
            mejor_evidencia = ev

    if mejor_evidencia is None:
        return {
            "mesa_key": mesa_key,
            "acta_oficial_encontrada": True,
            "evidencias_ciudadanas": len(rows_evidencia),
            "campos_comparados": 0,
            "discrepancias_generadas": 0,
            "discrepancia_ids": [],
            "error": "Ninguna evidencia tenia datos extraibles",
        }

    # Parsear votos_extraidos (es JSON TEXT en SQLite, JSONB en Postgres)
    votos_raw = mejor_evidencia.get("votos_extraidos")
    if isinstance(votos_raw, str):
        try:
            datos_ciudadanos = json.loads(votos_raw)
        except json.JSONDecodeError:
            datos_ciudadanos = {}
    elif isinstance(votos_raw, dict):
        datos_ciudadanos = votos_raw
    else:
        datos_ciudadanos = {}

    # 4. Comparar
    comparison = compare_mesa(
        mesa_key=mesa_key,
        datos_oficiales=datos_oficiales,
        datos_ciudadanos=datos_ciudadanos,
        tolerancia=tolerancia,
    )
    comparison.acta_oficial_id = datos_oficiales.get("id")

    # 5. Persistir
    disc_ids = persist_discrepancias(comparison, db_path)

    return {
        "mesa_key": mesa_key,
        "acta_oficial_encontrada": True,
        "acta_oficial_id": datos_oficiales.get("id"),
        "evidencias_ciudadanas": len(rows_evidencia),
        "campos_comparados": comparison.total_campos_comparados,
        "discrepancias_generadas": comparison.total_discrepancias,
        "discrepancia_ids": disc_ids,
    }


def run_comparison_batch(mesa_keys: Optional[List[str]] = None, tolerancia: int = 0,
                         db_path: Path = _DB_PATH) -> Dict[str, Any]:
    """
    Ejecuta la comparación para una lista de mesas.
    Si mesa_keys es None, compara todas las mesas que tienen tanto acta oficial como evidencia.

    Returns:
        {
            "total_mesas": int,
            "mesas_con_discrepancia": int,
            "total_discrepancias": int,
            "resultados": [...],
        }
    """
    conn = _get_db(db_path)
    _ensure_discrepancias_table(conn)

    if mesa_keys is None:
        # Encontrar todas las mesas que tienen evidencia ciudadana procesada
        rows = conn.execute("""
            SELECT DISTINCT mesa_key FROM evidencia_ciudadana
            WHERE estado_revision != 'rechazada_calidad'
        """).fetchall()
        mesa_keys = [r["mesa_key"] for r in rows]

    conn.close()

    resultados = []
    total_discrepancias = 0
    mesas_con_disc = 0

    for mesa_key in mesa_keys:
        try:
            r = run_comparison_for_mesa(mesa_key, tolerancia=tolerancia, db_path=db_path)
            resultados.append(r)
            total_discrepancias += r.get("discrepancias_generadas", 0)
            if r.get("discrepancias_generadas", 0) > 0:
                mesas_con_disc += 1
        except Exception as e:
            logger.error("Error comparing mesa %s: %s", mesa_key, e)
            resultados.append({"mesa_key": mesa_key, "error": str(e)})

    return {
        "total_mesas": len(mesa_keys),
        "mesas_con_discrepancia": mesas_con_disc,
        "total_discrepancias": total_discrepancias,
        "resultados": resultados,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        # CLI: comparar una mesa específica
        result = run_comparison_for_mesa(sys.argv[1])
    else:
        # Batch de todas las mesas con evidencia
        result = run_comparison_batch()

    print(json.dumps(result, indent=2, ensure_ascii=False))

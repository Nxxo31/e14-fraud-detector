"""MVP Pipeline — SQLite storage for analysis results."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .core import RenderedPage


DB_PATH = Path(__file__).parent.parent / "data" / "e14_mvp.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            table_code       TEXT NOT NULL,
            pdf_filename     TEXT NOT NULL,
            pdf_sha256       TEXT,
            processed_at     TEXT NOT NULL,
            signature_status TEXT,
            signatures_found INTEGER,
            signatures_expected INTEGER,
            max_risk         TEXT,
            ocr_confidence   REAL,
            total_votes      INTEGER,
            risk_score       REAL,
            risk_level       TEXT,
            anomaly_count    INTEGER,
            signature_boxes  TEXT,     -- JSON array
            candidate_votes  TEXT,     -- JSON {cand_num: votes}
            anomalies        TEXT,    -- JSON array of anomaly dicts
            page1_ocr_conf   REAL,
            page2_ocr_conf   REAL
        );

        CREATE TABLE IF NOT EXISTS rendered_pages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id     INTEGER NOT NULL REFERENCES analysis_results(id),
            page_number     INTEGER NOT NULL,
            width           INTEGER,
            height          INTEGER,
            dpi             INTEGER,
            image_path      TEXT NOT NULL   -- relative path to PNG
        );
    """)
    conn.commit()
    conn.close()


def save_analysis(
    table_code: str,
    pdf_filename: str,
    pdf_sha256: str,
    sig_result,
    page1_ocr,
    page2_ocr,
    validation_result,
    risk_score,
    pages: list[RenderedPage],
    mvp_dir: Path,
) -> int:
    """Save complete analysis to SQLite + write page PNGs to disk.

    Returns the row ID of the inserted analysis record.
    """
    init_db()
    conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()

    # Serialize signature boxes
    sig_boxes_json = json.dumps([
        {"box_id": b.box_id, "status": b.status, "ink_density": b.ink_density, "risk": b.risk}
        for b in sig_result.boxes
    ])

    # Candidate votes
    cand_votes = {}
    for cand in page1_ocr.candidates:
        cand_votes[cand.candidate_number] = _slots_to_int(cand)
    for cand in page2_ocr.candidates:
        cand_votes[cand.candidate_number] = _slots_to_int(cand)

    # Anomalies
    anomalies_json = json.dumps([
        {"rule": a.rule, "severity": a.severity, "message": a.message,
         "confidence": a.confidence, "page": a.page, "details": a.details}
        for a in validation_result.anomalies
    ])

    cursor = conn.execute("""
        INSERT INTO analysis_results (
            table_code, pdf_filename, pdf_sha256, processed_at,
            signature_status, signatures_found, signatures_expected, max_risk,
            ocr_confidence, total_votes, risk_score, risk_level, anomaly_count,
            signature_boxes, candidate_votes, anomalies,
            page1_ocr_conf, page2_ocr_conf
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        table_code, pdf_filename, pdf_sha256, now,
        sig_result.overall_status, sig_result.signatures_found, sig_result.signatures_expected,
        sig_result.max_risk,
        (page1_ocr.overall_confidence + page2_ocr.overall_confidence) / 2,
        page2_ocr.summary.total_votes if page2_ocr.summary else None,
        risk_score.score, risk_score.level, risk_score.anomaly_count,
        sig_boxes_json, json.dumps(cand_votes), anomalies_json,
        page1_ocr.overall_confidence, page2_ocr.overall_confidence,
    ))
    analysis_id = cursor.lastrowid

    # Save page images
    pages_dir = mvp_dir / "data" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    for page in pages:
        img_path = pages_dir / f"result_{analysis_id}_page{page.page_number}.png"
        page.image.save(img_path, "PNG")
        conn.execute("""
            INSERT INTO rendered_pages (analysis_id, page_number, width, height, dpi, image_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (analysis_id, page.page_number, page.width, page.height, page.dpi, str(img_path)))

    conn.commit()
    conn.close()
    return analysis_id


def _slots_to_int(cand) -> int:
    digits = [str(s.digit) if s.digit is not None else '0' for s in cand.slots]
    return int(''.join(digits)) if digits else 0


def get_result(analysis_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM analysis_results WHERE id = ?", (analysis_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    conn.close()
    return result


def list_results(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, table_code, pdf_filename, processed_at, risk_level, risk_score, anomaly_count "
        "FROM analysis_results ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
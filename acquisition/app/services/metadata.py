"""E14 Acquisition — Metadata collector.

Consumes allTransmissionCodes.json from the Registraduría CDN and stores
the universe of E14 records into PostgreSQL.

This is called ONCE to seed the database, then periodically to refresh.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy.orm import Session

from ..config import CDN_JSON_BASE, JSON_FILES, CURL_CFFI_IMPERSONATE, JSON_TIMEOUT
from ..models import Table, AuditLog
from ..database import SessionLocal
from .rate_limiter import TokenBucket

log = logging.getLogger(__name__)

# Reusable session with Akamai priming
_session = None


def _get_http():
    global _session
    if _session is None:
        from curl_cffi import requests as creq
        _session = creq.Session(impersonate=CURL_CFFI_IMPERSONATE)
        # Prime Akamai cookies
        base = CDN_JSON_BASE.rsplit("/", 2)[0]
        _session.get(f"{base}/", timeout=JSON_TIMEOUT)
    return _session


def fetch_universe_json() -> list[dict]:
    """Fetch and parse allTransmissionCodes.json.

    Returns: list of raw node dicts with expectedName != "".
    """
    url = f"{CDN_JSON_BASE}/{JSON_FILES['transmission_codes']}"
    log.info("Fetching universe: %s", url)

    client = _get_http()
    resp = client.get(url, timeout=JSON_TIMEOUT)
    resp.raise_for_status()

    payload = resp.json()
    data = payload.get("data", payload)

    nodes: list[dict] = []
    for block in data.values():
        for node in (block or {}).get("nodes", []) or []:
            if node.get("expectedName"):
                nodes.append(node)

    log.info("Universe contains %d actas", len(nodes))
    return nodes


def node_to_row(node: dict) -> dict:
    """Convert a JSON node into a dict matching Table model fields."""
    return {
        "dep_code":           str(node.get("idDepartmentCode", "")).zfill(2),
        "muni_code":          str(node.get("municipalityCode", "")).zfill(3),
        "zona_code":          str(node.get("idZoneCode", "")).zfill(3),
        "puesto_code":        str(node.get("standCode", "")).zfill(2),
        "mesa_code":          str(node.get("numberStand", "")).zfill(3),
        "corp_code":          str(node.get("idCorporationCode", "")),
        "expected_name":      str(node.get("expectedName", "")),
        "id_stand":           str(node.get("idStand", "")),
        "id_transmission":    int(node["idTransmissionCode"]) if node.get("idTransmissionCode") else None,
        "transmission_status": int(node.get("idTransmissionCodeStatus", 0)),
    }


def pdf_url_for(node: dict) -> str:
    """Build the CDN PDF URL from a node's geo codes."""
    from ..config import PDF_URL_TEMPLATE
    return PDF_URL_TEMPLATE.format(
        dep=node["dep_code"],
        muni=node["muni_code"],
        zona=node["zona_code"],
        puesto=node["puesto_code"],
        expected_name=node["expected_name"],
    )


def _bulk_upsert_tables(db: Session, rows: list[dict]) -> int:
    """Upsert table rows. Returns count of new records inserted."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    inserted = 0
    for row in rows:
        stmt = pg_insert(Table).values(**row).on_conflict_do_update(
            constraint="tables_dep_code_muni_code_zona_code_puesto_code_mesa_code_key",
            set_={
                "expected_name": row["expected_name"],
                "id_stand": row["id_stand"],
                "id_transmission": row["id_transmission"],
                "transmission_status": row["transmission_status"],
                "updated_at": datetime.now(timezone.utc),
            },
        )
        result = db.execute(stmt)
        if result.is_insert:
            inserted += 1
    db.commit()
    return inserted


def refresh_universe() -> dict:
    """Main entry point: fetch universe JSON and sync to PostgreSQL.

    Returns: summary dict.
    """
    nodes = fetch_universe_json()
    rows = []

    for node in nodes:
        row = node_to_row(node)
        row["pdf_url"] = pdf_url_for(row)
        rows.append(row)

    db = SessionLocal()
    try:
        inserted = _bulk_upsert_tables(db, rows)

        log = AuditLog(
            event_type="universe_refresh",
            details={
                "total_nodes": len(rows),
                "inserted": inserted,
                "updated": len(rows) - inserted,
            },
        )
        db.add(log)
        db.commit()

        return {
            "total": len(rows),
            "inserted": inserted,
            "updated": len(rows) - inserted,
        }
    finally:
        db.close()
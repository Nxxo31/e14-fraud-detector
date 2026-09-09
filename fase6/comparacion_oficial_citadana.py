#!/usr/bin/env python3
"""
FASE 6: Comparación oficial vs ciudadana
Sistema que cruza los reports ciudadanos con los datos oficiales del
TSE/CNE para detectar discrepancias y anomalías.
"""
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime

DATA_DIR = Path("/home/sebas/proyectos/e14-audit-platform/data/resultados_fraude")
CITIZEN_REPORTS_DIR = DATA_DIR / "citizen_reports"
REPORTES_OFICIALES_DIR = DATA_DIR / "reportes_oficiales"
MATCHES_DIR = DATA_DIR / "matches"
MATCHES_DIR.mkdir(exist_ok=True, parents=True)

@dataclass
class MatchResult:
    citizen_report_id: str
    official_data_id: str
    discrepancies: List[str]
    similarity_score: float
    verdict: str  # "match", "discrepancy", "unmatch"

def load_citizen_reports() -> List[dict]:
    """Carga reports ciudadanos"""
    reports = []
    if not CITIZEN_REPORTS_DIR.exists():
        return reports
    for f in CITIZEN_REPORTS_DIR.glob("*.json"):
        with open(f, 'r', encoding='utf-8') as fh:
            reports.append(json.load(fh))
    return reports

def load_oficial_data() -> List[dict]:
    """Carga datos oficiales"""
    reports = []
    if not REPORTES_OFICIALES_DIR.exists():
        return reports
    for f in REPORTES_OFICIALES_DIR.glob("*.json"):
        with open(f, 'r', encoding='utf-8') as fh:
            reports.append(json.load(fh))
    return reports

def match_reports(citizen: dict, oficial: dict) -> MatchResult:
    """Compara un reporte ciudadano con datos oficiales"""
    discrepancies = []
    score = 1.0
    
    # Comparar campos clave
    if citizen.get('municipality') != oficial.get('municipio'):
        discrepancies.append(f"Municipality mismatch: {citizen.get('municipality')} vs {oficial.get('municipio')}")
        score -= 0.2
    
    if citizen.get('polling_station') != oficial.get('mesa'):
        discrepancies.append(f"Polling station mismatch")
        score -= 0.3
    
    if citizen.get('reported_anomalies') != oficial.get('anomalies_detected'):
        discrepancies.append(f"Anomalies differ")
        score -= 0.1
    
    verdict = "match" if score >= 0.8 else "discrepancy" if score > 0.5 else "unmatch"
    
    return MatchResult(
        citizen_report_id=citizen['id'],
        official_data_id=oficial['id'],
        discrepancies=discrepancies,
        similarity_score=round(score, 2),
        verdict=verdict
    )

def save_match(match: MatchResult) -> str:
    """Guarda resultado de matching"""
    filepath = MATCHES_DIR / f"{match.citizen_report_id}_{match.official_data_id}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(asdict(match), f, indent=2, default=str)
    return filepath.name

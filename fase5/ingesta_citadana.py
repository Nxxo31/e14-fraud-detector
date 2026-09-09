#!/usr/bin/env python3
"""
FASE 5: Ingesta de datos ciudadanos
Sistema para recolectar reportes de fraude ciudadanos mediante formulario web
y validación cruzada con datos oficiales.
"""
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional
import hashlib
from datetime import datetime

DATA_DIR = Path("/home/sebas/proyectos/e14-audit-platform/data/resultados_fraude")
CITIZEN_REPORTS_DIR = DATA_DIR / "citizen_reports"
CITIZEN_REPORTS_DIR.mkdir(exist_ok=True, parents=True)

@dataclass
class CitizenReport:
    id: str
    department: str
    municipality: str
    polling_station: str
    reported_anomalies: str
    evidence_type: str  # photo, document, video
    evidence_path: Optional[str]
    submitted_at: datetime
    verified: bool = False
    matched_oficial: bool = False

def generate_report_id(dept: str, municipality: str, mesa: str) -> str:
    """Genera ID único para reporte ciudadano"""
    timestamp = datetime.now().isoformat()
    base = f"{dept}_{mesa}_{timestamp}"
    return hashlib.sha256(base.encode()).hexdigest()[:12]

def save_citizen_report(report: CitizenReport) -> str:
    """Guarda reporte ciudadano en disco"""
    report.id = generate_report_id(report.department, report.municipality, report.polling_station)
    report.submitted_at = datetime.now()
    filepath = CITIZEN_REPORTS_DIR / f"{report.id}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(asdict(report), f, indent=2, default=str)
    return report.id

def load_citizen_reports() -> List[CitizenReport]:
    """Carga todos los reports ciudadanos"""
    reports = []
    if not CITIZEN_REPORTS_DIR.exists():
        return reports
    for f in CITIZEN_REPORTS_DIR.glob("*.json"):
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            data['submitted_at'] = datetime.fromisoformat(data['submitted_at'])
            reports.append(CitizenReport(**data))
    return reports

#!/usr/bin/env python3
"""
FASE 7: Dashboard público de resultados
Genera dashboard público con estadísticas de detección de fraude
para visualización por la ciudadanía.
"""
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Any
from datetime import datetime

DATA_DIR = Path("/home/sebas/proyectos/e14-audit-platform/data/resultados_fraude")
CITIZEN_REPORTS_DIR = DATA_DIR / "citizen_reports"
MATCHES_DIR = DATA_DIR / "matches"
OUTPUT_DIR = DATA_DIR / "dashboard_publico"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

def generate_dashboard() -> Dict[str, Any]:
    """Genera reporte de dashboard público"""
    stats = {
        "total_reports": 0,
        "by_department": {},
        "by_verdict": Counter(),
        "total_matches": 0,
        "last_updated": datetime.now().isoformat()
    }
    
    # Contar reports ciudadanos
    if CITIZEN_REPORTS_DIR.exists():
        reports = []
        for f in CITIZEN_REPORTS_DIR.glob("*.json"):
            with open(f, 'r', encoding='utf-8') as fh:
                reports.append(json.load(fh))
        stats["total_reports"] = len(reports)
        
        # Por departamento
        dept_counter = Counter()
        for r in reports:
            dept = r.get('department', 'Desconocido')
            dept_counter[dept] += 1
        stats["by_department"] = dict(dept_counter)
    
    # Por veredicto
    if MATCHES_DIR.exists():
        matches = []
        for f in MATCHES_DIR.glob("*.json"):
            with open(f, 'r', encoding='utf-8') as fh:
                matches.append(json.load(fh))
        stats["total_matches"] = len(matches)
        for m in matches:
            verdict = m.get('verdict', 'unknown')
            stats["by_verdict"][verdict] += 1
    
    return stats

def save_dashboard(stats: Dict[str, Any]) -> str:
    """Guarda dashboard JSON"""
    filepath = OUTPUT_DIR / "dashboard.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, default=str)
    return str(filepath)

def main():
    """Entry point"""
    stats = generate_dashboard()
    filepath = save_dashboard(stats)
    print(f"Dashboard generado: {filepath}")
    print(f"Total reports: {stats['total_reports']}")
    print(f"Total matches: {stats['total_matches']}")
    print(f"By verdict: {dict(stats['by_verdict'])}")

if __name__ == "__main__":
    main()

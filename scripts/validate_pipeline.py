#!/usr/bin/env python3
"""
validate_pipeline.py — Valida que el pipeline E14 funcione correctamente.
Ejecuta sobre todas las muestras disponibles y genera reporte de estado.
"""
import sys
import json
from pathlib import Path
from datetime import datetime

# Agregar engine al path
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from pipeline import E14AnalysisPipeline

def main():
    base_dir = Path(__file__).parent.parent
    muestra_dir = base_dir / "data" / "pdf_muestra"
    
    if not muestra_dir.exists():
        print(f"❌ Directorio de muestras no encontrado: {muestra_dir}")
        sys.exit(1)
    
    pdfs = sorted(muestra_dir.glob("*.pdf"))
    if not pdfs:
        print(f"⚠️  No hay PDFs en {muestra_dir}. Usando data/pdf_control/...")
        pdfs = sorted((base_dir / "data" / "pdf_control").glob("*.pdf"))
    
    if not pdfs:
        print("❌ No se encontraron PDFs de muestra ni control")
        sys.exit(1)
    
    print(f"🔍 Validando pipeline con {len(pdfs)} actas...\n")
    print("=" * 60)
    
    success = 0
    failures = []
    
    for pdf_path in pdfs:
        try:
            pipeline = E14AnalysisPipeline(dpi=300)
            result = pipeline.analyze_pdf(pdf_path)
            
            status = "✅" if result.get("veredicto") else "⚠️ "
            score = result.get("score_global", "N/A")
            print(f"{status} {pdf_path.name:<30} → Score: {score:.2f}, Veredicto: {result.get('veredicto', 'N/A')}")
            success += 1
            
        except Exception as e:
            print(f"❌ {pdf_path.name} → ERROR: {str(e)[:60]}")
            failures.append((pdf_path.name, str(e)))
    
    print("=" * 60)
    print(f"\n📊 RESULTADO: {success}/{len(pdfs)} actas procesadas correctamente")
    if failures:
        print(f"❌ Errores: {len(failures)}")
        for name, err in failures:
            print(f"   - {name}: {err[:80]}")
    else:
        print("🎉 TODAS LAS ACTAS PROCESADAS SIN ERRORES")
    
    # Guardar reporte
    report = {
        "fecha": datetime.now().isoformat(),
        "total": len(pdfs),
        "exitosos": success,
        "fallidos": len(failures),
        "errores": failures
    }
    
    report_path = base_dir / "data" / "output" / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📁 Reporte guardado en: {report_path}")
    return 0 if not failures else 1

if __name__ == "__main__":
    sys.exit(main())

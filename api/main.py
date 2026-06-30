"""
API Controller — FastAPI REST para gestión de actas E-14.
"""
import sys
import json
from pathlib import Path
from typing import Optional

# Agregar el proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.database import init_db, upsert_acta, get_all_actas, get_acta, update_veredicto, get_stats

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="E14 Audit Platform API", version="2.0.0", lifespan=lifespan)

# CORS para el dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── ENDPOINTS ──────────────────────────────────────────

@app.get("/")
def root():
    """Health check."""
    return {"status": "ok", "version": "2.0.0", "sistema": "E14 Audit Platform MVC"}


@app.get("/actas")
def list_actas(
    veredicto: Optional[str] = Query(None, description="Filtrar por veredicto"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Lista todas las actas con filtro opcional por veredicto."""
    actas = get_all_actas()

    if veredicto:
        actas = [a for a in actas if a["veredicto"] == veredicto]

    total = len(actas)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": actas[offset:offset + limit]
    }


@app.get("/actas/{acta_id}")
def detalle_acta(acta_id: int):
    """Obtiene detalle completo de un acta incluyendo celdas y scores."""
    acta = get_acta(acta_id)
    if not acta:
        raise HTTPException(status_code=404, detail="Acta no encontrada")

    # Parsear el resultado JSON si existe
    if acta.get("resultado_json"):
        try:
            acta["resultado"] = json.loads(acta["resultado_json"])
        except (json.JSONDecodeError, TypeError):
            acta["resultado"] = None

    return acta


@app.put("/actas/{acta_id}/veredicto")
def set_veredicto(acta_id: int, veredicto: str = Query(...), revisor: str = Query("")):
    """Actualiza el veredicto de un acta (revisión humana)."""
    valid = ["LEGITIMA", "SOSPECHOSA", "ILEGITIMA", "PENDIENTE"]
    if veredicto not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Veredicto inválido. Debe ser uno de: {valid}"
        )

    acta = get_acta(acta_id)
    if not acta:
        raise HTTPException(status_code=404, detail="Acta no encontrada")

    update_veredicto(acta_id, veredicto, revisor)
    return {"id": acta_id, "veredicto": veredicto, "actualizado": True}


@app.post("/actas/analizar")
async def analizar_pdf(file: UploadFile = File(...)):
    """Sube y analiza un PDF E-14."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF")

    # Guardar archivo subido
    pdf_path = UPLOAD_DIR / file.filename
    content = await file.read()
    pdf_path.write_bytes(content)

    # Analizar
    try:
        from engine.pipeline import E14AnalysisPipeline

        pipeline = E14AnalysisPipeline(dpi=300)
        resultado = pipeline.analyze_pdf(pdf_path)

        # Guardar en base de datos
        acta_data = {
            "mesa_key": resultado["mesa_key"],
            "filename": file.filename,
            "resultado": resultado
        }
        acta_id = upsert_acta(acta_data)

        return {
            "id": acta_id,
            "mesa_key": resultado["mesa_key"],
            "veredicto": resultado["veredicto"],
            "score_global": resultado["score_global"],
            "total_celdas": resultado["total_celdas"],
            "celdas_sospechosas": resultado["visual_summary"]["celdas_sospechosas"],
            "resultado": resultado
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar PDF: {str(e)}")


@app.get("/celdas/{acta_id}")
def get_celdas(acta_id: int):
    """Obtiene las imágenes de celdas de un acta para el visor."""
    acta = get_acta(acta_id)
    if not acta:
        raise HTTPException(status_code=404, detail="Acta no encontrada")

    if acta.get("resultado_json"):
        try:
            resultado = json.loads(acta["resultado_json"])
            cells = resultado.get("cells", [])
            return {"acta_id": acta_id, "total": len(cells), "cells": cells}
        except (json.JSONDecodeError, TypeError):
            pass

    return {"acta_id": acta_id, "total": 0, "cells": []}


@app.get("/dashboard/stats")
def dashboard_stats():
    """Estadísticas para el dashboard."""
    return get_stats()


@app.get("/dashboard")
def dashboard():
    """Sirve el dashboard HTML."""
    html_path = Path(__file__).parent.parent / "dashboard" / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    raise HTTPException(status_code=404, detail="Dashboard no encontrado")


@app.post("/actas/{acta_id}/analizar-vlm")
def analizar_vlm(acta_id: int):
    """Analiza las celdas más sospechosas de un acta con VLM (NVIDIA NIM)."""
    from engine.analyze.vlm_nim import analyze_acta_vlm

    acta = get_acta(acta_id)
    if not acta:
        raise HTTPException(status_code=404, detail="Acta no encontrada")

    if not acta.get("resultado_json"):
        raise HTTPException(status_code=400, detail="Acta sin resultado de análisis previo")

    try:
        resultado = json.loads(acta["resultado_json"])
        cells = resultado.get("cells", [])

        if not cells:
            return {"acta_id": acta_id, "celdas_analizadas": 0, "mensaje": "Sin celdas para analizar"}

        context = f"Acta {acta.get('mesa_key', '')} — {acta.get('filename', '')}"
        vlm_result = analyze_acta_vlm(cells, context, max_cells=5)

        # Guardar resultado VLM en la base de datos
        resultado["vlm_analysis"] = vlm_result
        conn = __import__("api.database", fromlist=["get_db"]).get_db()
        conn.execute(
            "UPDATE actas SET resultado_json = ? WHERE id = ?",
            (json.dumps(resultado, ensure_ascii=False), acta_id)
        )
        conn.commit()
        conn.close()

        return {
            "acta_id": acta_id,
            "celdas_analizadas": vlm_result["celdas_analizadas"],
            "errores": vlm_result["errores"],
            "resultados": vlm_result["resultados"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en VLM: {str(e)}")


@app.post("/actas/analizar-lote")
async def analizar_lote():
    """Analiza todos los PDFs en data/pdf_control/ que no hayan sido procesados."""
    import asyncio
    from engine.pipeline import E14AnalysisPipeline

    pdf_dir = Path(__file__).parent.parent / "data" / "pdf_control"
    if not pdf_dir.exists():
        return {"mensaje": "Directorio pdf_control no encontrado", "procesados": 0}

    pdfs = list(pdf_dir.glob("*.pdf"))
    if not pdfs:
        return {"mensaje": "No hay PDFs en pdf_control", "procesados": 0}

    # Filtrar ya procesados
    actas_existentes = {a["filename"] for a in get_all_actas()}
    pendientes = [p for p in pdfs if p.name not in actas_existentes]

    pipeline = E14AnalysisPipeline(dpi=300)
    resultados = []
    errores = 0

    for pdf_path in pendientes[:10]:  # Máximo 10 por lote
        try:
            resultado = pipeline.analyze_pdf(pdf_path)
            upsert_acta({
                "mesa_key": resultado["mesa_key"],
                "filename": pdf_path.name,
                "resultado": resultado
            })
            resultados.append({
                "filename": pdf_path.name,
                "veredicto": resultado["veredicto"],
                "score": resultado["score_global"]
            })
        except Exception as e:
            errores += 1

    return {
        "total_pendientes": len(pendientes),
        "procesados": len(resultados),
        "errores": errores,
        "resultados": resultados
    }


@app.get("/exportar/actas")
def exportar_actas(formato: str = Query("json", description="Formato: json o csv")):
    """Exporta todas las actas en formato JSON o CSV."""
    import csv
    import io

    actas = get_all_actas()

    if formato == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "mesa_key", "filename", "score_global", "veredicto", "fecha_analisis"])
        for a in actas:
            writer.writerow([
                a["id"], a["mesa_key"], a["filename"],
                a["score_global"], a["veredicto"],
                (a.get("fecha_analisis") or "")[:19]
            ])
        return JSONResponse(content={"csv": output.getvalue()})
    else:
        return {"total": len(actas), "data": actas}


# ── MAIN ───────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("E14 AUDIT PLATFORM — MVC API v2.0")
    print("=" * 60)
    print("Endpoints:")
    print("  GET  /                  — Health check")
    print("  GET  /actas             — Listar actas")
    print("  POST /actas/analizar    — Subir y analizar PDF")
    print("  GET  /actas/{id}        — Detalle de acta")
    print("  PUT  /actas/{id}/veredicto — Actualizar veredicto")
    print("  GET  /celdas/{id}       — Celdas del acta")
    print("  GET  /dashboard/stats   — Estadísticas")
    print("  GET  /dashboard         — Dashboard HTML")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8700)
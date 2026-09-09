#!/usr/bin/env python3
"""
TAREA CORREGIDA — Anclaje de columna de votación con restricciones explícitas.

Estrategia:
1. Buscar encabezados CANDIDATO, AGRUPACIÓN, VOTACIÓN en la misma franja Y (fila de encabezado)
2. Usar la X de VOTACIÓN como columna fija para toda la tabla
3. Para cada candidato: celda = (X_votacion, Y_candidato, ancho_votacion, alto_nombre)
4. Buscar solo dentro del bounding box de la fila del candidato si falla lo anterior

Ejecutar: python3 fase4/ocr_anchor_fixed.py
"""

import easyocr
import fitz
import numpy as np
from pathlib import Path
import cv2

PDF_DIR = Path(__file__).parent.parent / "data" / "pdf_muestra"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "celdas_ocr_v2"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

print("🔤 Inicializando EasyOCR...")
reader = easyocr.Reader(['es'], gpu=False)
print("   ✅ Listo\n")


def render_page(doc: fitz.Document, page_num: int = 0, dpi: int = 300) -> np.ndarray:
    page = doc[page_num]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    return cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)


def ocr_page(page_img: np.ndarray) -> list:
    results = reader.readtext(page_img, paragraph=False)
    detections = []
    for bbox, text, conf in results:
        if conf > 0.3:
            x, y = int(bbox[0][0]), int(bbox[0][1])
            w = int(bbox[2][0] - bbox[0][0])
            h = int(bbox[2][1] - bbox[0][1])
            detections.append({'text': text.strip(), 'x': x, 'y': y, 'w': w, 'h': h, 'conf': round(conf, 2)})
    return detections


def find_in_y_stripe(detections, keyword, y_target, tolerance=60):
    """Buscar keyword SOLO en la franja Y [y_target - tol, y_target + tol]."""
    for d in detections:
        if keyword.upper() in d['text'].upper():
            if abs(d['y'] - y_target) <= tolerance:
                return d
    return None


def find_any(detections, keyword):
    for d in detections:
        if keyword.upper() in d['text'].upper():
            return d
    return None


# ── Procesar cada PDF ───────────────────────────────────────────────────────
for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
    pdf_name = pdf_path.stem
    doc = fitz.open(str(pdf_path))

    print(f"\n{'='*70}")
    print(f"📄 {pdf_path.name}")
    print(f"{'='*70}")

    page_img = render_page(doc, 0)  # Página 1
    h_img, w_img = page_img.shape[:2]
    detections = ocr_page(page_img)

    # ── Paso 1: Encontrar encabezados de tabla ──────────────────────────────
    cand_header = find_any(detections, "CANDIDATO")
    agrup_header = find_any(detections, "AGRUPACIÓN")

    if not cand_header or not agrup_header:
        print("   ❌ No se encontraron encabezados CANDIDATO/AGRUPACIÓN")
        doc.close()
        continue

    # La fila del encabezado es la Y promedio de CANDIDATO y AGRUPACIÓN
    header_y = int((cand_header['y'] + agrup_header['y']) / 2)

    print(f"\n   Encabezados detectados:")
    print(f"   CANDIDATO:  ({cand_header['x']}, {cand_header['y']}) {cand_header['w']}x{cand_header['h']}")
    print(f"   AGRUPACIÓN: ({agrup_header['x']}, {agrup_header['y']}) {agrup_header['w']}x{agrup_header['h']}")
    print(f"   Fila header Y ~{header_y}")

    # ── Paso 2: Buscar "VOTACIÓN" en la franja del encabezado ───────────────
    votacion_header = find_in_y_stripe(detections, "VOTACIÓN", header_y, tolerance=80)

    if not votacion_header:
        # Fallback: buscar "VOTOS" en la franja del encabezado
        votacion_header = find_in_y_stripe(detections, "VOTOS", header_y, tolerance=80)

    if not votacion_header:
        # Segundo fallback: "VOTACIÓN" en la mitad derecha del documento
        for d in detections:
            if "VOTACIÓN" in d['text'].upper() and d['x'] > w_img * 0.4:
                if abs(d['y'] - header_y) <= 100:
                    votacion_header = d
                    break

    if votacion_header:
        col_x = votacion_header['x']
        col_w = votacion_header['w']
        print(f"   VOTACIÓN:   ({votacion_header['x']}, {votacion_header['y']}) {votacion_header['w']}x{votacion_header['h']}")
        print(f"   Columna X = {col_x}, ancho = {col_w}")
    else:
        print(f"   ❌ No se pudo encontrar columna VOTACIÓN en la fila del encabezado")
        doc.close()
        continue

    # ── Paso 3: Encontrar candidatos ────────────────────────────────────────
    candidate_names = ["GUSTAVO", "IVÁN", "ABELARDO"]
    candidates_found = []

    for name in candidate_names:
        cand = find_any(detections, name)
        if cand:
            candidates_found.append((name, cand))

    if not candidates_found:
        print(f"   ❌ No se encontraron nombres de candidatos")
        doc.close()
        continue

    # ── Paso 4: Tabla de verificación numérica ──────────────────────────────
    print(f"\n   {'='*60}")
    print(f"   TABLA DE VERIFICACIÓN DE COORDENADAS")
    print(f"   {'='*60}")
    print(f"   {'Ancla':<25} {'X':>6} {'Y':>6} {'Ancho':>6} {'Alto':>6}")
    print(f"   {'-'*50}")

    for name, cand in candidates_found:
        # Celda = columna votación X, fila candidato Y
        cell_x = col_x
        cell_y = cand['y']
        cell_w = col_w
        cell_h = cand['h']  # Mismo alto que el nombre del candidato

        # Ajustar: la celda real es más angosta que el ancho de la columna
        # Usamos un ancho estimado de ~200px para la celda de dígitos
        cell_w_adj = min(cell_w, 220)  # Máximo 220px de ancho para celda

        print(f"   {name:<25} {cell_x:>6} {cell_y:>6} {cell_w_adj:>6} {cell_h:>6}")

    # ── Paso 5: Generar recortes ────────────────────────────────────────────
    print(f"\n   Generando recortes...")
    for name, cand in candidates_found:
        cell_x = col_x
        cell_y = cand['y']
        cell_w = min(col_w, 220)
        cell_h = cand['h']

        # Verificar límites
        x0 = max(0, cell_x)
        y0 = max(0, cell_y - 5)
        x1 = min(w_img, cell_x + cell_w)
        y1 = min(h_img, cell_y + cell_h + 5)

        crop = page_img[y0:y1, x0:x1]

        out_name = f"{pdf_name}_{name.lower()}_celda.png"
        out_path = OUTPUT_DIR / out_name
        cv2.imwrite(str(out_path), crop)
        print(f"   ✅ {out_name} → {crop.shape}")

    doc.close()

print(f"\n{'='*70}")
print(f"✅ Recortes guardados en: {OUTPUT_DIR}")
print(f"   Total: {len(list(OUTPUT_DIR.glob('*.png')))} archivos")
print(f"{'='*70}")
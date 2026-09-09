#!/usr/bin/env python3
"""
TAREA 1-3 — OCR de anclaje para celdas E-14 + recortes validados.

Usa EasyOCR (PyTorch-based, no necesita Tesseract) para detectar
las anclas de texto fijo (candidatos, encabezados, secciones)
y derivar las coordenadas de las celdas de votación por posición relativa.

Ejecutar con: python3 fase4/ocr_anchor.py
"""

import easyocr
import fitz
import numpy as np
from pathlib import Path
import cv2

# ── Configuración ───────────────────────────────────────────────────────────
PDF_DIR = Path(__file__).parent.parent / "data" / "pdf_muestra"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "celdas_ocr"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# Inicializar EasyOCR con español
print("🔤 Inicializando EasyOCR (español, CPU)...")
reader = easyocr.Reader(['es'], gpu=False)
print("   ✅ Listo\n")

# ── Anclas de texto a buscar ────────────────────────────────────────────────
ANCHOR_KEYWORDS = [
    "CANDIDATO",
    "AGRUPACIÓN",
    "VOTACIÓN",
    "GUSTAVO",
    "IVÁN",
    "ABELARDO",
    "BLANCO",
    "NULOS",
    "NO MARCADOS",
    "SUMA TOTAL",
    "TOTAL VOTANTES",
    "FORMULARIO E-11",
    "TOTAL VOTOS EN LA URNA",
    "NIVELACIÓN",
]

def ocr_page(page_image: np.ndarray) -> list:
    """Run EasyOCR on a page image and return detections with coordinates."""
    results = reader.readtext(page_image, paragraph=False)
    detections = []
    for bbox, text, conf in results:
        if conf > 0.3:  # Solo confianza > 30%
            # bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            x = int(bbox[0][0])
            y = int(bbox[0][1])
            w = int(bbox[2][0] - bbox[0][0])
            h = int(bbox[2][1] - bbox[0][1])
            detections.append({
                'text': text.strip(),
                'x': x, 'y': y, 'w': w, 'h': h,
                'conf': round(conf, 2)
            })
    return detections


def find_anchor(detections: list, keyword: str) -> dict | None:
    """Find the first detection containing keyword in its text."""
    keyword_upper = keyword.upper()
    for d in detections:
        if keyword_upper in d['text'].upper():
            return d
    return None


def render_page(doc: fitz.Document, page_num: int = 0, dpi: int = 300) -> np.ndarray:
    """Render a PDF page to numpy array at specified DPI."""
    page = doc[page_num]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    return cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)


def crop_cell(page_img: np.ndarray, x: int, y: int, w: int, h: int,
              pad: int = 2) -> np.ndarray:
    """Crop a cell region with optional padding."""
    h_img, w_img = page_img.shape[:2]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(w_img, x + w + pad)
    y1 = min(h_img, y + h + pad)
    return page_img[y0:y1, x0:x1]


# ── Procesar cada PDF ───────────────────────────────────────────────────────
for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
    pdf_name = pdf_path.stem
    doc = fitz.open(str(pdf_path))
    
    print(f"{'='*60}")
    print(f"📄 {pdf_path.name}")
    print(f"{'='*60}")
    
    # Página 1 (índice 0)
    for pn in range(min(2, len(doc))):  # Solo páginas 1 y 2
        print(f"\n📖 Página {pn+1}")
        page_img = render_page(doc, pn)
        print(f"   Renderizado: {page_img.shape}")
        
        detections = ocr_page(page_img)
        print(f"   Detecciones OCR: {len(detections)}")
        
        # Buscar anclas
        found = []
        for keyword in ANCHOR_KEYWORDS:
            anchor = find_anchor(detections, keyword)
            if anchor:
                found.append((keyword, anchor))
                print(f"   ✅ [{keyword}] \"{anchor['text']}\" @ ({anchor['x']},{anchor['y']}) conf={anchor['conf']}")
        
        if not found:
            print(f"   ⚠️  No se encontraron anclas en esta página")
    
    doc.close()
    print()

print("✅ Análisis OCR completado")

# ── Derivar celdas por proximidad ─────────────────────────────────────────
print(f"\n{'='*60}")
print("📊 Derivando coordenadas de celdas por anclaje...")
print(f"{'='*60}")

for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
    pdf_name = pdf_path.stem
    doc = fitz.open(str(pdf_path))
    page_img = render_page(doc, 0)  # Página 1 para candidatos
    
    detections = ocr_page(page_img)
    
    # Buscar fila de cada candidato
    for candidate_name in ["GUSTAVO", "IVÁN", "ABELARDO"]:
        anchor = find_anchor(detections, candidate_name)
        if anchor:
            print(f"\n📄 {pdf_name} — {candidate_name}:")
            print(f"   Ancla: ({anchor['x']},{anchor['y']}) \"{anchor['text']}\"")
            
            # La celda de votación está a la derecha del nombre, 
            # en la columna "VOTACIÓN"
            voting_col = find_anchor(detections, "VOTACIÓN")
            if voting_col:
                # Celda = misma fila Y que el candidato, columna X = columna de votación
                cell_x = voting_col['x']
                cell_y = anchor['y']
                cell_w = voting_col['w']
                cell_h = anchor['h']
                
                print(f"   Celda derivada: ({cell_x},{cell_y}) {cell_w}x{cell_h}")
                
                # Recortar y guardar
                crop = crop_cell(page_img, cell_x, cell_y, cell_w, cell_h)
                out_name = f"{pdf_name}_{candidate_name.lower()}_col1.png"
                out_path = OUTPUT_DIR / out_name
                cv2.imwrite(str(out_path), crop)
                print(f"   ✅ Guardado: {out_name} ({crop.shape})")
            else:
                print(f"   ⚠️  No se encontró columna 'VOTACIÓN'")
    
    doc.close()

print(f"\n✅ Recortes OCR guardados en {OUTPUT_DIR}")
print(f"   Revisar visualmente antes de continuar con scoring")
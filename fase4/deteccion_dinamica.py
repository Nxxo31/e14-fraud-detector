#!/usr/bin/env python3
"""
ESTRATEGIA: Detección dinámica de tinta manuscrita por columna de votación.
Problema original: las celdas se colocaban en Y de los NOMBRES de candidatos,
pero los números manuscritos están en FILAS DIFERENTES de la tabla.

Solución:
1. Renderizar PDF a alta resolución
2. Para cada candidato, buscar la FILA de la tabla donde están sus VOTOS
   - Buscar región con tinta/dígitos cerca de la columna VOTACIÓN
   - No usar la Y del nombre del candidato
3. Recortar la zona con tinta y aplicar análisis de doble trazo
"""

import easyocr
import fitz
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
import re

PDF_DIR = Path("data/pdf_muestra")
OUTPUT_DIR = Path("data/celdas_dinamicas")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
DEBUG_DIR = Path("data/debug_tinta")
DEBUG_DIR.mkdir(exist_ok=True, parents=True)

# Candidato que nos interesa (el que puede tener alterations = ABELARDO)
CANDIDATO_ALVO = "ABELARDO"

# Candidatos conocidos
CANDIDATE_KEYWORDS = {
    "GUSTAVO": ["GUSTAVO", "GUSTAVO PETRO"],
    "IVÁN": ["IVÁN", "IVAN", "IVÁN DUQUE", "IVAN DUQUE"],
    "ABELARDO": ["ABELARDO", "ABELARDO ARA", "ABELARDO ARANA"],
}

# Rango de búsqueda vertical (en px a 300dpi) desde la fila de encabezado
# Los votos están típicamente 300-2500px debajo de la fila de encabezado
ROW_HEIGHT_ESTIMATE = 1000  # distancia aproximada entre filas de candidatos

print("🔤 Inicializando EasyOCR...")
reader = easyocr.Reader(['es'], gpu=False)
print("   ✅ Listo\n")


def render_page(doc: fitz.Document, page_num: int = 0, dpi: int = 300) -> np.ndarray:
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)


def ocr_page(page_img: np.ndarray) -> list:
    results = reader.readtext(page_img, paragraph=False)
    detections = []
    for bbox, text, conf in results:
        if conf > 0.25:
            x, y = int(bbox[0][0]), int(bbox[0][1])
            w = int(bbox[2][0] - bbox[0][0])
            h = int(bbox[2][1] - bbox[0][1])
            detections.append({
                'text': text.strip(), 'x': x, 'y': y,
                'w': w, 'h': h, 'conf': round(conf, 2)
            })
    return detections


def get_column_votacion(detections, w_img):
    """Encontrar la columna X de VOTACIÓN (encabezado de la columna de votos)."""
    for d in detections:
        if d['text'].upper() in ("VOTACIÓN", "VOTOS", "VOTACIÓN."):
            if d['x'] > w_img * 0.35:  # columna derecha
                return d
    return None


def find_candidate_row(detections, candidate_keywords):
    """Encontrar la fila Y de un candidato por su nombre."""
    for d in detections:
        text_upper = d['text'].upper()
        for kw in candidate_keywords:
            if kw.upper() in text_upper:
                return d
    return None


def detect_digit_regions_in_column(page_img, col_x, col_w, y_start, y_end,
                                     col_y_header, row_height, reader):
    """
    Buscar regiones con DÍGITOS manuscritos en la columna de votación.
    Retorna lista de dicts con {y, x, w, h, text, conf}
    """
    h_img, w_img = page_img.shape[:2]

    # Definir zona de búsqueda: columna VOTACIÓN completa desde encabezado
    search_x0 = max(0, col_x - 30)
    search_x1 = min(w_img, col_x + col_w + 50)
    search_y0 = max(0, col_y_header)
    search_y1 = min(h_img, y_end)

    # Recortar la columna completa
    col_crop = page_img[search_y0:search_y1, search_x0:search_x1]

    # Detectar texto manuscrito (dígitos)
    dets = reader.readtext(col_crop, paragraph=False)

    regions = []
    offset_y = search_y0
    offset_x = search_x0

    for bbox, text, conf in dets:
        if conf < 0.3:
            continue
        # Solo nos interesan detecciones con dígitos (escritura manuscrita)
        if not any(c.isdigit() for c in text):
            continue

        abs_x = int(bbox[0][0]) + offset_x
        abs_y = int(bbox[0][1]) + offset_y
        abs_w = int(bbox[2][0] - bbox[0][0])
        abs_h = int(bbox[2][1] - bbox[0][1])

        regions.append({
            'text': text,
            'x': abs_x, 'y': abs_y,
            'w': abs_w, 'h': abs_h,
            'conf': conf
        })

    return regions


def find_voto_for_candidate(regions, cand_name_y, row_height=1000, tolerance=300):
    """
    De todas las regiones de dígitos detectadas, encontrar la más cercana
    a la fila del candidato pero DENTRO de su fila de la tabla.

    La clave: los votos NO están en la Y del nombre, sino en la MISMA FILA
    de la tabla, que está desplazada.
    """
    if not regions:
        return None

    # Ordenar por Y
    regions_sorted = sorted(regions, key=lambda r: r['y'])

    # Buscar la región de dígitos más cercana a cand_name_y
    # pero que esté razonablemente cerca (dentro de una fila)
    best = None
    best_dist = float('inf')

    for r in regions_sorted:
        dist = abs(r['y'] - cand_name_y)
        if dist < best_dist and dist < row_height:
            best_dist = dist
            best = r

    return best


def find_all_voto_rows(regions, y_start, row_height=900, tolerance=200):
    """
    Encontrar TODAS las filas de voto manuscrito en la columna,
    agrupando por cercanía vertical.
    """
    if not regions:
        return []

    # Ordenar por Y
    sorted_regions = sorted(regions, key=lambda r: r['y'])

    # Agrupar en filas (misma Y ~ dentro de tolerance)
    rows = []
    current_row = []

    for r in sorted_regions:
        if not current_row:
            current_row = [r]
        else:
            # ¿Está en la misma fila?
            if abs(r['y'] - current_row[0]['y']) <= tolerance:
                current_row.append(r)
            else:
                # Nueva fila
                rows.append(current_row)
                current_row = [r]

    if current_row:
        rows.append(current_row)

    # Para cada fila, quedarse con la detección más confiada
    best_per_row = []
    for row in rows:
        best = max(row, key=lambda r: r['conf'])
        best_per_row.append({
            'y': best['y'],
            'x': best['x'],
            'w': best['w'],
            'h': best['h'],
            'text': best['text'],
            'conf': best['conf'],
            'all_texts': [r['text'] for r in row]
        })

    return best_per_row


def detect_double_stroke(crop_img):
    """
    Análisis de doble trazo: buscar evidencia de alteración manuscrita.

    Un número manuscrito alterado presenta:
    1. Alta variabilidad en ancho de trazo (el trazo sobrepuesto es más grueso)
    2. Densidad de tinta elevada con distribución irregular
    3. Múltiples contornos que se solapan de forma no natural

    Retorna dict con:
    - has_double_stroke: bool
    - confidence: float 0-1
    - details: str
    """
    if crop_img is None or crop_img.size == 0:
        return {'has_double_stroke': False, 'confidence': 0.0, 'details': 'imagen vacía'}

    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Binarizar con Otsu (fondo claro, tinta oscura)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    ink_pixels = cv2.countNonZero(binary)
    ink_ratio = ink_pixels / (h * w)

    if ink_ratio < 0.02:
        return {'has_double_stroke': False, 'confidence': 0.0,
                'details': f'muy poca tinta ({ink_ratio:.3f})'}

    # Encontrar contornos de los trazos
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Filtrar ruido
    sig_cnts = [c for c in contours if cv2.contourArea(c) > 30]

    if not sig_cnts:
        return {'has_double_stroke': False, 'confidence': 0.0,
                'details': 'sin contornos significativos'}

    # Métrica 1: DISTRIBUCIÓN DE ANCHO DE TRAZO
    # Doble trazo → alta varianza en anchos de stroke
    stroke_widths = []
    for c in sig_cnts:
        x, y_c, cw, ch = cv2.boundingRect(c)
        if ch > 3:
            stroke_widths.append(cw)

    width_std = np.std(stroke_widths) if len(stroke_widths) > 1 else 0.0
    width_max = max(stroke_widths) if stroke_widths else 0
    width_mean = np.mean(stroke_widths) if stroke_widths else 0
    width_cv = width_std / width_mean if width_mean > 0 else 0  # coef de variación

    # Métrica 2: ÍNDICE DE SOLAPAMIENTO
    # Contar cuántos pixeles sobreviven a erosión moderada
    # Doble trazo → tinta compacta que resiste erosión fuerte
    kernel_small = np.ones((2, 2), np.uint8)
    kernel_large = np.ones((4, 4), np.uint8)
    eroded_s = cv2.erode(binary, kernel_small, iterations=1)
    eroded_l = cv2.erode(binary, kernel_large, iterations=2)
    eroded_s_ink = cv2.countNonZero(eroded_s)
    eroded_l_ink = cv2.countNonZero(eroded_l)

    # Ratio de erosión fuerte: doble trazo tiene ratio más alto
    erosion_ratio = eroded_l_ink / ink_pixels if ink_pixels > 0 else 0

    # Métrica 3: DENSIDAD LOCAL (varianza espacial)
    # Dividir imagen en grid y calcular varianza de densidad por celda
    grid_h, grid_w = 3, 3
    cell_h, cell_w = h // grid_h, w // grid_w
    density_per_cell = []
    for gi in range(grid_h):
        for gj in range(grid_w):
            cy0, cy1 = gi * cell_h, (gi + 1) * cell_h
            cx0, cx1 = gj * cell_w, (gj + 1) * cell_w
            cell = binary[cy0:cy1, cx0:cx1]
            density_per_cell.append(cv2.countNonZero(cell) / (cell_h * cell_w))

    density_variance = np.var(density_per_cell)

    # Métrica 4: CONTORNOS SOLAPADOS (buscar overlap horizontal)
    # Buscar si hay contornos que se superponen horizontalmente
    # (signo de un dígito escrito sobre otro)
    overlap_count = 0
    sorted_by_x = sorted(sig_cnts, key=lambda c: cv2.boundingRect(c)[0])
    for i in range(len(sorted_by_x) - 1):
        x1, _, w1, _ = cv2.boundingRect(sorted_by_x[i])
        x2, _, w2, _ = cv2.boundingRect(sorted_by_x[i + 1])
        # Si se solapan en más del 30% de la longitud
        overlap = min(x1 + w1, x2 + w2) - max(x1, x2)
        if overlap > 0:
            min_w = min(w1, w2)
            if overlap > min_w * 0.3:
                overlap_count += 1

    # SCORING
    score = 0.0
    reasons = []

    # 1. Ancho de stroke muy variable (alto CV indica trazo sobrepuesto)
    if width_cv > 0.8:
        score += 0.35
        reasons.append(f'width_cv={width_cv:.2f}')
    elif width_cv > 0.4:
        score += 0.15
        reasons.append(f'width_cv={width_cv:.2f}(bajo)')

    # 2. Trazo muy ancho respecto al promedio (doble trazo visible)
    if width_mean > 25 and width_max > width_mean * 2.5:
        score += 0.35
        reasons.append(f'width_max/mean={width_max/width_mean if width_mean>0 else 0:.1f}x')
    elif width_max > 30:
        score += 0.10
        reasons.append(f'width_max={width_max}px(alto)')

    # 3. Alta resistencia a erosión (tinta compacta = trazo doble)
    if erosion_ratio > 0.75:
        score += 0.25
        reasons.append(f'erosion={erosion_ratio:.2f}')
    elif erosion_ratio > 0.55:
        score += 0.10

    # 4. Varianza de densidad espacial (manchas irregulares)
    if density_variance > 0.03:
        score += 0.15
        reasons.append(f'dens_var={density_variance:.3f}')

    # 5. Contornos solapados (dígito sobre dígito)
    if overlap_count >= 1:
        score += 0.30
        reasons.append(f'overlap={overlap_count}')

    confidence = min(score, 1.0)
    has_double_stroke = score >= 0.5

    details = (f"tinta={ink_ratio:.3f}, widths=[{','.join(str(int(w)) for w in sorted(stroke_widths))}], "
               f"w_mean={width_mean:.1f}, w_std={width_std:.1f}, w_cv={width_cv:.2f}, "
               f"erosion={erosion_ratio:.2f}, dens_var={density_variance:.3f}, "
               f"overlap={overlap_count}, score={score:.2f}, reasons=[{','.join(reasons)}]")

    return {
        'has_double_stroke': has_double_stroke,
        'confidence': confidence,
        'details': details
    }


def crop_voto_region(page_img, region, margin=20):
    """Recortar la región exacta del voto con margen."""
    h_img, w_img = page_img.shape[:2]

    x0 = max(0, region['x'] - margin)
    y0 = max(0, region['y'] - margin)
    x1 = min(w_img, region['x'] + region['w'] + margin)
    y1 = min(h_img, region['y'] + region['h'] + margin)

    crop = page_img[y0:y1, x0:x1]
    return crop


def debug_save(page_img, regions, all_voto_rows, col_x, col_w,
               col_y_header, pdf_name, candidato=None):
    """Guardar imagen de debug con las regiones marcadas."""
    h, w = page_img.shape[:2]
    debug_img = page_img.copy()

    # Dibujar la columna VOTACIÓN
    cv2.rectangle(debug_img,
                  (col_x - 10, col_y_header),
                  (col_x + col_w + 10, h),
                  (0, 255, 0), 2)

    # Marcar todas las regiones de dígitos detectadas
    for r in regions:
        cv2.rectangle(debug_img,
                      (r['x'], r['y']),
                      (r['x'] + r['w'], r['y'] + r['h']),
                      (255, 0, 0), 2)
        cv2.putText(debug_img, r['text'][:5],
                    (r['x'], r['y'] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 0, 0), 2)

    # Marcar filas de voto identificadas
    for i, row in enumerate(all_voto_rows):
        cv2.circle(debug_img, (row['x'], row['y']), 8,
                   (0, 0, 255), -1)
        cv2.putText(debug_img, f"F{i+1}:{row['text'][:6]}",
                    (row['x'] + 15, row['y'] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2)

    out_path = DEBUG_DIR / f"{pdf_name}_debug.png"
    cv2.imwrite(str(out_path), debug_img)
    print(f"   🔍 Debug: {out_path}")


# ═══════════════════════════════════════════════════════════════════════════
# PROCESO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════
for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
    pdf_name = pdf_path.stem
    print(f"\n{'='*70}")
    print(f"📄 {pdf_path.name}")
    print(f"{'='*70}")

    doc = fitz.open(str(pdf_path))
    page_img = render_page(doc, 0)
    h_img, w_img = page_img.shape[:2]
    detections = ocr_page(page_img)

    print(f"   Imagen: {w_img}x{h_img} px")

    # ── Encontrar encabezado VOTACIÓN ────────────────────────────────────
    header_dets = [d for d in detections if d['text'].upper() in ("VOTACIÓN", "VOTOS")]
    if not header_dets:
        print("   ❌ No se encontró encabezado VOTACIÓN")
        doc.close()
        continue

    votacion_hdr = header_dets[0]
    col_x = votacion_hdr['x']
    col_w = votacion_hdr['w']
    col_y_header = votacion_hdr['y']

    print(f"   Columna VOTACIÓN: X={col_x}, Y_header={col_y_header}, W={col_w}")

    # ── Encontrar fila de cada candidato (por su nombre en la tabla) ────────
    candidate_positions = {}
    for cand_name, keywords in CANDIDATE_KEYWORDS.items():
        cand_det = find_candidate_row(detections, keywords)
        if cand_det:
            candidate_positions[cand_name] = cand_det
            print(f"   {cand_name}: Y_nombre={cand_det['y']}")

    if not candidate_positions:
        print("   ❌ No se encontraron candidatos")
        doc.close()
        continue

    # ── Detectar TODAS las regiones con dígitos en la columna ──────────────
    # Buscar desde el encabezado hasta el final de la página
    y_search_end = int(col_y_header + (len(candidate_positions) + 2) * 1100)

    digit_regions = detect_digit_regions_in_column(
        page_img, col_x, col_w,
        col_y_header, y_search_end,
        col_y_header,
        row_height=1000,
        reader=reader
    )

    print(f"\n   Dígitos detectados en columna: {len(digit_regions)}")
    for r in digit_regions:
        print(f"   → '{r['text']}' @ Y={r['y']}, conf={r['conf']:.2f}")

    if not digit_regions:
        print("   ⚠️  SIN DÍGITOS en columna de votación")

    # ── Encontrar TODAS las filas de voto (agrupadas por Y) ───────────────
    all_voto_rows = find_all_voto_rows(digit_regions, col_y_header, row_height=900)
    print(f"\n   Filas de voto identificadas: {len(all_voto_rows)}")
    for i, row in enumerate(all_voto_rows):
        print(f"   Fila {i+1}: '{row['text']}' @ Y={row['y']}, conf={row['conf']:.2f}")

    # ── Hacer match candidato → fila de voto ──────────────────────────────
    # El problema es que la Y del nombre NO coincide con la Y del voto.
    # Necesitamos: para cada candidato, encontrar la fila de voto más cercana
    # debajo de su nombre (pero dentro de su fila de la tabla ~900px)

    print(f"\n   ── Matching candidato → fila de voto ──")
    candidato_voto = {}  # cand_name -> row_info

    for cand_name, cand_det in candidate_positions.items():
        cand_y = cand_det['y']

        # Buscar la fila de voto más cercana DESPUÉS de cand_y (votos bajo el nombre)
        # pero dentro de ~900px (una fila de la tabla)
        best_row = None
        best_dist = float('inf')

        for row in all_voto_rows:
            # La fila debe estar DESPUÉS del nombre O ligeramente antes (es header)
            dist = abs(row['y'] - cand_y)
            if dist < best_dist and dist < 900:
                best_dist = dist
                best_row = row

        candidato_voto[cand_name] = best_row
        if best_row:
            print(f"   {cand_name}: '{best_row['text']}' @ Y={best_row['y']} (dist={best_dist:.0f}px)")
        else:
            print(f"   {cand_name}: ❌ SIN VOTO DETECTADO")

    # ── Generar análisis de doble trazo para ABELARDO ─────────────────────
    print(f"\n   ── Análisis de tinta (ABELARDO) ──")

    if CANDIDATO_ALVO in candidato_voto and candidato_voto[CANDIDATO_ALVO]:
        row = candidato_voto[CANDIDATO_ALVO]

        # Recortar la región del voto
        crop = crop_voto_region(page_img, row, margin=30)
        crop_path = OUTPUT_DIR / f"{pdf_name}_{CANDIDATO_ALVO.lower()}_voto.png"
        cv2.imwrite(str(crop_path), crop)
        print(f"   Recorte: {crop_path} → {crop.shape}")

        # Análisis de doble trazo
        analysis = detect_double_stroke(crop)

        print(f"   Doble trazo: {analysis['has_double_stroke']}")
        print(f"   Confianza: {analysis['confidence']:.2f}")
        print(f"   Detalles: {analysis['details']}")

        if analysis['has_double_stroke']:
            print(f"   ⚠️  POSIBLE ALTERACIÓN en {pdf_name}!")
    else:
        print(f"   No se pudo detectar el voto de {CANDIDATO_ALVO}")

    # ── Guardar debug ────────────────────────────────────────────────────
    debug_save(page_img, digit_regions, all_voto_rows, col_x, col_w,
               col_y_header, pdf_name)

    # ── Guardar recorte para TODOS los candidatos ─────────────────────────
    print(f"\n   Recortes generados:")
    for cand_name, row in candidato_voto.items():
        if row:
            crop = crop_voto_region(page_img, row, margin=25)
            out_name = f"{pdf_name}_{cand_name.lower()}_dinamico.png"
            crop_path = OUTPUT_DIR / out_name
            cv2.imwrite(str(crop_path), crop)
            print(f"   ✅ {out_name} → {crop.shape}")

    doc.close()

print(f"\n{'='*70}")
print(f"✅ Resultados en: {OUTPUT_DIR}")
print(f"   Debug: {DEBUG_DIR}")
print(f"{'='*70}")
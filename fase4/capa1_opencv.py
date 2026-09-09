#!/usr/bin/env python3
"""
Fase 4 - Capa 1: Visión por computador clásica para scoring de anomalías visuales

Procesa recortes de PDF E-14 y genera scores de anomalía visual:
  - score_grosor_trazo: detecta trazos anómalos (muy gruesos o finos)
  - score_forma_separador: detecta separadores anómalos (círculo grande relleno vs punto delgado)
  - score_densidad_tinta_superpuesta: detecta sobreescritura/tachón

Uso: python3 fase4/capa1_opencv.py
"""

import cv2
import numpy as np
from pathlib import Path
import fitz  # PyMuPDF
import urllib.request, json, uuid
from dataclasses import dataclass
from typing import List, Dict, Tuple

# Configuración
SERVICE_KEY = "REDACTED_SERVICE_KEY"
PROJECT_REF = "oawxinjygprnftkgcjyr"
BASE_URL = f"https://{PROJECT_REF}.supabase.co"
PDF_DIR = Path(__file__).parent.parent / "data" / "pdf_muestra"


@dataclass
class CeldaScore:
    """Score de anomalía para una celda específica del E-14"""
    mesa_key: str
    pagina: int
    tipo_campo: str
    score_grosor: float
    score_separador: float
    score_tinta_superpuesta: float
    score_global: float
    detalles: dict = None
    
    def __str__(self):
        return (f"[{self.mesa_key} p{self.pagina} {self.tipo_campo}] "
                f"grosor={self.score_grosor:.2f} separador={self.score_separador:.2f} "
                f"tinta={self.score_tinta_superpuesta:.2f} global={self.score_global:.2f}")


def score_grosor_trazo(celda_imagen: np.ndarray) -> float:
    """Mide grosor del trazo; 0=normal, 1=anómalo."""
    if celda_imagen.size == 0:
        return 0.0
    
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    
    if len(nonzero) == 0:
        return 0.0
    
    avg_thickness = np.median(nonzero) * 2
    
    if avg_thickness < 2.0:
        return min(1.0, (2.0 - avg_thickness) / 2.0 * 0.5)
    elif avg_thickness > 8.0:
        return min(1.0, (avg_thickness - 8.0) / 8.0)
    else:
        return 0.0


def score_forma_separador(celda_imagen: np.ndarray) -> float:
    """Detecta separadores anómalos; 0=normal, 1=círculo grande relleno."""
    if celda_imagen.size == 0:
        return 0.0
    
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return 0.0
    
    max_score = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 20:
            continue
        
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        
        circularity = 4 * np.pi * area / (perimeter ** 2)
        
        if circularity > 0.7 and 50 < area < 500:
            if area > 150:
                anomalia = min(1.0, (area - 150) / 200)
                max_score = max(max_score, anomalia)
        elif area > 100 and circularity < 0.5:
            max_score = max(max_score, min(1.0, (area - 100) / 150))
    
    return max_score


def score_densidad_tinta_superpuesta(celda_imagen: np.ndarray) -> float:
    """Detecta sobreescritura; 0=normal, 1=densidad alta."""
    if celda_imagen.size == 0:
        return 0.0
    
    if len(celda_imagen.shape) == 3:
        gray = cv2.cvtColor(celda_imagen, cv2.COLOR_BGR2GRAY)
    else:
        gray = celda_imagen
    
    dark_pixels = np.sum(gray < 120)
    total = gray.size
    if total == 0:
        return 0.0
    
    density = dark_pixels / total
    return max(0.0, min(1.0, (density - 0.15) / 0.25))


def procesar_celda(mesa_key, pagina, tipo_campo, coords, page_image):
    """Extrae recorte de la celda y calcula scores."""
    x, y, w, h = coords
    h_img, w_img = page_image.shape[:2]
    
    x0 = max(0, min(x, w_img))
    y0 = max(0, min(y, h_img))
    x1 = min(w_img, x0 + w)
    y1 = min(h_img, y0 + h)
    
    recorte = page_image[y0:y1, x0:x1]
    if recorte.size == 0:
        return CeldaScore(mesa_key, pagina, tipo_campo, 0, 0, 0, 0, {})
    
    s_grosor = score_grosor_trazo(recorte)
    s_separador = score_forma_separador(recorte)
    s_tinta = score_densidad_tinta_superpuesta(recorte)
    s_global = 0.3 * s_grosor + 0.4 * s_separador + 0.3 * s_tinta
    
    return CeldaScore(mesa_key, pagina, tipo_campo, s_grosor, s_separador, s_tinta, s_global, {
        "recorte_shape": recorte.shape[:2]
    })


def guardar_scores_supabase(scores, actas_map, capa1_score_revision=0.6):
    """Persiste scores de Capa 1 en tabla discrepancias de Supabase."""
    guardados = 0
    for score in scores:
        if score.score_global < capa1_score_revision:
            continue
        
        acta_id = actas_map.get(score.mesa_key)
        if not acta_id:
            print(f"    ⚠️  No se encontró acta_id para {score.mesa_key}")
            continue
        
        data = {
            "id": str(uuid.uuid4()),
            "mesa_key": score.mesa_key,
            "acta_oficial_id": acta_id,
            "campo_afectado": score.tipo_campo,
            "valor_oficial": None,
            "valor_ciudadano": None,
            "tipo_anomalia": "trazo_anomalo",
            "score_capa1": float(score.score_global),
            "razon_flag": (f"Capa1: grosor={score.score_grosor:.2f}, "
                          f"separador={score.score_separador:.2f}, "
                          f"tinta={score.score_tinta_superpuesta:.2f}"),
            "prioridad": "alta" if score.score_global >= 0.85 else "media",
            "estado": "por_verificar"
        }
        
        url = f"{BASE_URL}/rest/v1/discrepancias"
        req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
        req.add_header("apikey", SERVICE_KEY)
        req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=representation")
        
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 201:
                    print(f"    ✅ Saved: {score.tipo_campo} = {score.score_global:.2f}")
                    guardados += 1
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    return guardados


def procesar_pdf(pdf_path, mesa_key):
    """Renderiza el PDF y procesa las celdas de votación."""
    scores = []
    doc = fitz.open(str(pdf_path))
    
    # Coordenadas basadas en análisis del E-14 estándar colombiano
    # Documento: 871x2616 pts, renderizado a 3630x10900 px @ 300 DPI
    # Factor de escala: ~4.16 px / pt
    celdas = {
        1: {
            "votos_candidato_1": (1300, 6700, 800, 300),   # Columna izquierda, fila candidatos
            "votos_candidato_2": (2700, 6700, 800, 300),   # Columna derecha, fila candidatos
        },
        2: {
            "votos_blanco": (1300, 7100, 800, 300),        # Blanco, izquierda
            "votos_nulos": (2700, 7100, 800, 300),           # Nulos, derecha
            "votos_no_marcados": (1900, 7500, 800, 300),     # No marcados, centro
        }
    }
    
    for page_idx in range(1, 3):
        if page_idx > len(doc):
            continue
        
        page = doc[page_idx - 1]
        mat = fitz.Matrix(300/72, 300/72)
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.tobytes("png"), np.uint8)
        page_img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        
        if page_img is None:
            continue
        
        for tipo_campo, coords in celdas.get(page_idx, {}).items():
            score = procesar_celda(mesa_key, page_idx, tipo_campo, coords, page_img)
            scores.append(score)
    
    doc.close()
    return scores


def obtener_actas_map():
    """Fetch UUIDs de actas desde Supabase, mapeo por mesa_key."""
    req = urllib.request.Request(f"{BASE_URL}/rest/v1/actas_oficiales?select=id,mesa_key")
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        actas = json.loads(resp.read().decode())
    return {a["mesa_key"]: a["id"] for a in actas}


def main():
    """Procesa los 5 PDFs de muestra contra Supabase."""
    pdf_to_mesa = {
        "Anza.pdf": "01-034-01-001-000",
        "Turbo_015.pdf": "01-280-00-000-015",
        "Turbo_001.pdf": "01-280-00-000-001",
        "Turbo_002.pdf": "01-280-00-000-002",
        "Turbo_006.pdf": "01-280-00-000-006",
    }
    
    print("📥 Obteniendo actas desde Supabase...")
    actas_map = obtener_actas_map()
    print(f"   {len(actas_map)} actas encontradas\n")
    
    total_discrepancias = 0
    for pdf_file, mesa_key in pdf_to_mesa.items():
        pdf_path = PDF_DIR / pdf_file
        if not pdf_path.exists():
            print(f"  ❌ No encontrado: {pdf_file}")
            continue
        
        print(f"📝 {mesa_key} ({pdf_file})")
        scores = procesar_pdf(pdf_path, mesa_key)
        
        for s in scores:
            print(f"   {'⚠️ ' if s.score_global > 0.3 else '✅ '}{s.tipo_campo}: global={s.score_global:.2f}")
        
        n = guardar_scores_supabase(scores, actas_map)
        total_discrepancias += n
        print()
    
    print("="*60)
    print("✅ FASE 4 COMPLETADA")
    print(f"   {total_discrepancias} discrepancias tipo 'trazo_anomalo' creadas en Supabase")
    print("="*60)


if __name__ == "__main__":
    main()
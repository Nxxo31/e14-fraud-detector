#!/usr/bin/env python3
"""
PIPELINE DE DETECCIÓN DE FRAUDE - VERSIÓN SUBPROCESO
Usa EasyOCR del sistema (python3) mediante subprocesos.
"""

import cv2
import fitz
import numpy as np
from pathlib import Path
import json
import pytesseract
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from typing import List, Optional
import re

PDF_DIR = Path("/home/sebas/proyectos/e14-audit-platform/data/pdf_adicionales")
PDF_MUESTRA = Path("/home/sebas/proyectos/e14-audit-platform/data/pdf_muestra")
OUTPUT_DIR = Path("/home/sebas/proyectos/e14-audit-platform/data/resultados_fraude")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

@dataclass
class VotoCelda:
    x: int; y: int; w: int; h: int
    texto_ocr: str; numero: Optional[int]; confianza: float; tipo: str

@dataclass
class AnomaliaFraude:
    tipo: str; ubicacion: str; severidad: str; evidencia: str; score: float

@dataclass
class ResultadoAnalisis:
    pdf_name: str; departamento: str; municipio: str; mesa: str
    votos_detectados: List[VotoCelda]; anomalias: List[AnomaliaFraude]
    score_fraude: float; veredicto: str; resumen: str


def ocr_zona_votos_easyocr(img_path: str) -> list:
    """Ejecuta EasyOCR del sistema como subproceso sobre una imagen."""
    script = f'''
import easyocr, json, sys
reader = easyocr.Reader(['es', 'en'], gpu=False)
results = reader.readtext("{img_path}", paragraph=False)
output = []
for bbox, text, conf in results:
    if conf > 0.2:
        output.append({{"text": text, "conf": conf, "x": int(bbox[0][0]), "y": int(bbox[0][1]),
                        "w": int(bbox[2][0]-bbox[0][0]), "h": int(bbox[2][1]-bbox[0][1])}})
print(json.dumps(output))
'''
    result = subprocess.run(
        ["python3", "-c", script],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except:
            return []
    return []


def extraer_votos_easyocr(img_gray: np.ndarray) -> List[VotoCelda]:
    """Detecta números en zona de votación usando EasyOCR del sistema."""
    h, w = img_gray.shape
    
    # Guardar zona de votos como imagen temporal
    zona = img_gray[int(h*0.20):int(h*0.65), int(w*0.50):int(w*0.85)]
    if zona.size == 0:
        return []
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        cv2.imwrite(tmp.name, zona)
        tmp_path = tmp.name
    
    # OCR con subproceso
    detections = ocr_zona_votos_easyocr(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)
    
    votos = []
    for d in detections:
        numeros = re.findall(r'\d+', d['text'])
        numero = int(numeros[0]) if numeros else None
        
        votos.append(VotoCelda(
            x=d['x']+int(w*0.50), y=d['y']+int(h*0.20),
            w=d['w'], h=d['h'],
            texto_ocr=d['text'], numero=numero,
            confianza=round(d['conf'], 2), tipo="candidato"
        ))
    
    return sorted(votos, key=lambda v: v.y)


def extraer_info_tesseract(img_gray: np.ndarray) -> dict:
    """Metadatos del acta con Tesseract."""
    data = pytesseract.image_to_data(img_gray, lang='spa', output_type=pytesseract.Output.DICT)
    info = {'departamento': '', 'municipio': '', 'zona': '', 'puesto': '', 'mesa': ''}
    for i in range(len(data['text'])):
        t = data['text'][i].strip().upper()
        if 'DEPARTAMENTO' in t: info['departamento'] = data['text'][i]
        elif 'MUNICIPIO' in t: info['municipio'] = data['text'][i]
        elif t.startswith('ZONA'): info['zona'] = data['text'][i]
        elif t.startswith('PUESTO'): info['puesto'] = data['text'][i]
        elif t.startswith('MESA'): info['mesa'] = data['text'][i]
    return info


def detectar_anomalias_visuales(img_gray: np.ndarray) -> List[AnomaliaFraude]:
    """Tachones, enmendaduras, firmas."""
    anomalias = []
    h, w = img_gray.shape
    
    # Tachones: líneas horizontales gruesas
    edges = cv2.Canny(img_gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=200, maxLineGap=10)
    if lines is not None and len(lines) > 15:
        anomalias.append(AnomaliaFraude("tachon", "Zona votación", "media",
                       f"{len(lines)} líneas horizontales", min(1.0, len(lines)/25)))
    
    # Firmas faltantes
    zona_firmas = img_gray[int(h*0.75):, :]
    if zona_firmas.size > 0:
        dark = np.sum(zona_firmas < 100) / zona_firmas.size
        if dark < 0.02:
            anomalias.append(AnomaliaFraude("firma_faltante", "Zona firmas", "alta",
                           f"Solo {dark:.1%} tinta", 0.9))
    
    return anomalias


def verificar_consistencia(votos: List[VotoCelda]) -> List[AnomaliaFraude]:
    """Verifica suma de votos = total."""
    numeros = [v.numero for v in votos if v.numero is not None]
    if len(numeros) < 3:
        return [AnomaliaFraude("pocos_datos", "Tabla votación", "alta",
                f"Solo {len(numeros)} números", 0.8)]
    
    total = max(numeros)
    candidatos = [n for n in numeros if n < total * 0.9]
    if candidatos:
        suma = sum(candidatos)
        diff = abs(suma - total)
        if diff > total * 0.1:
            return [AnomaliaFraude("suma_inconsistente", "Tabla votación", "alta",
                    f"Suma={suma} vs Total={total} (Δ={diff})", 0.95)]
    return []


def analizar_acta(pdf_path: Path) -> ResultadoAnalisis:
    """Pipeline completo de detección de fraude."""
    print(f"\n{'='*60}")
    print(f"🔍 {pdf_path.name}")
    
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(300/72, 300/72)
    pix = page.get_pixmap(matrix=mat)
    img = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    doc.close()
    
    # Extraer info
    info = extraer_info_tesseract(img_gray)
    print(f"   {info['departamento']} | {info['mesa']}")
    
    # Votos con EasyOCR (subproceso)
    print("   🔢 OCR de votos...")
    votos = extraer_votos_easyocr(img_gray)
    print(f"   → {len(votos)} números detectados")
    for v in votos[:5]:
        print(f"      {v.texto_ocr} (conf={v.confianza})")
    
    # Anomalías
    anomalias = detectar_anomalias_visuales(img_gray)
    anomalias.extend(verificar_consistencia(votos))
    
    # Score
    score = max([a.score for a in anomalias]) if anomalias else 0.0
    score += 0.1 * len(anomalias)
    score = min(1.0, score)
    veredicto = "FRAUDE" if score > 0.7 else ("SOSPECHOSO" if score > 0.3 else "LIMPIO")
    
    print(f"   📊 Score: {score:.2f} | {veredicto}")
    
    return ResultadoAnalisis(
        pdf_name=pdf_path.name,
        departamento=info['departamento'], municipio=info['municipio'], mesa=info['mesa'],
        votos_detectados=votos, anomalias=anomalias,
        score_fraude=round(score, 2), veredicto=veredicto,
        resumen=f"{len(votos)} votos, {len(anomalias)} anomalías"
    )


if __name__ == "__main__":
    pdfs = [PDF_MUESTRA / "Anza.pdf"] if (PDF_MUESTRA / "Anza.pdf").exists() else []
    pdfs += [p for p in sorted(PDF_DIR.glob("E14_*.pdf"))[:6] if "(" not in str(p)]
    
    resultados = []
    for pdf in pdfs:
        try:
            res = analizar_acta(pdf)
            resultados.append(res)
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    output = OUTPUT_DIR / "resultados_fraude.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in resultados], f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(resultados)} actas analizadas → {output}")
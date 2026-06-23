#!/usr/bin/env python3
"""
analizar_pdfs.py — Analiza los 5 PDFs E-14 reales y extrae:
  1. Metadatos de cada PDF (páginas, tamaño)
  2. QR decodificado y sus metadatos (para verificar/corregir fixtures)
  3. Dimensiones de página (para calibrar coordenadas de Capa 1)
  4. Texto extraído de cada página (para validar estructura)

Uso: python3 fase2/analizar_pdfs.py
"""
import sys
from pathlib import Path

# Agregar proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

PDF_DIR = Path(__file__).parent.parent / "data" / "pdf_muestra"

def analyze_pdf(pdf_path: Path) -> dict:
    """Analiza un PDF individual"""
    import fitz
    
    from PIL import Image
    import io

    print(f"\n{'='*60}")
    print(f"📄 Analizando: {pdf_path.name}")
    print(f"{'='*60}")

    result = {
        "file": pdf_path.name,
        "size_bytes": pdf_path.stat().st_size,
        "pages": [],
        "qr_data": [],
    }

    doc = fitz.open(str(pdf_path))
    result["page_count"] = len(doc)
    print(f"  Páginas: {len(doc)}")

    for page_num in range(len(doc)):
        page = doc[page_num]
        width = page.rect.width
        height = page.rect.height
        print(f"  Página {page_num+1}: {width:.0f}x{height:.0f} pts")

        # Extraer texto
        text = page.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        print(f"    Texto extraído: {len(lines)} líneas")
        for line in lines[:8]:
            print(f"      → {line[:80]}")

        # Renderizar página a imagen para QR
        mat = fitz.Matrix(2, 2)  # 144 DPI para QR detection
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Buscar QR usando OpenCV (no necesita libzbar externo)
        import cv2
        import numpy as np
        try:
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            qr_detector = cv2.QRCodeDetector()
            retval, decoded_info, points, straight_qrcode = qr_detector.detectAndDecodeMulti(img_cv)
            if retval and decoded_info:
                for i, qr_data in enumerate(decoded_info):
                    if qr_data:
                        rect = points[i] if len(points) > i else None
                        print(f"    QR detectado: data={qr_data}")
                        if rect is not None:
                            x, y, w, h = cv2.boundingRect(rect.astype(int))
                            print(f"      Position: ({x}, {y}) size={w}x{h}")
                        result["qr_data"].append({
                            "type": "QR_CODE",
                            "data": qr_data,
                            "page": page_num + 1,
                        })
            else:
                print(f"    Sin QR en esta página")
        except Exception as e:
            print(f"    QR error: {e}")

        result["pages"].append({
            "page": page_num + 1,
            "width": width,
            "height": height,
            "lines": len(lines),
        })

    doc.close()
    return result


def main():
    print(f"\n{'='*60}")
    print("🔍 ANÁLISIS DE PDFs E-14 — Extracción de metadatos y QR")
    print(f"{'='*60}")
    print(f"Directorio: {PDF_DIR}")

    if not PDF_DIR.exists():
        print(f"❌ Directorio no encontrado: {PDF_DIR}")
        return

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No se encontraron PDFs en: {PDF_DIR}")
        return

    print(f"PDFs encontrados: {len(pdf_files)}")

    all_results = []
    for pdf_path in pdf_files:
        result = analyze_pdf(pdf_path)
        all_results.append(result)

    # Resumen de QR
    print(f"\n{'='*60}")
    print("📊 RESUMEN DE QR DETECTADOS")
    print(f"{'='*60}")
    for r in all_results:
        qrs = r.get("qr_data", [])
        if qrs:
            for qr in qrs:
                print(f"  {r['file']} (página {qr['page']}): {qr['data']}")
        else:
            print(f"  {r['file']}: ❌ Sin QR detectado")

    # Resumen de páginas
    print(f"\n{'='*60}")
    print("📊 RESUMEN DE DIMENSIONES")
    print(f"{'='*60}")
    for r in all_results:
        first_page = r["pages"][0] if r["pages"] else {}
        print(f"  {r['file']}: {len(r['pages'])} páginas, página 1 = {first_page.get('width',0):.0f}x{first_page.get('height',0):.0f} pts")

    print(f"\n✅ Análisis completado para {len(all_results)} PDFs")


if __name__ == "__main__":
    main()
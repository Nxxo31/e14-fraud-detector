#!/usr/bin/env python3
"""Verificar qué contienen las celdas generadas y por qué están vacías."""

import easyocr, fitz, cv2, numpy as np
from pathlib import Path

reader = easyocr.Reader(['es'], gpu=False)

# Analizar Turbo_006
pdf_path = "data/pdf_muestra/Turbo_006.pdf"
doc = fitz.open(pdf_path)
page = doc[0]
mat = fitz.Matrix(300/72, 300/72)
pix = page.get_pixmap(matrix=mat)
img = cv2.imdecode(np.frombuffer(pix.tobytes('png'), np.uint8), cv2.IMREAD_COLOR)
h, w = img.shape[:2]
print(f"Imagen: {w}x{h} px\n")

det = reader.readtext(img, paragraph=False)
print("TODAS las detecciones en columna derecha (X>2500):")
for bbox, text, conf in det:
    if conf > 0.3:
        x, y = int(bbox[0][0]), int(bbox[0][1])
        if x > 2500:
            print(f"  {repr(text):<25} X:{x:>5} Y:{y:>5} conf:{conf:.2f}")

doc.close()

# Ahora ver qué contienen los recortes generados
print("\n\nContenido de los recortes:")
celdas_dir = Path("data/celdas_ocr_v2")
for png_path in sorted(celdas_dir.glob("Turbo_006*.png")):
    crop = cv2.imread(str(png_path))
    print(f"\n{png_path.name}: shape={crop.shape}")
    det2 = reader.readtext(crop, paragraph=False)
    if det2:
        print(f"  Detecciones: {[(t,c) for b,t,c in det2 if c>0.3]}")
    else:
        print("  SIN TEXTO DETECTADO")
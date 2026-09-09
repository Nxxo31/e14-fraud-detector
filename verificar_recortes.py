#!/usr/bin/env python3
import cv2, numpy as np, sys

# Verificar los recortes de ABELARDO
for name in ['Anza', 'Turbo_001', 'Turbo_006', 'Turbo_015', 'Turbo_002']:
    p = f'data/celdas_dinamicas/{name}_abelardo_voto.png'
    img = cv2.imread(p)
    if img is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink = cv2.countNonZero(binary)
        total = img.shape[0] * img.shape[1]
        print(f'{name}: shape={img.shape}, tinta={ink/total:.3f} ({ink}px)')
    else:
        print(f'{name}: NO ENCONTRADO')

# También verificar el recorte de Turbo_002 (que no detectó nada)
p2 = 'data/celdas_dinamicas/Turbo_002_iván_dinamico.png'
img2 = cv2.imread(p2)
if img2 is not None:
    print(f"\nTurbo_002 IVAN: shape={img2.shape}")
else:
    print(f"\nTurbo_002 IVAN: NO ENCONTRADO (expected - no digits detected)")
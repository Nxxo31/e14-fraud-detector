#!/usr/bin/env python3
"""
VERIFICACIÓN RÁPIDA: Ver todos los debug images generados.
Este script lista los archivos y sus tamaños para confirmar que la
detección dinámica está funcionando correctamente.
"""
from pathlib import Path

debug_dir = Path("data/debug_tinta")
celdas_dir = Path("data/celdas_dinamicas")

print("=== IMÁGENES DE DEBUG (zona de columna votacion marcada) ===")
for p in sorted(debug_dir.glob("*.png")):
    import os
    size_kb = os.path.getsize(p) / 1024
    print(f"  {p.name}: {size_kb:.0f} KB")

print("\n=== RECORTES DE VOTOS (ABELARDO) ===")
for p in sorted(celdas_dir.glob("*_abelardo_voto.png")):
    import os
    size_kb = os.path.getsize(p) / 1024
    print(f"  {p.name}: {size_kb:.0f} KB")

print("\n=== RECORTES DINÁMICOS (TODOS) ===")
for p in sorted(celdas_dir.glob("*_dinamico.png")):
    import os
    size_kb = os.path.getsize(p) / 1024
    print(f"  {p.name}: {size_kb:.0f} KB")

print(f"\nTotal archivos: {len(list(celdas_dir.glob('*.png')))}")
#!/usr/bin/env python3
# seed_data.py — Pobla DIVIPOLA e inserta los 5 PDFs de muestra

import sqlite3
import os
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/proyectos/e14-audit-platform/data/e14_audit.db")
PDF_DIR = os.path.expanduser("~/proyectos/e14-audit-platform/data/pdf_muestra")

conn = sqlite3.connect(DB_PATH)

# ────────────────────────────────────────────────────────────
# 1. Poblar DIVIPOLA — Antioquia (código 01)
# ────────────────────────────────────────────────────────────

# Según la codificación oficial DIVIPOLA para las elecciones 2026,
# Antioquia = código 01. Anza = código 034, Turbo = código 280.

conn.execute("INSERT OR IGNORE INTO divipole_departamento (codigo_departamento, nombre_departamento) VALUES (?, ?)",
             ("01", "Antioquia"))

conn.execute("INSERT OR IGNORE INTO divipole_municipio (codigo_departamento, codigo_municipio, nombre_municipio) VALUES (?, ?, ?)",
             ("01", "034", "Anzá"))
conn.execute("INSERT OR IGNORE INTO divipole_municipio (codigo_departamento, codigo_municipio, nombre_municipio) VALUES (?, ?, ?)",
             ("01", "280", "Turbo"))

print("✅ DIVIPOLA poblado: Antioquia con 2 municipios (Anzá, Turbo)")

# ────────────────────────────────────────────────────────────
# 2. Insertar los 5 PDFs de muestra en actas_oficiales
# ────────────────────────────────────────────────────────────

# Mapeo de archivos PDF a mesas
# Según los nombres de archivo y el análisis previo documentado en PROJECT.md:
#   Anza.pdf        → Anzá,    zona 01, puesto 001, mesa 000
#   Turbo_015.pdf   → Turbo,   zona 00, puesto 000, mesa 015  (Delegados/Claveros — la más controversial)
#   Turbo_001.pdf   → Turbo,   zona 00, puesto 000, mesa 001
#   Turbo_002.pdf   → Turbo,   zona 00, puesto 000, mesa 002
#   Turbo_006.pdf   → Turbo,   zona 00, puesto 000, mesa 006

# ⚠️ Los nombres exactos de los archivos deben coincidir con los que ya copiamos
mesas = [
    {
        "pdf_file": "Anza.pdf",
        "mesa_key": "01-034-01-001-000",
        "codigo_departamento": "01",
        "codigo_municipio": "034",
        "zona": "01",
        "puesto": "001",
        "mesa": "000",
        "lugar_votacion": "Anzá — Puesto 001",
        "tipo_ejemplar": "delegados",
        "version_formato": "Ver: 01",
    },
    {
        "pdf_file": "Turbo_015.pdf",
        "mesa_key": "01-280-00-000-015",
        "codigo_departamento": "01",
        "codigo_municipio": "280",
        "zona": "00",
        "puesto": "000",
        "mesa": "015",
        "lugar_votacion": "Turbo — Puesto 000 Mesa 015",
        "tipo_ejemplar": "delegados",
        "version_formato": "Ver: 01",
    },
    {
        "pdf_file": "Turbo_001.pdf",
        "mesa_key": "01-280-00-000-001",
        "codigo_departamento": "01",
        "codigo_municipio": "280",
        "zona": "00",
        "puesto": "000",
        "mesa": "001",
        "lugar_votacion": "Turbo — Puesto 000 Mesa 001",
        "tipo_ejemplar": "delegados",
        "version_formato": "Ver: 01",
    },
    {
        "pdf_file": "Turbo_002.pdf",
        "mesa_key": "01-280-00-000-002",
        "codigo_departamento": "01",
        "codigo_municipio": "280",
        "zona": "00",
        "puesto": "000",
        "mesa": "002",
        "lugar_votacion": "Turbo — Puesto 000 Mesa 002",
        "tipo_ejemplar": "delegados",
        "version_formato": "Ver: 01",
    },
    {
        "pdf_file": "Turbo_006.pdf",
        "mesa_key": "01-280-00-000-006",
        "codigo_departamento": "01",
        "codigo_municipio": "280",
        "zona": "00",
        "puesto": "000",
        "mesa": "006",
        "lugar_votacion": "Turbo — Puesto 000 Mesa 006",
        "tipo_ejemplar": "delegados",
        "version_formato": "Ver: 01",
    },
]

inserted = 0
for m in mesas:
    pdf_path = os.path.join(PDF_DIR, m["pdf_file"])
    pdf_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else None

    acta_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO actas_oficiales (
            id, mesa_key, codigo_departamento, codigo_municipio,
            zona, puesto, mesa, lugar_votacion, tipo_ejemplar,
            pdf_storage_path, version_formato,
            paginas_esperadas, estado_procesamiento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente')
    """, (
        acta_id, m["mesa_key"], m["codigo_departamento"], m["codigo_municipio"],
        m["zona"], m["puesto"], m["mesa"], m["lugar_votacion"], m["tipo_ejemplar"],
        pdf_path, m["version_formato"],
        2  # paginas_esperadas = 2
    ))
    inserted += 1
    print(f"✅ Insertado acta: {m['mesa_key']} ({m['pdf_file']}) [{pdf_size:,} bytes]")

conn.commit()

# Verificar
cursor = conn.execute("SELECT mesa_key, codigo_departamento, codigo_municipio, estado_procesamiento FROM actas_oficiales")
rows = cursor.fetchall()
print(f"\n📊 Total de actas insertadas: {len(rows)}")
for r in rows:
    print(f"  → {r[0]} (Dpto={r[1]}, Mun={r[2]}, Estado={r[3]})")

# Verificar DIVIPOLA
cursor2 = conn.execute("SELECT nombre_departamento, nombre_municipio FROM divipole_municipio m JOIN divipole_departamento d ON d.codigo_departamento = m.codigo_departamento")
dptos = cursor2.fetchall()
print(f"\n📊 Departamentos/Municipios poblados: {len(dptos)}")
for d in dptos:
    print(f"  → {d[0]} → {d[1]}")

conn.close()
print("\n🎉 Fase 1 — Datos de muestra insertados correctamente")
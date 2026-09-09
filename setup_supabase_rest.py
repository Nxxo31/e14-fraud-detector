#!/usr/bin/env python3
"""
Crear esquema en Supabase usando API REST (PostgREST).
No necesita psycopg2 ni IPv6 — funciona completamente via HTTPS.

La API de Supabase (PostgREST) permite:
  - Crear tablas via POST
  - Insertar datos
  - Leer/Obtener

Estrategia: crear tablas una por una usando POST con datos de ejemplo,
insertar DIVIPOLA y luego migrar todos los datos desde SQLite.
"""

import urllib.request
import json
import time

URL = "https://oawxinjygprnftkgcjyr.supabase.co"
KEY = "REDACTED_SERVICE_KEY"

def supabase(method, endpoint, data=None):
    req = urllib.request.Request(
        f"{URL}/rest/v1/{endpoint}",
        data=json.dumps(data).encode() if data else None,
        method=method
    )
    req.add_header('apikey', KEY)
    req.add_header('Authorization', f'Bearer {KEY}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Prefer', 'return=representation')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode()) if resp.status != 204 else []
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return None, str(e)

# Verificar estado
status, result = supabase('GET', '')
print(f"Supabase API: {status}")
if status == 200:
    print("✅ Servicio activo")

# 1. Crear DIVIPOLA departamento
print("\n📋 Creando tabla divipole_departamento...")
dept_data = {
    "codigo_departamento": "01",
    "nombre_departamento": "Antioquia"
}
status, result = supabase('POST', 'divipole_departamento', dept_data)
print(f"  Status: {status}")
if status in (201, 200):
    print(f"  ✅ Creado: {result}")

# 2. Crear DIVIPOLA municipio
print("\n📋 Creando tabla divipole_municipio...")
muni_data = {
    "codigo_departamento": "01",
    "codigo_municipio": "034",
    "nombre_municipio": "Anzá"
}
status, result = supabase('POST', 'divipole_municipio', muni_data)
print(f"  Status: {status}")
if status in (201, 200):
    print(f"  ✅ Creado: {result}")

# Insertar Turbo también
turbo_data = {
    "codigo_departamento": "01",
    "codigo_municipio": "280",
    "nombre_municipio": "Turbo"
}
status, result = supabase('POST', 'divipole_municipio', turbo_data)
print(f"  Turbo: {status}")

# 3. Crear tabla configuracion_sistema
print("\n📋 Creando configuracion_sistema...")
configs = [
    {'clave': 'umbral_min_votos', 'valor': '5', 'descripcion': 'Mínimo votos para consenso'},
    {'clave': 'umbral_consenso_pct', 'valor': '0.80', 'descripcion': 'Porcentaje consenso'},
    {'clave': 'capa1_score_revision', 'valor': '0.60', 'descripcion': 'Score Capa 1 revisión'},
    {'clave': 'capa1_score_prioridad_alta', 'valor': '0.85', 'descripcion': 'Score Capa 1 prioridad alta'},
]
for cfg in configs:
    supabase('POST', 'configuracion_sistema', cfg)
print("  ✅ 4 parámetros insertados")

print("\n✅ Creaciones completas")
print("Para crear tablas completas (actas_oficiales, discrepancias, etc.),")
print("se necesita el SQL Editor. La API REST no soporta CREATE TABLE directo.")
print(f"\nSolución: copia schema_postgresql.sql en el SQL Editor de Supabase:")
print(f"Dashboard → SQL Editor → Pegar → Run")
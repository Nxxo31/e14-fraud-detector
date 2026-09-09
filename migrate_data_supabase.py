#!/usr/bin/env python3
"""
Migra datos desde SQLite local → Supabase PostgreSQL
"""
import sqlite3, json, urllib.request, uuid
from pathlib import Path

DB_SQLITE = Path(__file__).parent / "data" / "e14_audit.db"
SCHEMA_PATH = Path(__file__).parent / "schema_postgresql.sql"

PROJECT_REF = "oawxinjygprnftkgcjyr"
SERVICE_KEY = "REDACTED_SERVICE_KEY"
BASE_URL = f"https://{PROJECT_REF}.supabase.co"

def supabase_rest(method, table, data=None, params=""):
    url = f"{BASE_URL}/rest/v1/{table}{params}"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method)
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body and resp.status != 204 else []
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]

def supabase_rpc(func_name, params):
    """Ejecutar función RPC via REST"""
    url = f"{BASE_URL}/rest/v1/rpc/{func_name}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else []
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]

conn = sqlite3.connect(str(DB_SQLITE))

# ── 1. DIVIPOLA ───────────────────────────────────────────────
print("📍 Migrando DIVIPOLA...")
for row in conn.execute("SELECT * FROM divipole_departamento"):
    codigo, nombre = row
    status, _ = supabase_rest("POST", "divipole_departamento", {"codigo_departamento": codigo, "nombre_departamento": nombre})
    if status == 201:
        print(f"  ✅ Depto: {nombre}")
    elif status == 409:
        print(f"  ⚠️  Ya existe: {nombre}")
    else:
        print(f"  ❌ {status}")

for row in conn.execute("SELECT * FROM divipole_municipio"):
    cod_d, cod_m, nombre = row
    status, _ = supabase_rest("POST", "divipole_municipio", {"codigo_departamento": cod_d, "codigo_municipio": cod_m, "nombre_municipio": nombre})
    if status == 201:
        print(f"  ✅ Muni: {nombre}")
    elif status == 409:
        print(f"  ⚠️  Ya existe: {nombre}")
    else:
        print(f"  ❌ {status}: {_}")

# ── 2. Configuracion ─────────────────────────────────────────
print("\n⚙️  Migrando configuracion_sistema...")
for row in conn.execute("SELECT * FROM configuracion_sistema"):
    clave, valor, desc = row[0], row[1], (row[2] if len(row) > 2 else None)
    status, _ = supabase_rest("POST", "configuracion_sistema", {"clave": clave, "valor": valor, "descripcion": desc})
    print(f"  ✅ {clave} = {valor}" if status == 201 else f"  ⚠️  {clave}: {status}")

# ── 3. Actas Oficiales ───────────────────────────────────────
print("\n📋 Migrando actas_oficiales...")
actas_map = {}  # old_id -> new_uuid

for row in conn.execute("SELECT * FROM actas_oficiales"):
    # row = (id, mesa_key, cod_dept, cod_mun, zona, puesto, mesa, lugar_vot, tipo,
    #        pdf_url, pdf_storage, kit, formulario, version, qr_raw, qr_match,
    #        pag_total, pag_esp, pag2_vacia, firmas_det,
    #        total_e11, total_urna, total_incinerados,
    #        c1, c2, blanco, nulos, no_marcados, suma_calc,
    #        flag_excede, flag_no_coincide, flag_nivel, flag_pag, flag_firmas, flag_qr,
    #        capa_max, estado_proc, creado, actualizado)
    new_uuid = str(uuid.uuid4())
    r = row
    data = {
        "id": new_uuid,
        "mesa_key": r[1], "codigo_departamento": r[2], "codigo_municipio": r[3],
        "zona": r[4], "puesto": r[5], "mesa": r[6], "lugar_votacion": r[7],
        "tipo_ejemplar": r[8],
        "pdf_url": r[9], "pdf_storage_path": r[10],
        "kit_numero": r[11], "formulario_numero": r[12], "version_formato": r[13],
        "qr_raw_value": r[14],
        "qr_decoded_match": bool(r[15]) if r[15] is not None else None,
        "paginas_total": r[16], "paginas_esperadas": r[17],
        "pagina_2_vacia": bool(r[18]) if r[18] is not None else None,
        "firmas_detectadas": r[19],
        "total_votantes_e11": r[20], "total_votos_urna": r[21], "total_votos_incinerados": r[22],
        "votos_candidato_1": r[23], "votos_candidato_2": r[24],
        "votos_blanco": r[25], "votos_nulos": r[26], "votos_no_marcados": r[27],
        "suma_total_calculada": r[28],
        "flag_aritmetica_excede_total": bool(r[29]),
        "flag_aritmetica_no_coincide": bool(r[30]),
        "flag_nivelacion_inconsistente": bool(r[31]),
        "flag_paginas_incompletas": bool(r[32]),
        "flag_firmas_insuficientes": bool(r[33]),
        "flag_qr_metadata_mismatch": bool(r[34]),
        "capa_maxima_procesada": r[35], "estado_procesamiento": r[36],
    }
    status, result = supabase_rest("POST", "actas_oficiales", data)
    if status == 201:
        print(f"  ✅ {r[1]}")
        actas_map[r[0]] = new_uuid
    elif status == 409:
        print(f"  ⚠️  Ya existe: {r[1]}")
    else:
        print(f"  ❌ {r[1]}: {result}")

# ── 4. Discrepancias ──────────────────────────────────────────
print("\n🚩 Migrando discrepancias...")
disc_count = 0
for row in conn.execute("SELECT * FROM discrepancias"):
    # Buscar old acta_id → new uuid
    old_acta_id = row[3]  # acta_oficial_id
    new_acta_id = actas_map.get(old_acta_id)
    if not new_acta_id:
        continue

    data = {
        "id": str(uuid.uuid4()),
        "mesa_key": row[1],
        "acta_oficial_id": new_acta_id,
        "evidencia_ciudadana_id": row[4],  # UUID o null
        "campo_afectado": row[5], "valor_oficial": row[6], "valor_ciudadano": row[7],
        "tipo_anomalia": row[8],
        "score_capa0": row[9], "score_capa1": row[10], "score_capa2": row[11],
        "razon_flag": row[12],
        "evidencia_imagen_recorte_url": row[13],
        "prioridad": row[14], "estado": row[15],
        "votos_confirma": row[16], "votos_rechaza": row[17], "congelado": bool(row[18]),
    }
    status, _ = supabase_rest("POST", "discrepancias", data)
    if status == 201:
        disc_count += 1
    elif status == 409:
        print(f"  ⚠️  Ya existe: {row[1]} / {row[5]}")
    else:
        print(f"  ❌ {row[1]}: {_}")

print(f"  ✅ {disc_count} discrepancias migradas")

# ── 5. Cola de procesamiento ─────────────────────────────────
print("\n⏳ Migrando cola_procesamiento...")
for row in conn.execute("SELECT * FROM cola_procesamiento"):
    old_acta_id = row[2]
    new_acta_id = actas_map.get(old_acta_id)
    if not new_acta_id:
        continue
    data = {
        "id": str(uuid.uuid4()), "mesa_key": row[1], "acta_id": new_acta_id,
        "capa_actual": row[3], "estado_slot": row[4],
        "worker_id": row[5], "intentos": row[6], "max_intentos": row[7],
        "ultimo_error": row[8], "tomado_en": row[9], "completado_en": row[10],
    }
    status, _ = supabase_rest("POST", "cola_procesamiento", data)
    if status == 201:
        pass

print("\n✅ Migración completa!")
conn.close()
print(f"   Actas: {len(actas_map)}")
print(f"   Discrepancias: {disc_count}")
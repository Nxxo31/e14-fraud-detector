#!/usr/bin/env python3
"""
Genera y persiste las 7 discrepancias de Capa 0 directamente en Supabase.
"""
import urllib.request, json, uuid

SERVICE_KEY = "REDACTED_SERVICE_KEY"
PROJECT_REF = "oawxinjygprnftkgcjyr"
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

# Obtener actas desde Supabase
print("📋 Obteniendo actas de Supabase...")
_, actas = supabase_rest("GET", "actas_oficiales", params="?select=id,mesa_key,votos_candidato_1,votos_candidato_2,votos_blanco,votos_nulos,votos_no_marcados,total_votos_urna,total_votantes_e11,total_votos_incinerados,firmas_detectadas")
print(f"   {len(actas)} actas encontradas")

# Generar discrepancias para cada acta según reglas Capa 0
discrepancias_creadas = 0
for acta in actas:
    disc_list = []
    mesa = acta["mesa_key"]
    votes_sum = (acta.get("votos_candidato_1") or 0) + (acta.get("votos_candidato_2") or 0) + (acta.get("votos_blanco") or 0) + (acta.get("votos_nulos") or 0) + (acta.get("votos_no_marcados") or 0)
    total_urna = acta.get("total_votos_urna") or 0
    total_e11 = acta.get("total_votantes_e11") or 0
    total_inc = acta.get("total_votos_incinerados") or 0
    firmas = acta.get("firmas_detectadas") or 0

    # 1. Excede total
    if votes_sum > total_urna:
        disc_list.append({
            "mesa_key": mesa,
            "acta_oficial_id": acta["id"],
            "campo_afectado": "suma_votos",
            "valor_oficial": str(total_urna),
            "valor_ciudadano": str(votes_sum),
            "tipo_anomalia": "aritmetica_excede_total",
            "score_capa0": 1.0,
            "razon_flag": f"Suma votos ({votes_sum}) excede total urna ({total_urna}) por {votes_sum - total_urna}",
            "prioridad": "alta",
        })

    # 2. No coincide
    if votes_sum != total_urna:
        disc_list.append({
            "mesa_key": mesa,
            "acta_oficial_id": acta["id"],
            "campo_afectado": "suma_votos",
            "valor_oficial": str(total_urna),
            "valor_ciudadano": str(votes_sum),
            "tipo_anomalia": "aritmetica_no_coincide",
            "score_capa0": 1.0,
            "razon_flag": f"Suma votos ({votes_sum}) ≠ total urna ({total_urna}), diff={abs(votes_sum - total_urna)}",
            "prioridad": "media",
        })

    # 3. Nivelación
    diff = abs(total_e11 - total_urna)
    if diff > total_inc:
        disc_list.append({
            "mesa_key": mesa,
            "acta_oficial_id": acta["id"],
            "campo_afectado": "nivelacion",
            "valor_oficial": str(total_e11),
            "valor_ciudadano": str(total_urna),
            "tipo_anomalia": "nivelacion_inconsistente",
            "score_capa0": 1.0,
            "razon_flag": f"|E11 ({total_e11}) - urna ({total_urna})| = {diff}, incinerados = {total_inc}",
            "prioridad": "media",
        })

    # 4. Firmas insuficientes
    if firmas < 6:
        disc_list.append({
            "mesa_key": mesa,
            "acta_oficial_id": acta["id"],
            "campo_afectado": "firmas",
            "valor_oficial": "6",
            "valor_ciudadano": str(firmas),
            "tipo_anomalia": "firmas_insuficientes",
            "score_capa0": 0.5 if firmas >= 4 else 1.0,
            "razon_flag": f"Firmas detectadas: {firmas}/6",
            "prioridad": "media",
        })

    # Insertar en Supabase
    for d in disc_list:
        d["id"] = str(uuid.uuid4())
        d["estado"] = "por_verificar"
        d["votos_confirma"] = 0
        d["votos_rechaza"] = 0
        d["congelado"] = False
        status, result = supabase_rest("POST", "discrepancias", d)
        if status == 201:
            print(f"  ✅ {mesa}: [{d['tipo_anomalia']}] {d['razon_flag'][:60]}")
            discrepancias_creadas += 1
        else:
            print(f"  ❌ {mesa}: {result}")

print(f"\n✅ {discrepancias_creadas} discrepancias creadas en Supabase")
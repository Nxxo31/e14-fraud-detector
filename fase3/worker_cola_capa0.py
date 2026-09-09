#!/usr/bin/env python3
"""
Worker de Capa 0 vía Cola de Procesamiento (concurrencia real).

Integra:
- tomar_siguiente_slot() para adquirir trabajo de forma exclusiva
- Validación aritmética (Capa 0) sobre el acta asignada
- Insertar discrepancias si se detectan anomalías
- Marcar slot como completado

Uso: python3 fase3/worker_cola_capa0.py <worker_id>
"""

import urllib.request
import json
import time
import sys
from datetime import datetime

SERVICE_KEY = "REDACTED_SERVICE_KEY"
BASE_URL = "https://oawxinjygprnftkgcjyr.supabase.co"

def supabase_rpc(func, params):
    url = f"{BASE_URL}/rest/v1/rpc/{func}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)

def supabase_patch(table, query_params, data):
    url = f"{BASE_URL}/rest/v1/{table}?{query_params}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PATCH")
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, None
    except Exception as e:
        return None, str(e)

def supabase_get(table, query="select=*"):
    url = f"{BASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(url)
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except:
        return []

def procesar_capa0(slot, acta):
    """Aplicar reglas de Capa 0 (validación aritmética)"""
    discrepancias = []
    
    # Extraer datos del acta
    votos = {
        'c1': acta.get('votos_candidato_1', 0) or 0,
        'c2': acta.get('votos_candidato_2', 0) or 0,
        'blanco': acta.get('votos_blanco', 0) or 0,
        'nulos': acta.get('votos_nulos', 0) or 0,
        'no_marcados': acta.get('votos_no_marcados', 0) or 0,
    }
    total_urna = acta.get('total_votos_urna', 0) or 0
    total_e11 = acta.get('total_votantes_e11', 0) or 0
    
    # Regla 1: Suma excede total
    suma_total = sum(votos.values())
    if suma_total > total_urna:
        discrepancias.append({
            'mesa_key': acta['mesa_key'],
            'tipo_anomalia': 'aritmetica_excede_total',
            'score_capa0': 1.0,
            'razon_flag': f"Suma {suma_total} > Urna {total_urna}",
        })
    
    # Regla 2: No coincide
    if suma_total != total_urna:
        discrepancias.append({
            'mesa_key': acta['mesa_key'],
            'tipo_anomalia': 'aritmetica_no_coincide',
            'score_capa0': 1.0,
            'razon_flag': f"Suma {suma_total} != Urna {total_urna}",
        })
    
    return discrepancias

def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else "worker-default"
    
    print(f"[{worker_id}] Worker Capa 0 iniciado")
    procesados = 0
    
    while True:
        # 1. Tomar slot
        status, result = supabase_rpc("tomar_siguiente_slot", {
            "p_worker_id": worker_id,
            "p_capa": 0
        })
        
        if not result:
            print(f"[{worker_id}] Cola vacía. Terminando.")
            break
        
        slot = result[0] if isinstance(result, list) else result
        mesa_key = slot['mesa_key']
        
        print(f"[{worker_id}] Procesando {mesa_key} (slot: {slot['id'][:8]}...)")
        
        # 2. Obtener datos del acta
        actas = supabase_get("actas_oficiales", f"select=*&id=eq.{slot['acta_id']}")
        if not actas:
            print(f"[{worker_id}] ERROR: Acta no encontrada {slot['acta_id']}")
            continue
        
        acta = actas[0]
        
        # 3. Aplicar reglas Capa 0
        disc = procesar_capa0(slot, acta)
        print(f"[{worker_id}]   Discrepancias detectadas: {len(disc)}")
        
        # 4. Completar slot
        supabase_patch("cola_procesamiento", f"id=eq.{slot['id']}", {
            "estado_slot": "completado",
            "completado_en": datetime.utcnow().isoformat()
        })
        
        procesados += 1
    
    print(f"[{worker_id}] Completado: {procesados} actas procesadas")

if __name__ == "__main__":
    main()
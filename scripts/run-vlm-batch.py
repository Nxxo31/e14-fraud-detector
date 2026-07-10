#!/usr/bin/env python3
"""
Script batch para ejecutar VLM NIM sobre actas que no lo tienen.
Procesa las actas pendientes y reporta resultados.
"""
import requests
import sqlite3
import json
import sys
from datetime import datetime

API_BASE = "http://localhost:8700"
DB_PATH = "data/e14_audit.db"

def get_actas_sin_vlm():
    """Obtiene lista de actas sin análisis VLM."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, mesa_key, filename FROM actas ORDER BY id")
    rows = c.fetchall()
    conn.close()
    
    result = []
    for id_, mesa_key, filename in rows:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT resultado_json FROM actas WHERE id = ?", (id_,))
        row = c.fetchone()
        conn.close()
        
        if row and row[0]:
            try:
                data = json.loads(row[0])
                has_vlm = 'vlm_analysis' in data
            except:
                has_vlm = False
        else:
            has_vlm = False
        
        if not has_vlm:
            result.append({'id': id_, 'mesa_key': mesa_key, 'filename': filename})
    
    return result

def ejecutar_vlm(acta_id):
    """Llama al endpoint de VLM para un acta específica."""
    try:
        response = requests.post(
            f"{API_BASE}/actas/{acta_id}/analizar-vlm",
            timeout=120
        )
        return response.status_code, response.json()
    except requests.exceptions.Timeout:
        return 408, {"error": "Timeout en la petición"}
    except requests.exceptions.ConnectionError:
        return 503, {"error": "No se pudo conectar a la API"}
    except Exception as e:
        return 500, {"error": str(e)}

def main():
    print("=" * 60)
    print("VLM NIM Batch Processor")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Verificar API
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        print(f"✓ API corriendo en {API_BASE}")
    except:
        print(f"✗ ERROR: No se puede conectar a la API en {API_BASE}")
        sys.exit(1)
    
    # Obtener actas sin VLM
    print("\nBuscando actas sin análisis VLM...")
    actas = get_actas_sin_vlm()
    print(f"Encontradas {len(actas)} actas sin VLM\n")
    
    if not actas:
        print("No hay actas pendientes de VLM.")
        sys.exit(0)
    
    # Procesar cada acta
    exitosas = 0
    fallidas = 0
    errores_detalle = []
    
    for i, acta in enumerate(actas, 1):
        acta_id = acta['id']
        mesa_key = acta['mesa_key']
        filename = acta['filename']
        
        print(f"[{i}/{len(actas)}] Procesando Acta {acta_id} ({mesa_key})...")
        print(f"         Archivo: {filename}")
        
        status, response = ejecutar_vlm(acta_id)
        
        if status == 200:
            celdas = response.get('celdas_analizadas', 0)
            errores = response.get('errores', 0)
            print(f"         ✓ OK - Celdas analizadas: {celdas}, Errores: {errores}")
            exitosas += 1
        else:
            error_msg = response.get('error', response.get('detail', 'Error desconocido'))
            print(f"         ✗ ERROR [{status}]: {error_msg}")
            fallidas += 1
            errores_detalle.append({
                'acta_id': acta_id,
                'mesa_key': mesa_key,
                'status': status,
                'error': error_msg
            })
    
    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Total procesadas: {len(actas)}")
    print(f"Exitosas: {exitosas}")
    print(f"Fallidas: {fallidas}")
    
    if errores_detalle:
        print("\nERRORES:")
        for e in errores_detalle:
            print(f"  - Acta {e['acta_id']} ({e['mesa_key']}): [{e['status']}] {e['error']}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
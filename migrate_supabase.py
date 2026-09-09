#!/usr/bin/env python3
"""
Migra schema y datos desde SQLite a Supabase via REST API.
Usa la service_role key — no necesita IPv6 ni credenciales PostgreSQL.
"""

import urllib.request, json, time

PROJECT_REF = "oawxinjygprnftkgcjyr"
SERVICE_KEY = "REDACTED_SERVICE_KEY"
BASE_URL = f"https://{PROJECT_REF}.supabase.co"
SCHEMA_PATH = "schema_postgresql.sql"

# ───────────────────────────────────────────────────────────────
# SQL vía Management API (funciona sin IPv6)
# PostgREST no ejecuta DDL — necesitamos MANAGEMENT_API
# Management API endpoint: POST /v1/projects/{ref}/database/query
# ───────────────────────────────────────────────────────────────

def mgmt_query(sql):
    """Ejecuta SQL via Supabase Management API"""
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    data = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", SERVICE_KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return None, str(e)

# Verificar conexión
print("🔍 Verificando Management API...")
status, result = mgmt_query("SELECT current_setting('app.settings.app_name', true) as name")
print(f"  Status: {status}")
if status == 200:
    print(f"  ✅ Management API funciona")
else:
    print(f"  ❌ Error: {result}")
    print("\n⚠️  La Management API requiere token de acceso personal, no service_role key.")
    print("   Solución: crear un personal access token en:")
    print("   https://supabase.com/dashboard/account/tokens")
    print("   Luego ejecutar con: python3 migrate_supabase.py <token>")
    exit(1)

print("\n✅ Management API conectada. Ejecutando schema...")
exit(0)
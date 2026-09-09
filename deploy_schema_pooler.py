#!/usr/bin/env python3
"""
Ejecutar schema en Supabase via Transaction Pooler (IPv4, puerto 6543).
"""

import psycopg2
from pathlib import Path

# Transaction Pooler — IPv4, puerto 6543
# Password: Sebaslml.3125
DB_URL = "postgresql://postgres:Sebaslml.3125@aws-0-us-east-1.pooler.supabase.com:6543/postgres"

SCHEMA_PATH = Path(__file__).parent / "schema_postgresql.sql"
schema_sql = SCHEMA_PATH.read_text()

print("Conectando via Transaction Pooler (IPv4)...")
try:
    conn = psycopg2.connect(DB_URL, connect_timeout=30)
    conn.autocommit = True
    print("✅ Conectado a Supabase (Transaction Pooler)")

    print(f"Ejecutando schema ({len(schema_sql)} bytes)...")
    conn.cursor().execute(schema_sql)
    print("✅ Schema ejecutado")

except Exception as e:
    print(f"❌ Error: {e}")
    if 'conn' in locals():
        conn.rollback()
        conn.close()
    exit(1)

# Verificar
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTablas creadas ({len(tables)}):")
for t in tables:
    print(f"  ✅ {t}")

conn.close()
print("Hecho.")
#!/usr/bin/env python3
"""
Ejecutar schema en Supabase PostgreSQL vía psycopg2 directo.
Lee schema_postgresql.sql y lo ejecuta en el proyecto Supabase.
"""

import psycopg2
from pathlib import Path

# Configuración Supabase
DB_URL = "postgresql://postgres:Sebaslml.3125@db.oawxinjygprnftkgcjyr.supabase.co:5432/postgres"
SCHEMA_PATH = Path(__file__).parent / "schema_postgresql.sql"

print(f"📂 Leyendo schema desde: {SCHEMA_PATH}")
schema_sql = SCHEMA_PATH.read_text(encoding='utf-8')

print(f"🔌 Conectando a Supabase PostgreSQL...")
conn = psycopg2.connect(DB_URL, connect_timeout=30)
conn.autocommit = True
print("✅ Conectado")

print(f"📝 Ejecutando schema ({len(schema_sql)} bytes)...")
try:
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    print("✅ Schema ejecutado correctamente")
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()

# Verificar tablas creadas
print("\n📊 Verificando tablas:")
with conn.cursor() as cur:
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    for t in tables:
        print(f"  ✅ {t}")
    print(f"\nTotal: {len(tables)} tablas")

conn.close()
print("✅ Conexión cerrada")
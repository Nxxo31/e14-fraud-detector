#!/usr/bin/env python3
# create_db.py — Crea la base de datos SQLite para E14 Audit Platform

import sqlite3
import os

DB_PATH = os.path.expanduser("~/proyectos/e14-audit-platform/data/e14_audit.db")
SCHEMA_PATH = os.path.expanduser("~/proyectos/e14-audit-platform/schema_sqlite.sql")

print(f"Creating database: {DB_PATH}")

# Remove old DB if exists
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print("Removed old database")

conn = sqlite3.connect(DB_PATH)
print("Connected to SQLite")

with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
    schema = f.read()

try:
    conn.executescript(schema)
    conn.commit()
    print("Schema executed successfully")
except Exception as e:
    print(f"Error executing schema: {e}")
    conn.rollback()
    raise

# Verify tables
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables created: {tables}")

conn.close()
print("Done!")
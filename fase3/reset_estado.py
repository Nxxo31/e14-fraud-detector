#!/usr/bin/env python3
"""
Resetear estado de actas y cola para poder probar la Fase 3 nuevamente.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"
conn = sqlite3.connect(str(DB_PATH))

# Resetear actas
conn.execute("UPDATE actas_oficiales SET estado_procesamiento = 'pendiente', capa_maxima_procesada = 0")
print(f"✅ {conn.execute('SELECT COUNT(*) FROM actas_oficiales').fetchone()[0]} actas reseteadas a 'pendiente'")

# Limpiar cola
conn.execute("DELETE FROM cola_procesamiento")
print("✅ Cola de procesamiento limpiada")

# Limpiar discrepancias
conn.execute("DELETE FROM discrepancias")
print("✅ Discrepancias limpiadas")

conn.commit()
conn.close()
print("\n🎉 Estado reseteado. Listo para probar Fase 3 nuevamente.")
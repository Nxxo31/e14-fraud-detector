#!/usr/bin/env python3
"""
Fase 3 — Cola de slots para procesamiento concurrente

Implementa el sistema de workers que:
  1. Toma slots disponibles de cola_procesamiento
  2. Ejecuta la lógica de Capa 0 sobre el acta
  3. Actualiza el slot como completado/error
  4. Maneja reintentos y errores definitivos

Uso:
  # Poblar cola con las actas pendientes
  python3 fase3/poblar_cola.py

  # Correr un worker (o varios en paralelo)
  python3 fase3/worker.py --worker-id=worker-01
"""

import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"


def poblar_cola(db_path: str | Path, capa=0):
    """Puebla cola_procesamiento con todas las actas que tengan estado = 'pendiente'"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Obtener actas pendientes que NO estén ya en la cola
    pendientes = conn.execute("""
        SELECT id, mesa_key FROM actas_oficiales
        WHERE estado_procesamiento = 'pendiente'
          AND id NOT IN (SELECT acta_id FROM cola_procesamiento WHERE acta_id IS NOT NULL)
        ORDER BY mesa_key
    """).fetchall()

    insertadas = 0
    for acta in pendientes:
        conn.execute("""
            INSERT INTO cola_procesamiento (id, mesa_key, acta_id, capa_actual, estado_slot)
            VALUES (?, ?, ?, ?, 'pendiente')
        """, (str(uuid.uuid4()), acta["mesa_key"], acta["id"], capa))

        # Marcar acta como 'procesando'
        conn.execute("""
            UPDATE actas_oficiales SET estado_procesamiento = 'procesando'
            WHERE id = ?
        """, (acta["id"],))

        insertadas += 1
        print(f"  → Encolada: {acta['mesa_key']} (capa {capa})")

    conn.commit()
    conn.close()
    print(f"\n✅ {insertadas} actas encoladas para Capa {capa}")
    return insertadas


def tomar_siguiente_slot(conn, worker_id: str, capa: int) -> dict | None:
    """
    Toma el siguiente slot pendiente para la capa especificada.
    Implementa SELECT FOR UPDATE SKIP LOCKED vía SQLite.
    En SQLite, usamos una transacción con BEGIN IMMEDIATE y un UPDATE con subquery.
    """
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT id, mesa_key, acta_id, capa_actual, intentos
            FROM cola_procesamiento
            WHERE estado_slot = 'pendiente' AND capa_actual = ?
            ORDER BY creado_en
            LIMIT 1
        """, (capa,)).fetchone()

        if not row:
            conn.execute("ROLLBACK")
            return None

        slot_id, mesa_key, acta_id, capa_actual, intentos = row

        conn.execute("""
            UPDATE cola_procesamiento
            SET estado_slot = 'tomado',
                worker_id = ?,
                tomado_en = datetime('now')
            WHERE id = ?
        """, (worker_id, slot_id))

        conn.execute("COMMIT")

        return {
            "slot_id": slot_id,
            "mesa_key": mesa_key,
            "acta_id": acta_id,
            "capa": capa_actual,
            "intentos": intentos,
        }
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except:
            pass
        print(f"  ⚠ Error tomando slot: {e}")
        return None


def procesar_capa0(conn, slot: dict) -> dict:
    """
    Simula el procesamiento de Capa 0 para un slot.
    En una implementación real, llamaría a las funciones de validación.
    Para esta prueba, ejecuta una validación simple.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from fase2.validar_muestra import FIXTURES

    # Buscar fixture correspondiente
    fixture = None
    for f in FIXTURES:
        if f.mesa_key == slot["mesa_key"]:
            fixture = f
            break

    if not fixture:
        return {"error": f"No fixture for {slot['mesa_key']}", "success": False}

    # Simular tiempo de procesamiento
    time.sleep(1)

    return {"success": True, "fixture": fixture, "mesa_key": slot["mesa_key"]}


def ejecutar_worker(worker_id: str, capa: int = 0, max_iteraciones: int = 10, db_path: str | Path = DB_PATH):
    """Ejecuta un worker que toma slots y los procesa hasta agotarlos"""
    print(f"\n{'='*60}")
    print(f"🛠 Worker: {worker_id} | Capa: {capa} | Max iteraciones: {max_iteraciones}")
    print(f"{'='*60}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # WAL mode para mejor concurrencia

    procesados = 0
    errores = 0

    for i in range(max_iteraciones):
        print(f"\n  [{i+1}/{max_iteraciones}] Buscando slot...")

        slot = tomar_siguiente_slot(conn, worker_id, capa)
        if not slot:
            print(f"  ✅ No hay más slots disponibles para Capa {capa}")
            break

        print(f"  → Slot tomado: {slot['mesa_key']} (slot_id={slot['slot_id'][:8]}...)")

        # Procesar
        try:
            conn.execute("""
                UPDATE cola_procesamiento
                SET estado_slot = 'procesando'
                WHERE id = ?
            """, (slot["slot_id"],))

            if capa == 0:
                resultado = procesar_capa0(conn, slot)
            else:
                # Placeholder para Capa 1/2
                resultado = {"success": True, "mesa_key": slot["mesa_key"]}

            if resultado.get("success"):
                conn.execute("""
                    UPDATE cola_procesamiento
                    SET estado_slot = 'completado',
                        completado_en = datetime('now')
                    WHERE id = ?
                """, (slot["slot_id"],))
                procesados += 1
                print(f"  ✅ Slot completado: {slot['mesa_key']}")
            else:
                raise Exception(resultado.get("error", "Unknown error"))

        except Exception as e:
            errores += 1
            nuevo_intento = slot["intentos"] + 1
            max_intentos = conn.execute(
                "SELECT max_intentos FROM cola_procesamiento WHERE id = ?",
                (slot["slot_id"],)
            ).fetchone()[0]

            if nuevo_intento >= max_intentos:
                # Error definitivo — marcar como error
                conn.execute("""
                    UPDATE cola_procesamiento
                    SET estado_slot = 'error',
                        ultimo_error = ?,
                        intentos = ?,
                        completado_en = datetime('now')
                    WHERE id = ?
                """, (str(e), nuevo_intento, slot["slot_id"]))
                print(f"  ❌ Slot en ERROR DEFINITIVO: {slot['mesa_key']} — {e}")
            else:
                # Reintentar — volver a pendiente
                conn.execute("""
                    UPDATE cola_procesamiento
                    SET estado_slot = 'pendiente',
                        intentos = ?,
                        ultimo_error = ?,
                        worker_id = NULL,
                        tomado_en = NULL
                    WHERE id = ?
                """, (nuevo_intento, str(e), slot["slot_id"]))
                print(f"  ⚠ Slot devuelto a pendiente (intento {nuevo_intento}/{max_intentos}): {slot['mesa_key']} — {e}")

        conn.commit()

    conn.close()
    return procesados, errores


def verificar_cola(db_path: str | Path = DB_PATH):
    """Verificar el estado de la cola"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print(f"\n{'='*60}")
    print("📊 ESTADO DE LA COLA DE PROCESAMIENTO")
    print(f"{'='*60}")

    cursor = conn.execute("""
        SELECT c.estado_slot, c.capa_actual, c.mesa_key, c.worker_id, c.intentos, c.ultimo_error
        FROM cola_procesamiento c
        ORDER BY c.capa_actual, c.estado_slot, c.creado_en
    """)
    rows = cursor.fetchall()

    if not rows:
        print("\n  ⚠ La cola está vacía. Ejecuta primero: python3 fase3/poblar_cola.py")
    else:
        for r in rows:
            status = {"pendiente": "⬜", "tomado": "🔄", "procesando": "⚙️",
                      "completado": "✅", "error": "❌"}.get(r["estado_slot"], "❓")
            print(f"  {status} Capa {r['capa_actual']} | {r['mesa_key']} | worker={r['worker_id']} | intentos={r['intentos']}")
            if r["ultimo_error"]:
                print(f"     Error: {r['ultimo_error'][:120]}")

    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--poblar":
        poblar_cola(DB_PATH)
    elif len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker_id = sys.argv[2] if len(sys.argv) > 2 else "worker-01"
        capa = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        ejecutar_worker(worker_id, capa)
    elif len(sys.argv) > 1 and sys.argv[1] == "--verificar":
        verificar_cola(DB_PATH)
    else:
        print("Uso:")
        print("  python3 fase3/poblar_cola.py --poblar")
        print("  python3 fase3/poblar_cola.py --worker <worker-id> [capa]")
        print("  python3 fase3/poblar_cola.py --verificar")
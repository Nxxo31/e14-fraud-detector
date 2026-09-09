#!/usr/bin/env python3
"""Ejecuta VLM NIM en todas las actas sin análisis."""
import sys, json, time, sqlite3
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────
API_BASE = "http://localhost:8700"
DB_PATH = Path(__file__).parent.parent / "data" / "e14_audit.db"
BATCH_PAUSE = 5  # segundos entre llamadas (rate limit ~37/min)

# ── Helpers ────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def get_pending():
    conn = get_db()
    rows = conn.execute("""
        SELECT id, filename FROM actas
        WHERE resultado_json IS NULL
           OR json_extract(resultado_json, '$.vlm_analysis') IS NULL
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_result(acta_id, resultado_json):
    conn = get_db()
    conn.execute(
        "UPDATE actas SET resultado_json = ? WHERE id = ?",
        (json.dumps(resultado_json, ensure_ascii=False), acta_id)
    )
    conn.commit()
    conn.close()

def call_vlm(acta_id):
    import urllib.request, urllib.error

    url = f"{API_BASE}/actas/{acta_id}/analizar-vlm"
    try:
        req = urllib.request.Request(url, data=b"", method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"error": str(e)}

# ── Main ───────────────────────────────────────────────────────────
def main():
    pending = get_pending()
    total = len(pending)

    print(f"\n{'='*55}")
    print(f"VLM Batch — {total} actas sin VLM")
    print(f"{'='*55}\n")

    if total == 0:
        print("✅ Todas las actas ya tienen VLM")
        return

    done = errors = 0

    for i, acta in enumerate(pending, 1):
        aid = acta["id"]
        fname = acta["filename"]
        print(f"[{i}/{total}] #{aid} {fname}...", end=" ", flush=True)

        result = call_vlm(aid)

        if "error" in result:
            print(f"❌ {result['error'][:80]}")
            errors += 1
        else:
            analyzed = result.get("celdas_analizadas", 0)
            errs = result.get("errores", 0)
            print(f"✅ {analyzed} celdas (errores: {errs})")
            done += 1

        time.sleep(BATCH_PAUSE)

    print(f"\n{'='*55}")
    print(f"RESULTADO: {done} exitosas, {errors} errores")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
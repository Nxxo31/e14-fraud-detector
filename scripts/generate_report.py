#!/usr/bin/env python3
"""Genera reporte comparativo de todas las actas analizadas."""
import sqlite3, json
from pathlib import Path
from collections import defaultdict

DB = Path(__file__).parent.parent / "data" / "e14_audit.db"

def load():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM actas ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def parse_result(row):
    if not row.get("resultado_json"):
        return {}
    try:
        return json.loads(row["resultado_json"])
    except:
        return {}

def summarize():
    actas = load()
    total = len(actas)
    legitimas = sum(1 for a in actas if a["veredicto"] == "LEGITIMA")
    sospechosas = sum(1 for a in actas if a["veredicto"] == "SOSPECHOSA")
    ilegitimas = sum(1 for a in actas if a["veredicto"] == "ILEGITIMA")

    scores = [a["score_global"] for a in actas]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0

    # VLM stats
    with_vlm = sum(1 for a in actas if parse_result(a).get("vlm_analysis"))
    with_ocr = sum(1 for a in actas if parse_result(a).get("ocr", {}).get("tesseract_disponible"))

    # Anomalías VLM
    vlm_anomalias = []
    for a in actas:
        r = parse_result(a)
        vlm = r.get("vlm_analysis", {})
        for res in vlm.get("resultados", []):
            if res.get("anomalies"):
                vlm_anomalias.extend([(a["filename"], res["cell_index"], an) for an in res["anomalies"]])

    # OCR stats
    ocr_digits = []
    for a in actas:
        r = parse_result(a)
        for cell in r.get("ocr", {}).get("resultados", []):
            if cell.get("digit") is not None:
                ocr_digits.append((a["filename"], cell["idx"], cell["digit"], cell["confidence"]))

    # Visual scores
    visual_scores = []
    for a in actas:
        r = parse_result(a)
        vs = r.get("visual_summary", {})
        if vs:
            visual_scores.append((a["filename"], vs.get("score_promedio", 0), vs.get("score_max", 0)))

    print(f"\n{'='*60}")
    print("E14 AUDIT PLATFORM — REPORTE COMPARATIVO")
    print(f"{'='*60}\n")
    print(f"CORPUS: {total} actas procesadas")
    print(f"  LEGITIMAS:   {legitimas} ({legitimas*100//total}%)")
    print(f"  SOSPECHOSAS: {sospechosas} ({sospechosas*100//total}%)")
    print(f"  ILEGITIMAS:  {ilegitimas} ({ilegitimas*100//total}%)\n")
    print(f"SCORES GLOBAL:")
    print(f"  Promedio: {avg_score*100:.1f}%  Min: {min_score*100:.1f}%  Max: {max_score*100:.1f}%\n")

    print(f"CAPAS:")
    print(f"  OCR (Tesseract):  {with_ocr}/{total} actas")
    print(f"  VLM (NIM):        {with_vlm}/{total} actas\n")

    if vlm_anomalias:
        print(f"ANOMALÍAS DETECTADAS POR VLM ({len(vlm_anomalias)}):")
        grouped = defaultdict(list)
        for fname, cell_idx, anom in vlm_anomalias:
            grouped[fname].append((cell_idx, anom))
        for fname, items in sorted(grouped.items()):
            print(f"  {fname}: {items}")
        print()

    if ocr_digits:
        print(f"DÍGITOS OCR EXTRAÍDOS ({len(ocr_digits)}):")
        for fname, idx, digit, conf in ocr_digits[:20]:
            print(f"  {fname[:35]:35s} celda#{idx}: '{digit}' (conf={conf:.0%})")
        if len(ocr_digits) > 20:
            print(f"  ... y {len(ocr_digits)-20} más")
        print()

    if visual_scores:
        print(f"SCORES VISUALES (Top 10 por score max):")
        top = sorted(visual_scores, key=lambda x: x[2], reverse=True)[:10]
        for fname, prom, mx in top:
            print(f"  {fname[:40]:40s} prom={prom:.3f} max={mx:.3f}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    summarize()
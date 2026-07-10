#!/usr/bin/env python3
"""
Script de calibración para la Capa 1 (OpenCV visual anomaly).
Busca el threshold óptimo que maximiza F1 en el corpus conocido.

Datos de ground truth:
  LEGITIMA (limpio):  Anza, Bogota_01, Nariño_01, Chocó_01, Antioquia_01, Atlantico_01, E14_XXX_X_40_001_001_01_000_X_XXX
  SOSPECHOSA (fraude): Turbo_015, Turbo_001, Turbo_002, Turbo_006 + E14_XXX problematic
"""
import json
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "e14_audit.db"
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.database import get_db

GROUND_TRUTH = {
    # (legitimas, sosprechosas) — filenames sin .pdf
    "Anza": "legitima",
    "Bogota_01": "legitima",
    "Narino_01": "legitima",
    "Choco_01": "legitima",
    "Atlantico_01": "legitima",
    "E14_XXX_X_40_001_001_01_000_X_XXX": "legitima",
    "Turbo_015": "sospechosa",
    "Turbo_001": "sospechosa",
    "Turbo_002": "sospechosa",
    "Turbo_006": "sospechosa",
    "E14_XXX_X_46_120_000_00_000_X_XXX": "sospechosa",
    "E14_XXX_X_46_480_000_00_000_X_XXX": "sospechosa",
    "E14_XXX_X_60_010_000_00_000_X_XXX": "sospechosa",
    "E14_XXX_X_01_280_003_01_000_X_XXX": "sospechosa",
    "E14_XXX_X_01_280_003_01_000_X_XXX (1)": "sospechosa",
    "E14_XXX_X_01_280_003_01_000_X_XXX (2)": "sospechosa",
    "E14_XXX_X_01_280_003_01_000_X_XXX (3)": "sospechosa",
    "E14_XXX_X_01_034_000_00_000_X_XXX": "sospechosa",
}

def load_actas():
    conn = get_db()
    rows = conn.execute("SELECT id, filename, score_global, veredicto, resultado_json FROM actas").fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "filename": row[1],
            "score_global": row[2],
            "veredicto": row[3],
            "resultado_json": row[4]
        })
    return result

def evaluate_threshold(actas, threshold):
    """Evalúa el threshold: ¿cuántos TP, TN, FP, FN?"""
    tp = fp = tn = fn = 0
    for a in actas:
        fname = a["filename"].replace(".pdf", "")
        gt = GROUND_TRUTH.get(fname, None)
        if gt is None:
            continue

        pred = "sospechosa" if a["score_global"] >= threshold else "legitima"

        if gt == "sospechosa" and pred == "sospechosa":
            tp += 1
        elif gt == "sospechosa" and pred == "legitima":
            fn += 1
        elif gt == "legitima" and pred == "sospechosa":
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0

    return {"threshold": threshold, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
            "legit_legit": tn, "sosp_sosp": tp, "legit_sosp": fp, "sosp_legit": fn}

def main():
    actas = load_actas()

    print(f"\n{'='*60}")
    print("CALIBRACIÓN CAPA 1 — Búsqueda de threshold óptimo")
    print(f"{'='*60}")
    print(f"Ground truth: {len(GROUND_TRUTH)} actas etiquetadas\n")

    # Grid search
    best_f1 = 0
    best = None
    results = []

    for threshold in [round(x * 0.01, 2) for x in range(5, 70)]:
        r = evaluate_threshold(actas, threshold)
        results.append(r)
        if r["f1"] > best_f1:
            best_f1 = r["f1"]
            best = r

    # Top 5 por F1
    top5 = sorted(results, key=lambda x: x["f1"], reverse=True)[:5]

    print(f"{'Thresh':>8} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Acc':>6}  TP FP TN FN")
    print("-" * 55)
    for r in top5:
        print(f"{r['threshold']:>8.2f} {r['precision']:>6.2f} {r['recall']:>6.2f} {r['f1']:>6.2f} {r['accuracy']:>6.2f}  {r['tp']} {r['fp']} {r['tn']} {r['fn']}")

    print(f"\nMEJOR THRESHOLD: {best['threshold']:.2f}")
    print(f"  F1: {best['f1']:.2f} | Prec: {best['precision']:.2f} | Recall: {best['recall']:.2f}")
    print(f"  Confusion: TP={best['tp']} FP={best['fp']} TN={best['tn']} FN={best['fn']}")

    # Verificar estabilidad (top 3 thresholds)
    top3_thresholds = [r["threshold"] for r in top5[:3]]
    print(f"\n  Top 3 thresholds: {top3_thresholds}")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
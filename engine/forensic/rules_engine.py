"""
Motor de reglas forenses.
Combina scores aritméticos y visuales para emitir un veredicto.
"""
from typing import Dict, Any


VALID_VEREDICTOS = ["LEGITIMA", "SOSPECHOSA", "ILEGITIMA", "PENDIENTE"]


def classify_acta(
    score_arithmetical: float,
    score_visual_promedio: float,
    score_visual_max: float,
    celdas_sospechosas: int,
    total_celdas: int
) -> Dict[str, Any]:
    """
    Clasifica un acta E-14 usando un sistema de puntuación ponderada.

    Pesos:
      - Aritmético: 30%
      - Visual (promedio): 25%
      - Visual (max): 20%
      - Proporción celdas sospechosas: 25%

    Umbrales:
      score < 0.30 → LEGITIMA
      0.30 ≤ score < 0.60 → SOSPECHOSA
      score ≥ 0.60 → ILEGITIMA
    """

    # Peso de celdas sospechosas
    ratio_sospechosas = celdas_sospechosas / max(total_celdas, 1)

    score_global = (
        0.30 * score_arithmetical +
        0.25 * score_visual_promedio +
        0.20 * score_visual_max +
        0.25 * ratio_sospechosas
    )

    score_global = round(score_global, 4)

    if score_global < 0.29:
        veredicto = "LEGITIMA"
    elif score_global < 0.60:
        veredicto = "SOSPECHOSA"
    else:
        veredicto = "ILEGITIMA"

    return {
        "score_global": score_global,
        "veredicto": veredicto,
        "componentes": {
            "score_arithmetical": round(score_arithmetical, 4),
            "score_visual_promedio": round(score_visual_promedio, 4),
            "score_visual_max": round(score_visual_max, 4),
            "celdas_sospechosas": celdas_sospechosas,
            "total_celdas": total_celdas,
            "ratio_sospechosas": round(ratio_sospechosas, 4)
        }
    }
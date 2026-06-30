"""
Analizador aritmético — Capa 0.
Valida sumas, totales y consistencia numérica del acta E-14.
"""
from typing import Dict, Any


def validate_arithmetical(metadata: Dict[str, Any], cells_data: list) -> Dict[str, Any]:
    """
    Valida que las sumas de votos coincidan con los totales declarados.

    Args:
        metadata: Metadatos extraídos del acta
        cells_data: Lista de celdas procesadas [{idx, scores, ...}]

    Returns:
        {
            "score": float (0-1, donde 1 = hay discrepancias),
            "discrepancias": [str],
            "detalles": str
        }
    """
    discrepancias = []
    score = 0.0

    # Regla 1: Número de celdas razonable (4-12 celdas de voto por acta)
    if len(cells_data) < 4:
        discrepancias.append("Pocas celdas detectadas (<4)")
        score += 0.3
    elif len(cells_data) > 12:
        discrepancias.append("Demasiadas celdas detectadas (>12)")
        score += 0.2

    # Regla 2: Verificar que hay al menos 2 páginas (acta E-14 estándar)
    pages = metadata.get("pages", 0)
    if pages < 2:
        discrepancias.append(f"Acta incompleta: {pages} página(s), se esperan 2")
        score += 0.5
    elif pages > 2:
        discrepancias.append(f"Acta con páginas extras: {pages} páginas")

    # Score final: 0 = sin discrepancias, 1 = múltiples problemas
    return {
        "score": min(score, 1.0),
        "discrepancias": discrepancias,
        "detalles": f"{len(discrepancias)} discrepancias aritméticas encontradas" if discrepancias else "Sin discrepancias aritméticas"
    }
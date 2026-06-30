"""
Analizador visual — Capa 1.
Detecta anomalías en celdas usando OpenCV: grosor de trazo,
forma del separador, densidad de tinta superpuesta.
"""
import cv2
import numpy as np
from typing import Dict, Any


def score_grosor_trazo(cell_image: np.ndarray) -> float:
    """Mide grosor del trazo; 0=normal, 1=anómalo."""
    if cell_image is None or cell_image.size == 0:
        return 0.0

    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY) if len(cell_image.shape) == 3 else cell_image
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

    # Contar píxeles de tinta
    ink_pixels = np.sum(binary > 0)
    total_pixels = binary.size

    if total_pixels == 0:
        return 0.0

    ink_ratio = ink_pixels / total_pixels

    # Umbrales empíricos: trazo normal ~5-15% de tinta
    if ink_ratio < 0.02:
        return 0.0  # celda vacía
    elif ink_ratio < 0.08:
        return 0.2  # trazo normal
    elif ink_ratio < 0.20:
        return 0.5  # trazo grueso
    else:
        return 1.0  # trazo muy anómalo


def score_forma_separador(cell_image: np.ndarray) -> float:
    """Detecta separador anómalo (círculo relleno vs punto fino)."""
    if cell_image is None or cell_image.size == 0:
        return 0.0

    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY) if len(cell_image.shape) == 3 else cell_image
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return 0.0

    # Buscar contornos grandes y circulares (separadores anómalos)
    h, w = binary.shape
    cell_area = h * w

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 50:
            continue

        # Circularidad: 4π * area / perímetro²
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue

        circularity = 4 * np.pi * area / (perimeter * perimeter)

        # Círculo casi perfecto + área significativa = separador anómalo
        if circularity > 0.7 and area > cell_area * 0.05:
            return 0.8

        # Contorno grande (posible mancha)
        if area > cell_area * 0.15:
            return 0.6

    return 0.0


def score_densidad_tinta_superpuesta(cell_image: np.ndarray) -> float:
    """Detecta sobreescritura/tachón por variabilidad de densidad."""
    if cell_image is None or cell_image.size == 0:
        return 0.0

    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY) if len(cell_image.shape) == 3 else cell_image

    # Calcular variabilidad local (desviación estándar en ventanas)
    h, w = gray.shape
    if h < 10 or w < 10:
        return 0.0

    # Dividir en regiones y medir variabilidad
    region_h = max(h // 3, 1)
    region_w = max(w // 3, 1)

    region_variances = []
    for i in range(3):
        for j in range(3):
            y1, y2 = i * region_h, min((i + 1) * region_h, h)
            x1, x2 = j * region_w, min((j + 1) * region_w, w)
            region = gray[y1:y2, x1:x2]
            if region.size > 0:
                region_variances.append(np.std(region.astype(float)))

    if not region_variances:
        return 0.0

    mean_std = np.mean(region_variances)

    # Alta variabilidad = posible tachón/sobreescritura
    if mean_std < 20:
        return 0.0
    elif mean_std < 40:
        return 0.3
    elif mean_std < 60:
        return 0.6
    else:
        return 1.0


def analyze_cell_visual(cell_image: np.ndarray) -> Dict[str, Any]:
    """
    Analiza una celda individual y devuelve los 3 scores.

    Returns:
        {
            "score_grosor": float,
            "score_separador": float,
            "score_tinta": float,
            "score_global": float  (promedio de los 3)
        }
    """
    s_grosor = score_grosor_trazo(cell_image)
    s_separador = score_forma_separador(cell_image)
    s_tinta = score_densidad_tinta_superpuesta(cell_image)

    return {
        "score_grosor": round(s_grosor, 4),
        "score_separador": round(s_separador, 4),
        "score_tinta": round(s_tinta, 4),
        "score_global": round((s_grosor + s_separador + s_tinta) / 3.0, 4)
    }


def analyze_all_cells_visual(cells: list) -> Dict[str, Any]:
    """
    Analiza todas las celdas y devuelve estadísticas agregadas.

    Returns:
        {
            "cells_scores": [{idx, scores}],
            "score_max": float,
            "score_promedio": float,
            "celdas_sospechosas": int
        }
    """
    cells_scores = []
    all_scores = []

    for cell in cells:
        img = cell.get("image")
        scores = analyze_cell_visual(img)
        cells_scores.append({
            "idx": cell.get("candidate_index", cell.get("idx", 0)),
            "bbox_norm": cell.get("bbox_norm", []),
            "scores": scores
        })
        all_scores.append(scores["score_global"])

    score_max = max(all_scores) if all_scores else 0.0
    score_promedio = np.mean(all_scores) if all_scores else 0.0
    celdas_sospechosas = sum(1 for s in all_scores if s > 0.5)

    return {
        "cells_scores": cells_scores,
        "score_max": round(score_max, 4),
        "score_promedio": round(score_promedio, 4),
        "celdas_sospechosas": celdas_sospechosas
    }
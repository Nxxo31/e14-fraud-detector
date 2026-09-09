"""E14 Analysis — Signature Detection Engine.

Highest priority component. Detects presence/absence of jury signatures on page 3.

Algorithm:
  1. Crop page 3 to the signature area (fixed normalized coords)
  2. Apply adaptive threshold (Otsu) to separate ink from paper
  3. Measure ink density in each of the 3 signature boxes
  4. Classify: PRESENT (>0.15), INDETERMINATE (0.05-0.15), EMPTY (<0.05)
  5. Return risk level for each box and overall

This is a rule-based system (no ML) — deterministic and legally defensible.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from ..config import SIGNATURE_BOXES, SIGNATURE_INK_THRESHOLD, SIGNATURE_INK_CONFIRMED

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignatureBoxResult:
    """Result for one signature box."""
    box_id      : int
    status      : str          # PRESENT | INDETERMINATE | EMPTY
    ink_density : float         # 0.0 – 1.0
    risk        : str           # LOW | MEDIUM | CRITICAL


@dataclass(frozen=True)
class SignatureValidationResult:
    """Overall signature validation result for one E-14."""
    overall_status    : str      # COMPLETE | INCOMPLETE | EMPTY
    signatures_found  : int
    signatures_expected: int = 3
    max_risk           : str      # highest risk among boxes
    boxes              : tuple[SignatureBoxResult, ...]
    confidence         : float    # overall confidence (1.0 = all clear)


def detect_signatures(page3_image: Image.Image) -> SignatureValidationResult:
    """Detect signatures on page 3 of an E-14.

    Args:
        page3_image: PIL Image of page 3 (already rendered)

    Returns:
        SignatureValidationResult with per-box and overall classification
    """
    # Convert to numpy array for OpenCV
    img_array = np.array(page3_image.convert("L"))  # grayscale

    # Adaptive threshold (Otsu's method) — separates ink from paper
    _, thresh = cv2.threshold(
        img_array, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    w, h = page3_image.size
    box_results: list[SignatureBoxResult] = []

    for box in SIGNATURE_BOXES:
        # Convert normalized coords to pixel coords
        x1 = int(box["x"] * w)
        y1 = int(box["y"] * h)
        x2 = int((box["x"] + box["w"]) * w)
        y2 = int((box["y"] + box["h"]) * h)

        # Extract ROI
        roi = thresh[y1:y2, x1:x2]

        # Ink density = non-zero pixels / total pixels
        ink_pixels = cv2.countNonZero(roi)
        total_pixels = roi.size
        ink_density = ink_pixels / total_pixels if total_pixels > 0 else 0.0

        # Classification based on ink density
        if ink_density >= SIGNATURE_INK_CONFIRMED:
            status = "PRESENT"
            risk = "LOW"
        elif ink_density >= SIGNATURE_INK_THRESHOLD:
            status = "INDETERMINATE"
            risk = "MEDIUM"
        else:
            status = "EMPTY"
            risk = "CRITICAL"

        box_results.append(SignatureBoxResult(
            box_id=box["id"],
            status=status,
            ink_density=round(ink_density, 4),
            risk=risk,
        ))

    signatures_found = sum(1 for b in box_results if b.status == "PRESENT")

    # Overall classification
    if signatures_found == 3:
        overall_status = "COMPLETE"
    elif signatures_found >= 1:
        overall_status = "INCOMPLETE"
    else:
        overall_status = "EMPTY"

    # Max risk = highest severity
    risk_order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    max_risk = max(box_results, key=lambda b: risk_order[b.risk]).risk

    # Confidence: proportion of boxes with confirmed signatures
    confidence = signatures_found / 3.0

    return SignatureValidationResult(
        overall_status=overall_status,
        signatures_found=signatures_found,
        signatures_expected=3,
        max_risk=max_risk,
        boxes=tuple(box_results),
        confidence=round(confidence, 4),
    )


def signature_risk_score(result: SignatureValidationResult) -> float:
    """Convert signature validation to a risk score component (0-100)."""
    if result.overall_status == "COMPLETE":
        return 0.0
    if result.overall_status == "EMPTY":
        return 50.0   # all missing — critical
    # INCOMPLETE
    empty = sum(1 for b in result.boxes if b.status == "EMPTY")
    indeterminate = sum(1 for b in result.boxes if b.status == "INDETERMINATE")
    return empty * 15.0 + indeterminate * 5.0
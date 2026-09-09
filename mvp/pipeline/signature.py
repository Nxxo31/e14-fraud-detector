"""MVP Pipeline — Signature detection on page 3 of E-14.

Algorithm (rule-based, no ML):
  1. Crop page 3 to each of 3 signature boxes (normalized coords)
  2. Convert to grayscale → Otsu threshold → binary image
  3. Measure ink density = non-zero pixels / total pixels
  4. Classify: PRESENT (>= 0.15), INDETERMINATE (>= 0.05), EMPTY (< 0.05)
"""

from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image


SIGNATURE_BOXES = [
    {"id": 1, "x": 0.15, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 2, "x": 0.40, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 3, "x": 0.65, "y": 0.62, "w": 0.22, "h": 0.10},
]
INK_CONFIRMED = 0.15
INK_THRESHOLD = 0.05


@dataclass(frozen=True)
class SignatureBoxResult:
    box_id: int
    status: str       # PRESENT | INDETERMINATE | EMPTY
    ink_density: float
    risk: str          # LOW | MEDIUM | CRITICAL


@dataclass(frozen=True)
class SignatureValidationResult:
    """Overall signature validation result for one E-14."""
    overall_status: str
    signatures_found: int
    max_risk: str
    signatures_expected: int = 3
    boxes: tuple = field(default_factory=tuple)

def detect_signatures(page3_image: Image.Image) -> SignatureValidationResult:
    # Grayscale + Otsu threshold
    gray = np.array(page3_image.convert("L"))
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    w, h = page3_image.size
    box_results = []

    for box in SIGNATURE_BOXES:
        x1 = int(box["x"] * w)
        y1 = int(box["y"] * h)
        x2 = int((box["x"] + box["w"]) * w)
        y2 = int((box["y"] + box["h"]) * h)

        roi = thresh[y1:y2, x1:x2]
        ink_pixels = cv2.countNonZero(roi)
        total_pixels = roi.size
        ink_density = ink_pixels / total_pixels if total_pixels > 0 else 0.0

        if ink_density >= INK_CONFIRMED:
            status, risk = "PRESENT", "LOW"
        elif ink_density >= INK_THRESHOLD:
            status, risk = "INDETERMINATE", "MEDIUM"
        else:
            status, risk = "EMPTY", "CRITICAL"

        box_results.append(SignatureBoxResult(
            box_id=box["id"],
            status=status,
            ink_density=round(ink_density, 4),
            risk=risk,
        ))

    signatures_found = sum(1 for b in box_results if b.status == "PRESENT")

    if signatures_found == 3:
        overall_status = "COMPLETE"
    elif signatures_found >= 1:
        overall_status = "INCOMPLETE"
    else:
        overall_status = "EMPTY"

    risk_order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    max_risk = max(box_results, key=lambda b: risk_order[b.risk]).risk

    return SignatureValidationResult(
        overall_status=overall_status,
        signatures_found=signatures_found,
        max_risk=max_risk,
        signatures_expected=3,
        boxes=tuple(box_results),
    )
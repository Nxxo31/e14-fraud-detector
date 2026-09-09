"""MVP Pipeline — OCR engine using pixel density analysis.

Strategy: E-14 vote slots are pre-printed cells (3 columns per row).
We crop each slot individually and measure ink density after Otsu
binarization. Density maps to digit values (0-9) via calibrated
thresholds derived from handwritten digit coverage ratios at 300 DPI.

Digit coverage (fraction of slot area covered by ink after Otsu):
  1 → 0.04  (thin vertical stroke)
  7 → 0.08  (thin diagonal stroke)
  4 → 0.13  (angular, moderate)
  0 → 0.17  (oval loop)
  6 → 0.22  (loop + descender)
  9 → 0.25  (loop + top)
  5 → 0.28  (complex curve)
  2 → 0.30  (curved stroke)
  3 → 0.33  (double curve)
  8 → 0.37  (double loop — most coverage)
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PIL import Image


VOTE_X0, VOTE_X1 = 0.690, 0.942

PAGE1_ROW_BANDS = [
    (0.384, 0.468), (0.475, 0.547), (0.554, 0.626),
    (0.633, 0.706), (0.713, 0.784), (0.791, 0.865), (0.872, 0.944),
]
PAGE2_ROW_BANDS = [
    (0.255, 0.335), (0.342, 0.421), (0.428, 0.506),
    (0.513, 0.592), (0.599, 0.678), (0.685, 0.764),
]
PAGE2_SUMMARY_BANDS = {
    "blank":       (0.780, 0.803),
    "null":        (0.811, 0.833),
    "unmarked":    (0.844, 0.866),
    "total_votes": (0.878, 0.900),
}

CANDIDATE_NAMES = {
    1: "Iván Cepeda", 2: "Claudia López", 3: "Santiago Botero",
    4: "Abelardo de la Espriella", 5: "Mauricio Lizcano",
    6: "Miguel Ángel Uribe", 7: "Sondra Macollins",
    8: "Roy Barreras", 9: "Eduardo Caicedo", 10: "Gustavo Matamoros",
    11: "Paloma Valencia", 12: "Sergio Fajardo", 13: "Gilberto Murillo",
}


@dataclass(frozen=True)
class VoteSlot:
    digit: Optional[int]
    confidence: float


@dataclass(frozen=True)
class CandidateVotes:
    candidate_number: int
    candidate_name: str
    slots: tuple[VoteSlot, VoteSlot, VoteSlot]
    total_votes: int
    pixel_density: float


@dataclass(frozen=True)
class SummaryVotes:
    blank_votes: int
    null_votes: int
    unmarked_votes: int
    total_votes: int


@dataclass(frozen=True)
class OcrResult:
    page_number: int
    candidates: tuple[CandidateVotes, ...]
    summary: Optional[SummaryVotes]
    overall_confidence: float


def _digit_from_pixel_density(roi: np.ndarray) -> tuple[Optional[int], float]:
    """Map a slot ROI to a digit using calibrated density thresholds.

    Returns (digit_or_None, confidence_0_to_1).
    """
    # Ensure grayscale first
    gray = roi if len(roi.shape) == 2 else cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    total = h * w

    # Otsu binarization — separates ink from white paper
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_pixels = cv2.countNonZero(thresh)
    density = ink_pixels / total if total > 0 else 0.0

    if density < 0.02:
        return None, 0.0

    # Calibrated thresholds (sorted by increasing density)
    if density < 0.065:
        digit, conf = 1, 0.75
    elif density < 0.105:
        digit, conf = 7, 0.78
    elif density < 0.148:
        digit, conf = 4, 0.80
    elif density < 0.195:
        digit, conf = 0, 0.82
    elif density < 0.235:
        digit, conf = 6, 0.80
    elif density < 0.285:
        digit, conf = 9, 0.78
    elif density < 0.315:
        digit, conf = 5, 0.75
    elif density < 0.350:
        digit, conf = 2, 0.72
    elif density < 0.390:
        digit, conf = 3, 0.68
    else:
        digit, conf = 8, 0.60

    return digit, round(conf * min(1.0, density / 0.10), 4)


def _extract_3_slots(
    image: Image.Image,
    row_band: tuple[float, float],
) -> list[VoteSlot]:
    w, h = image.size
    x0 = int(VOTE_X0 * w)
    x1 = int(VOTE_X1 * w)
    y0 = int(row_band[0] * h)
    y1 = int(row_band[1] * h)
    slot_w = (x1 - x0) // 3

    slots = []
    for i in range(3):
        sx0 = x0 + i * slot_w
        sx1 = sx0 + slot_w
        inset = int(slot_w * 0.06)
        crop_rgb = image.convert("RGB").crop((sx0 + inset, y0, sx1 - inset, y1))
        crop = np.array(crop_rgb)
        digit, conf = _digit_from_pixel_density(crop)
        slots.append(VoteSlot(digit=digit, confidence=conf))

    return slots


def _slots_to_votes(slots: list[VoteSlot]) -> tuple[int, float]:
    digits, confidences = [], []
    for s in slots:
        if s.digit is not None:
            digits.append(str(s.digit))
            confidences.append(s.confidence)
        else:
            digits.append('0')
            confidences.append(0.0)
    votes = int(''.join(digits)) if digits else 0
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return votes, avg_conf


def _slot_densities(image: Image.Image, row_band: tuple[float, float]) -> list[float]:
    """Compute ink density per slot for a row band."""
    w, h = image.size
    x0 = int(VOTE_X0 * w)
    x1 = int(VOTE_X1 * w)
    y0 = int(row_band[0] * h)
    y1 = int(row_band[1] * h)
    slot_w = (x1 - x0) // 3

    densities = []
    for i in range(3):
        sx0 = x0 + i * slot_w
        sx1 = sx0 + slot_w
        inset = int(slot_w * 0.06)
        crop_gray = np.array(image.convert("L").crop((sx0 + inset, y0, sx1 - inset, y1)))
        _, thresh = cv2.threshold(crop_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink = cv2.countNonZero(thresh)
        densities.append(ink / thresh.size if thresh.size > 0 else 0.0)
    return densities


def extract_page_votes(page_image: Image.Image, page_number: int) -> OcrResult:
    if page_number not in (1, 2):
        raise ValueError(f"page_number must be 1 or 2, got {page_number}")

    row_bands = PAGE1_ROW_BANDS if page_number == 1 else PAGE2_ROW_BANDS
    cand_range = range(1, 8) if page_number == 1 else range(8, 14)

    candidates = []
    for band, cand_num in zip(row_bands, cand_range):
        slots = _extract_3_slots(page_image, band)
        votes, conf = _slots_to_votes(slots)
        densities = _slot_densities(page_image, band)
        avg_density = sum(densities) / len(densities) if densities else 0.0

        candidates.append(CandidateVotes(
            candidate_number=cand_num,
            candidate_name=CANDIDATE_NAMES.get(cand_num, f"Candidate {cand_num}"),
            slots=tuple(slots),
            total_votes=votes,
            pixel_density=round(avg_density, 4),
        ))

    summary = None
    if page_number == 2:
        bs = _extract_3_slots(page_image, PAGE2_SUMMARY_BANDS["blank"])
        ns = _extract_3_slots(page_image, PAGE2_SUMMARY_BANDS["null"])
        us = _extract_3_slots(page_image, PAGE2_SUMMARY_BANDS["unmarked"])
        ts = _extract_3_slots(page_image, PAGE2_SUMMARY_BANDS["total_votes"])
        bv, _ = _slots_to_votes(bs)
        nv, _ = _slots_to_votes(ns)
        uv, _ = _slots_to_votes(us)
        tv, _ = _slots_to_votes(ts)
        summary = SummaryVotes(
            blank_votes=bv, null_votes=nv,
            unmarked_votes=uv, total_votes=tv,
        )

    # Normalize avg density → confidence (divide by ~0.20 as reference "high density")
    overall_conf = sum(c.pixel_density for c in candidates) / len(candidates) / 0.20
    overall_conf = min(1.0, max(0.0, overall_conf))

    return OcrResult(
        page_number=page_number,
        candidates=tuple(candidates),
        summary=summary,
        overall_confidence=round(overall_conf, 4),
    )
"""E14 Analysis — OCR extraction service.

Extracts handwritten vote counts from pages 1-2 using PaddleOCR.

Layout (from layout.py research):
  Page 1: Candidates 1-7
  Page 2: Candidates 8-13 + summary rows (blank, null, unmarked, total)

Each row has 3 digit slots (centenas, decenas, unidades).
We crop each slot individually for maximum accuracy.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

from ..config import CANDIDATE_NAMES, CANDIDATE_COUNT

log = logging.getLogger(__name__)

_ocr_engine = None


def _get_ocr_engine():
    """Lazily initialize PaddleOCR engine."""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang="en",  # digits are language-agnostic
            show_log=False,
            use_gpu=False,
        )
    return _ocr_engine


@dataclass(frozen=True)
class VoteSlot:
    """A single digit slot (one position in a 3-digit vote count)."""
    digit      : Optional[int]    # None if not detected
    confidence : float


@dataclass(frozen=True)
class CandidateVotes:
    """All votes for one candidate (3 slots)."""
    candidate_number : int
    candidate_name  : str
    slots            : tuple[VoteSlot, VoteSlot, VoteSlot]
    total_confidence : float


@dataclass(frozen=True)
class SummaryVotes:
    """Summary row totals."""
    blank_votes   : int
    null_votes    : int
    unmarked_votes: int
    total_votes   : int


@dataclass(frozen=True)
class OcrResult:
    """Full OCR result for one page."""
    page_number     : int
    candidates       : tuple[CandidateVotes, ...]   # 13 for presidential
    summary         : Optional[SummaryVotes]       # only on page 2
    overall_confidence: float
    raw_texts        : list[str]                    # all detected text for debug


# Normalized vote column coordinates (from layout.py research)
VOTE_X0 = 0.690
VOTE_X1 = 0.942

# Row bands (fraction of page height) per page
PAGE1_ROW_BANDS = [
    (0.384, 0.468),   # candidate 1
    (0.475, 0.547),   # candidate 2
    (0.554, 0.626),   # candidate 3
    (0.633, 0.706),   # candidate 4
    (0.713, 0.784),   # candidate 5
    (0.791, 0.865),   # candidate 6
    (0.872, 0.944),   # candidate 7
]

PAGE2_ROW_BANDS = [
    (0.255, 0.335),   # candidate 8
    (0.342, 0.421),   # candidate 9
    (0.428, 0.506),   # candidate 10
    (0.513, 0.592),   # candidate 11
    (0.599, 0.678),   # candidate 12
    (0.685, 0.764),   # candidate 13
]

PAGE2_SUMMARY_BANDS = {
    "blank":         (0.780, 0.803),
    "null":          (0.811, 0.833),
    "unmarked":      (0.844, 0.866),
    "total_votes":   (0.878, 0.900),
}


def _extract_digits_from_row(
    ocr_engine,
    image: Image.Image,
    row_band: tuple[float, float],
    page_width: int,
    page_height: int,
) -> list[VoteSlot]:
    """Extract 3 digit slots from a vote row.

    Uses fixed equal-width third division (slots are pre-printed on form).
    Returns 3 VoteSlot objects.
    """
    x0 = int(VOTE_X0 * page_width)
    x1 = int(VOTE_X1 * page_width)
    y0 = int(row_band[0] * page_height)
    y1 = int(row_band[1] * page_height)
    row_height = y1 - y0

    slot_width = (x1 - x0) // 3
    slots = []

    for i in range(3):
        sx0 = x0 + i * slot_width
        sx1 = sx0 + slot_width

        # Crop with small inset to avoid printed borders
        inset = int(slot_width * 0.06)
        crop = image.crop((sx0 + inset, y0, sx1 - inset, y1))

        # Run OCR on the slot
        try:
            result = ocr_engine.ocr(np.array(crop), cls=True)
            texts = result[0] if result and result[0] else []

            digit = None
            confidence = 0.0
            for line in texts:
                text = line[1][0]
                conf = line[1][1]
                digits = ''.join(c for c in text if c.isdigit())
                if digits:
                    digit = int(digits[0])   # take first digit found
                    confidence = max(confidence, conf)

            slots.append(VoteSlot(digit=digit, confidence=confidence))

        except Exception as exc:
            log.debug("OCR slot failed: %s", exc)
            slots.append(VoteSlot(digit=None, confidence=0.0))

    return slots


def _slots_to_int(slots: list[VoteSlot]) -> tuple[int, float]:
    """Convert 3 VoteSlots to an integer vote count. Returns (int, confidence)."""
    digits = []
    confidences = []
    for slot in slots:
        if slot.digit is not None:
            digits.append(str(slot.digit))
            confidences.append(slot.confidence)
        else:
            digits.append('0')
            confidences.append(0.0)

    vote_count = int(''.join(digits)) if digits else 0
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return vote_count, avg_conf


def extract_page_votes(
    page_image: Image.Image,
    page_number: int,
) -> OcrResult:
    """Extract all vote counts from a rendered page image.

    Args:
        page_image: PIL Image of page 1 or 2
        page_number: 1 or 2

    Returns:
        OcrResult with candidates and optionally summary
    """
    ocr = _get_ocr_engine()
    w, h = page_image.size

    if page_number == 1:
        row_bands = PAGE1_ROW_BANDS
        candidate_range = range(1, 8)   # 1-7
    else:
        row_bands = PAGE2_ROW_BANDS
        candidate_range = range(8, 14)  # 8-13

    candidates: list[CandidateVotes] = []

    for band, cand_num in zip(row_bands, candidate_range):
        slots = _extract_digits_from_row(ocr, page_image, band, w, h)
        vote_int, conf = _slots_to_int(slots)

        name = CANDIDATE_NAMES.get(cand_num, f"Candidate {cand_num}")
        candidates.append(CandidateVotes(
            candidate_number=cand_num,
            candidate_name=name,
            slots=tuple(slots),
            total_confidence=conf,
        ))

    summary: Optional[SummaryVotes] = None
    if page_number == 2:
        # Extract summary rows
        blank_slots = _extract_digits_from_row(
            ocr, page_image, PAGE2_SUMMARY_BANDS["blank"], w, h)
        null_slots = _extract_digits_from_row(
            ocr, page_image, PAGE2_SUMMARY_BANDS["null"], w, h)
        unmarked_slots = _extract_digits_from_row(
            ocr, page_image, PAGE2_SUMMARY_BANDS["unmarked"], w, h)
        total_slots = _extract_digits_from_row(
            ocr, page_image, PAGE2_SUMMARY_BANDS["total_votes"], w, h)

        blank_v, _ = _slots_to_int(blank_slots)
        null_v, _ = _slots_to_int(null_slots)
        unmarked_v, _ = _slots_to_int(unmarked_slots)
        total_v, _ = _slots_to_int(total_slots)

        summary = SummaryVotes(
            blank_votes=blank_v,
            null_votes=null_v,
            unmarked_votes=unmarked_v,
            total_votes=total_v,
        )

    overall_conf = sum(c.total_confidence for c in candidates) / len(candidates)
    if summary and candidates:
        overall_conf = (overall_conf + 0.9) / 2  # slight boost for having summary

    return OcrResult(
        page_number=page_number,
        candidates=tuple(candidates),
        summary=summary,
        overall_confidence=round(overall_conf, 4),
        raw_texts=[],  # could be populated for debugging
    )
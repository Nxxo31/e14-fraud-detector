"""Generate a synthetic E14-like PDF using RECTANGLE-BASED digit simulation.

The pixel-density OCR classifier needs variable ink density to distinguish
digit values. Instead of using font text (which produces similar densities
for all digits), we draw filled rectangles whose area is proportional to
the digit value (0-9). Higher digits get more coverage.

Digit coverage mapping (fraction of slot area):
  0 → 0.18  (oval shape)
  1 → 0.05  (thin vertical line)
  2 → 0.25  (curved stroke)
  3 → 0.28  (two curves)
  4 → 0.20  (angular)
  5 → 0.24  (complex)
  6 → 0.26  (loop + tail)
  7 → 0.15  (thin + diagonal)
  8 → 0.30  (double loop)
  9 → 0.27  (loop + top)

At 300 DPI, each slot is ~125×26 pixels. These coverage values give
measurable density differences at the Otsu threshold level.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import fitz


CANDIDATE_NAMES = {
    1: "Iván Cepeda", 2: "Claudia López", 3: "Santiago Botero",
    4: "Abelardo de la Espriella", 5: "Mauricio Lizcano",
    6: "Miguel Ángel Uribe", 7: "Sondra Macollins",
    8: "Roy Barreras", 9: "Eduardo Caicedo", 10: "Gustavo Matamoros",
    11: "Paloma Valencia", 12: "Sergio Fajardo", 13: "Gilberto Murillo",
}

VOTES = {
    1: 142, 2: 289, 3: 87, 4: 56, 5: 203, 6: 178, 7: 34,
    8: 167, 9: 91, 10: 45, 11: 312, 12: 198, 13: 78,
    "blank": 12, "null": 8, "unmarked": 23,
}
CANDIDATE_TOTAL = sum(v for k, v in VOTES.items() if isinstance(k, int))
TOTAL = CANDIDATE_TOTAL + VOTES["blank"] + VOTES["null"] + VOTES["unmarked"]

# OCR coordinate system
VOTE_X0, VOTE_X1 = 0.690, 0.942
PAGE_W, PAGE_H = 595, 842

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

SIGNATURE_BOXES = [
    {"id": 1, "x": 0.15, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 2, "x": 0.40, "y": 0.62, "w": 0.22, "h": 0.10},
    {"id": 3, "x": 0.65, "y": 0.62, "w": 0.22, "h": 0.10},
]

# Digit → coverage fraction of slot area (ink density after Otsu binarization)
DIGIT_COVERAGE = {
    '0': 0.18, '1': 0.05, '2': 0.25, '3': 0.28,
    '4': 0.20, '5': 0.24, '6': 0.26, '7': 0.15,
    '8': 0.30, '9': 0.27,
}


def _draw_digit_in_slot(
    page: fitz.Page,
    slot_x0: int, slot_y0: int, slot_w: int, slot_h: int,
    digit: str,
) -> None:
    """Draw a filled digit in a slot as a rectangle cluster.

    Simulates handwritten digit coverage by drawing multiple small filled
    rectangles whose total area corresponds to the digit's coverage fraction.
    """
    coverage = DIGIT_COVERAGE[digit]
    target_area = int(slot_w * slot_h * coverage)

    # Draw filled rectangles ("ink clusters") until we hit target_area
    # Use varied sizes and positions to simulate natural handwriting
    INK_COLOR = (0.05, 0.05, 0.05)  # near-black ink
    y = slot_y0 + 2
    x = slot_x0 + 2
    area_drawn = 0
    rect_h = 3  # height of each ink stroke

    while area_drawn < target_area and y < slot_y0 + slot_h - rect_h:
        remaining_area = target_area - area_drawn
        # Width proportional to remaining area need
        max_w = min(slot_w - 4 - x + slot_x0, remaining_area // rect_h + 1)
        rect_w = max(2, max_w)

        if x + rect_w > slot_x0 + slot_w - 2:
            x = slot_x0 + 2
            y += 4
            if y >= slot_y0 + slot_h - rect_h:
                break

        rect = fitz.Rect(x, y, min(x + rect_w, slot_x0 + slot_w - 2), y + rect_h)
        page.draw_rect(rect, color=INK_COLOR, fill=INK_COLOR, width=0)
        area_drawn += rect_w * rect_h
        x += rect_w + 1
        if x >= slot_x0 + slot_w - 4:
            x = slot_x0 + 2
            y += 4


def _write_vote(page: fitz.Page, vote: int, x0: int, y0: int, w: int, h: int) -> None:
    """Draw a 3-digit vote count into a row band at the given slot coordinates."""
    digits = f"{vote:03d}"
    slot_w = w // 3
    for si, digit in enumerate(digits):
        sx = x0 + si * slot_w
        _draw_digit_in_slot(page, sx + 1, y0 + 1, slot_w - 2, h - 2, digit)


def draw_page1(doc: fitz.Document) -> None:
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    page.insert_text((25, 20), "E-14  ELECCIONES 2026  PAGINA 1", fontsize=8)

    x0 = int(VOTE_X0 * PAGE_W)
    x1 = int(VOTE_X1 * PAGE_W)
    total_slot_w = x1 - x0

    for i, cand_num in enumerate(range(1, 8)):
        band = PAGE1_ROW_BANDS[i]
        y0 = int(band[0] * PAGE_H)
        y1 = int(band[1] * PAGE_H)
        _write_vote(page, VOTES[cand_num], x0, y0, total_slot_w, y1 - y0)


def draw_page2(doc: fitz.Document) -> None:
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    page.insert_text((25, 20), "E-14  ELECCIONES 2026  PAGINA 2", fontsize=8)

    x0 = int(VOTE_X0 * PAGE_W)
    x1 = int(VOTE_X1 * PAGE_W)
    total_slot_w = x1 - x0

    # Candidates 8-13
    for i, cand_num in enumerate(range(8, 14)):
        band = PAGE2_ROW_BANDS[i]
        y0 = int(band[0] * PAGE_H)
        y1 = int(band[1] * PAGE_H)
        _write_vote(page, VOTES[cand_num], x0, y0, total_slot_w, y1 - y0)

    # Summary rows
    summary_map = {
        "blank": VOTES["blank"], "null": VOTES["null"],
        "unmarked": VOTES["unmarked"], "total_votes": TOTAL,
    }
    for label, band in PAGE2_SUMMARY_BANDS.items():
        y0 = int(band[0] * PAGE_H)
        y1 = int(band[1] * PAGE_H)
        _write_vote(page, summary_map[label], x0, y0, total_slot_w, y1 - y0)


def draw_page3(doc: fitz.Document) -> None:
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    page.insert_text((25, 20), "E-14  FIRMAS DE JURADOS  PAGINA 3", fontsize=8)

    # ── Signature boxes ──────────────────────────────────────────────────
    for box in SIGNATURE_BOXES:
        bx = int(box["x"] * PAGE_W)
        by = int(box["y"] * PAGE_H)
        bw = int(box["w"] * PAGE_W)
        bh = int(box["h"] * PAGE_H)

        page.draw_rect(fitz.Rect(bx, by, bx + bw, by + bh), color=(0, 0, 0), width=0.5)

        # High-density signature strokes → target >0.15 for PRESENT
        # ~15 horizontal strokes ≈ 22% coverage
        INK = (0.08, 0.08, 0.08)
        for sy in range(by + 6, by + bh - 5, 4):
            page.draw_line(
                fitz.Point(bx + 3, sy),
                fitz.Point(bx + bw - 3, sy),
                color=INK, width=1.0,
            )

        page.insert_text((bx + 2, by + bh - 1), f"Firma {box['id']}", fontsize=6)


def generate(output_path: str) -> None:
    doc = fitz.Document()
    doc.set_metadata({"title": "E-14 Synthetic Test"})

    draw_page1(doc)
    draw_page2(doc)
    draw_page3(doc)

    doc.save(output_path, garbage=3, deflate=True, clean=True)
    doc.close()

    print(f"\n  Generated: {output_path}")
    print(f"  Candidates: {CANDIDATE_TOTAL} votes")
    print(f"  Sum check: {CANDIDATE_TOTAL + VOTES['blank'] + VOTES['null'] + VOTES['unmarked']} = {TOTAL} (declared)")


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "data" / "synthetic_e14.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    generate(str(out))
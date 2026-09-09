"""E14 Analysis — PDF rendering service.

Renders E-14 PDF pages to PIL Images at configurable DPI.
Each E-14 has exactly 3 pages:
  Page 1: Candidates 1-7
  Page 2: Candidates 8-13 + totals
  Page 3: Signatures of jury members

Caps output size to MAX_RENDER_MP to prevent OOM on pathological scans.
"""

import io
import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from .config import RENDER_DPI, MAX_RENDER_MP

log = logging.getLogger(__name__)


class PdfRenderError(Exception):
    """Raised when a PDF cannot be rendered."""


@dataclass(frozen=True)
class RenderedPage:
    """A single rendered page."""
    page_number: int      # 1-based
    width: int            # pixels
    height: int           # pixels
    dpi: int
    image: Image.Image


def _load_fitx():
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise PdfRenderError(
            "PyMuPDF (fitz) is required. Install: pip install pymupdf"
        ) from exc
    return fitz


def render_pdf_pages(
    pdf_bytes: bytes,
    pages: Optional[list[int]] = None,
    dpi: int = RENDER_DPI,
) -> list[RenderedPage]:
    """Render specific pages (1-based) to PIL Images.

    Args:
        pdf_bytes: raw PDF content
        pages: list of 1-based page numbers (default: [1, 2, 3])
        dpi: dots per inch (default: 300)

    Returns:
        list of RenderedPage objects

    Raises:
        PdfRenderError on rendering failure
    """
    fitz = _load_fitx()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PdfRenderError(f"Cannot open PDF: {exc}") from exc

    if len(doc) < 3:
        raise PdfRenderError(f"PDF has only {len(doc)} pages, expected 3")

    if pages is None:
        pages = [1, 2, 3]

    rendered: list[RenderedPage] = []

    try:
        zoom = dpi / 72.0

        for page_num in pages:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                raise PdfRenderError(f"Page {page_num} out of range (1-{len(doc)})")

            page = doc.load_page(idx)

            # Cap zoom to prevent OOM from pathological page sizes
            page_zoom = zoom
            rect = page.rect
            projected_mp = (rect.width * zoom) * (rect.height * zoom) / 1e6
            if MAX_RENDER_MP > 0 and projected_mp > MAX_RENDER_MP:
                page_zoom = zoom * (MAX_RENDER_MP / projected_mp) ** 0.5
                log.debug(
                    "Capped DPI from %.1f to %.1f for page %d (would be %.1f MP)",
                    zoom, page_zoom, page_num, projected_mp,
                )

            mat = fitz.Matrix(page_zoom, page_zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            rendered.append(RenderedPage(
                page_number=page_num,
                width=pix.width,
                height=pix.height,
                dpi=dpi,
                image=image,
            ))

        return rendered

    finally:
        doc.close()


def validate_image_quality(image: Image.Image) -> dict:
    """Check image quality before OCR.

    Returns:
        dict with keys: valid (bool), issues (list[str]),
        dimensions (tuple), dpi (int)
    """
    issues = []

    w, h = image.size

    # Resolution check
    if w < 800 or h < 800:
        issues.append("LOW_RESOLUTION")

    # Aspect ratio (E-14 is approximately A4, ~0.707)
    ar = w / h if h else 0
    if not (0.55 <= ar <= 0.85):
        issues.append("UNUSUAL_ASPECT_RATIO")

    # Brightness check
    gray = image.convert("L")
    import numpy as np
    pixels = np.array(gray.getdata())
    avg = pixels.mean()
    if avg > 230:
        issues.append("OVEREXPOSED")
    elif avg < 40:
        issues.append("UNDEREXPOSED")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "dimensions": (w, h),
        "aspect_ratio": round(ar, 4),
    }
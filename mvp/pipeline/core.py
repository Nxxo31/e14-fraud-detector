"""MVP Pipeline — Core PDF rendering using PyMuPDF.

Renders E-14 PDF pages to PIL Images.
E-14 has exactly 3 pages:
  Page 1: Candidates 1-7
  Page 2: Candidates 8-13 + totals
  Page 3: Signatures of jury members
"""

import io
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class RenderedPage:
    page_number: int  # 1-based
    width: int
    height: int
    dpi: int
    image: Image.Image


def render_pdf_pages(pdf_bytes: bytes, pages: list[int] | None = None, dpi: int = 300):
    """Render specific pages (1-based) to PIL Images.

    Args:
        pdf_bytes: raw PDF content
        pages: list of 1-based page numbers (default: [1, 2, 3])
        dpi: dots per inch (default: 300)

    Returns:
        list of RenderedPage objects
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if len(doc) < 3:
        doc.close()
        raise ValueError(f"PDF has {len(doc)} pages, expected 3")

    if pages is None:
        pages = [1, 2, 3]

    rendered = []
    zoom = dpi / 72.0

    for page_num in pages:
        idx = page_num - 1
        if idx < 0 or idx >= len(doc):
            doc.close()
            raise ValueError(f"Page {page_num} out of range (1-{len(doc)})")

        page = doc.load_page(idx)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        rendered.append(RenderedPage(
            page_number=page_num,
            width=pix.width,
            height=pix.height,
            dpi=dpi,
            image=image,
        ))

    doc.close()
    return rendered


def pdf_to_bytes(path: str) -> bytes:
    """Read a PDF file from disk."""
    with open(path, "rb") as f:
        return f.read()
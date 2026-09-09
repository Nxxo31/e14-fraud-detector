"""MVP Pipeline — Main orchestrator.

PDF → Render (PyMuPDF) → Signature Detection (OpenCV)
    → OCR (pixel density) → Math Validation → Risk Score → SQLite Storage

Usage:
    python -m mvp.pipeline.run <pdf_path_or_url>
"""

import hashlib
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mvp.pipeline.core import render_pdf_pages, pdf_to_bytes
from mvp.pipeline.signature import detect_signatures
from mvp.pipeline.ocr import extract_page_votes
from mvp.pipeline.validation import validate_mathematics, calculate_risk_score
from mvp.pipeline.storage import save_analysis
from mvp.pipeline.download import try_download


def run_pipeline(pdf_bytes: bytes, pdf_filename: str, table_code: str = "unknown") -> dict:
    """Run the complete analysis pipeline on one E-14 PDF.

    Returns a dict with all results and the SQLite row ID.
    """
    # SHA256 for identification
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    print(f"  PDF SHA256: {sha256[:16]}...")

    # ── Step 1: Render all 3 pages ───────────────────────────────────────
    print("  [1/5] Rendering pages (300 DPI)...")
    pages = render_pdf_pages(pdf_bytes, pages=[1, 2, 3], dpi=300)
    page_images = {p.page_number: p.image for p in pages}
    print(f"       Pages rendered: {[p.page_number for p in pages]}")
    print(f"       Sizes: {[f'{p.width}x{p.height}' for p in pages]}")

    # ── Step 2: Signature detection (page 3) ────────────────────────────
    print("  [2/5] Detecting signatures (page 3)...")
    sig_result = detect_signatures(page_images[3])
    print(f"       Status: {sig_result.overall_status}")
    print(f"       Found: {sig_result.signatures_found}/{sig_result.signatures_expected}")
    for box in sig_result.boxes:
        print(f"         Box {box.box_id}: {box.status} (ink={box.ink_density:.4f}, risk={box.risk})")

    # ── Step 3: OCR pages 1 and 2 ──────────────────────────────────────
    print("  [3/5] OCR extraction (pages 1 and 2)...")
    page1_ocr = extract_page_votes(page_images[1], page_number=1)
    page2_ocr = extract_page_votes(page_images[2], page_number=2)

    print(f"       Page 1: {len(page1_ocr.candidates)} candidates, conf={page1_ocr.overall_confidence:.2%}")
    print(f"       Page 2: {len(page2_ocr.candidates)} candidates, conf={page2_ocr.overall_confidence:.2%}")

    if page2_ocr.summary:
        s = page2_ocr.summary
        print(f"       Summary: total={s.total_votes}, blank={s.blank_votes}, null={s.null_votes}, unmarked={s.unmarked_votes}")

    for cand in page1_ocr.candidates:
        digits = [str(s.digit) if s.digit is not None else '_' for s in cand.slots]
        print(f"         Cand {cand.candidate_number} ({cand.candidate_name[:20]}): {''.join(digits)}")

    for cand in page2_ocr.candidates:
        digits = [str(s.digit) if s.digit is not None else '_' for s in cand.slots]
        print(f"         Cand {cand.candidate_number} ({cand.candidate_name[:20]}): {''.join(digits)}")

    # ── Step 4: Mathematical validation ────────────────────────────────
    print("  [4/5] Mathematical validation...")
    math_result = validate_mathematics(page1_ocr, page2_ocr)
    print(f"       Valid: {math_result.valid}")
    print(f"       Anomalies: {math_result.anomaly_count}")
    for a in math_result.anomalies:
        print(f"         [{a.severity}] {a.rule}: {a.message}")

    # ── Step 5: Risk scoring ───────────────────────────────────────────
    print("  [5/5] Risk scoring...")
    avg_conf = (page1_ocr.overall_confidence + page2_ocr.overall_confidence) / 2
    risk_score = calculate_risk_score(sig_result, math_result, avg_conf)
    print(f"       Score: {risk_score.score}/100 — {risk_score.level}")
    print(f"       Breakdown: {risk_score.breakdown}")

    # ── Step 6: Save to SQLite ────────────────────────────────────────
    print("  [6/6] Saving to SQLite...")
    mvp_dir = Path(__file__).parent.parent
    analysis_id = save_analysis(
        table_code=table_code,
        pdf_filename=pdf_filename,
        pdf_sha256=sha256,
        sig_result=sig_result,
        page1_ocr=page1_ocr,
        page2_ocr=page2_ocr,
        validation_result=math_result,
        risk_score=risk_score,
        pages=pages,
        mvp_dir=mvp_dir,
    )
    print(f"       Saved to SQLite row ID: {analysis_id}")

    return {
        "analysis_id": analysis_id,
        "sha256": sha256,
        "pages": pages,
        "sig_result": sig_result,
        "page1_ocr": page1_ocr,
        "page2_ocr": page2_ocr,
        "math_result": math_result,
        "risk_score": risk_score,
    }


def main():
    mvp_dir = Path(__file__).parent.parent

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.startswith("http"):
            print(f"Downloading PDF from: {arg}")
            pdf_bytes = try_download(arg)
            if not pdf_bytes:
                print("FAIL: Could not download PDF")
                sys.exit(1)
            pdf_filename = arg.split("/")[-1]
            table_code = "url_download"
        else:
            pdf_path = Path(arg)
            if not pdf_path.exists():
                print(f"FAIL: File not found: {pdf_path}")
                sys.exit(1)
            print(f"Loading PDF: {pdf_path}")
            pdf_bytes = pdf_to_bytes(str(pdf_path))
            pdf_filename = pdf_path.name
            table_code = pdf_path.stem
    else:
        print("No PDF provided, attempting download...")
        pdf_bytes = try_download()
        if not pdf_bytes:
            print("FAIL: No PDF available. Provide a path or URL.")
            print("Usage: python -m mvp.pipeline.run <pdf_path_or_url>")
            sys.exit(1)
        pdf_filename = "downloaded_e14.pdf"
        table_code = "test_download"

    print(f"\n{'='*60}")
    print(f"E14 MVP PIPELINE — Processing: {pdf_filename}")
    print(f"{'='*60}\n")

    result = run_pipeline(pdf_bytes, pdf_filename, table_code)

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"  Analysis ID: {result['analysis_id']}")
    print(f"  SHA256: {result['sha256']}")
    print(f"  Risk Score: {result['risk_score'].score}/100 ({result['risk_score'].level})")
    print(f"  Signatures: {result['sig_result'].signatures_found}/{result['sig_result'].signatures_expected} ({result['sig_result'].overall_status})")
    print(f"  Anomalies: {result['math_result'].anomaly_count}")
    print(f"  Database: ~/proyectos/e14-audit-platform/mvp/data/e14_mvp.db")
    print(f"  Page images: ~/proyectos/e14-audit-platform/mvp/data/pages/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
"""MVP Pipeline — Download one E14 PDF from Registraduria CDN.

Uses requests (no TLS fingerprinting). Tries simple download first.
If blocked, tries with browser-like headers.
"""

import requests

BASE = "https://divulgacione14presidente.registraduria.gov.co"

# Bogotá mesa 1 - try a few known table codes
TEST_URLS = [
    f"{BASE}/assets/temis/pdf/11/001/001/0001/0001/PRE/0011-03-001-00-00-0001-01.pdf",
    f"{BASE}/assets/temis/pdf/11/001/001/0001/0001/PRE/0011-03-001-00-00-0002-01.pdf",
    f"{BASE}/assets/temis/pdf/11/001/001/0001/0001/PRE/0011-03-001-00-00-0010-01.pdf",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": f"{BASE}/home",
}


def download_e14_pdf(url: str, timeout: int = 30) -> bytes | None:
    """Download an E14 PDF. Returns bytes or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 10000:
            print(f"  OK: {len(resp.content):,} bytes, Content-Type: {resp.headers.get('Content-Type')}")
            return resp.content
        else:
            print(f"  HTTP {resp.status_code}, {len(resp.content)} bytes")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def try_download(table_code: str | None = None) -> bytes | None:
    """Try downloading from known URLs. Returns PDF bytes or None."""
    import os

    # If a cached PDF exists locally, use it
    cache_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    cached = os.path.join(cache_dir, "test_e14.pdf")
    if os.path.exists(cached):
        print(f"Using cached PDF: {cached}")
        with open(cached, "rb") as f:
            return f.read()

    print("Attempting download from Registraduria CDN...")
    for url in TEST_URLS:
        print(f"  Trying: {url}")
        pdf_bytes = download_e14_pdf(url)
        if pdf_bytes:
            return pdf_bytes

    print("  All download attempts failed.")
    return None
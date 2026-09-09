import urllib.request
from pathlib import Path

OUTDIR = Path("data/pdf_control")
OUTDIR.mkdir(exist_ok=True)

# Headers de navegador real
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": "https://divulgacione14presidente.registraduria.gov.co/",
    "Connection": "keep-alive",
}

urls = {
    "Atlantico": "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/08/001/001/0001/0001/PRE/08001-01-001-00-00-0001-01.pdf",
    "Narino": "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/52/001/001/0001/0001/PRE/52001-01-001-00-00-0001-01.pdf",
    "Choco": "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/27/001/001/0001/0001/PRE/27001-01-001-00-00-0001-01.pdf",
    "Bogota": "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/11/001/001/0001/0001/PRE/11001-01-001-00-00-0001-01.pdf",
}

for depto, url in urls.items():
    out_path = OUTDIR / f"{depto}_01.pdf"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            out_path.write_bytes(data)
            print(f"{depto}: {len(data)} bytes | Status: {resp.status}")
    except Exception as e:
        print(f"{depto}: ERROR - {e}")


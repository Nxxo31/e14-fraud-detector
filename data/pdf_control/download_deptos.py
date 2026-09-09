import subprocess
import os
from pathlib import Path

OUTDIR = Path("data/pdf_control")
OUTDIR.mkdir(exist_ok=True)

# URLs de prueba para diferentes departamentos
# Patrón: https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/{dd}/{mmm}/{zzz}/{pp}/{mm}/PRE/E14-{depto}-{muni}-{zona}-{puesto}-{mesa}.pdf
# Simplificado para prueba - intentar con estructura fija conocida de Turbos
urls = {
    "Atlantico": [
        "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/08/001/001/0001/0001/PRE/08001-01-001-00-00-0001-01.pdf",
    ],
    "Narino": [
        "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/52/001/001/0001/0001/PRE/52001-01-001-00-00-0001-01.pdf",
    ],
    "Choco": [
        "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/27/001/001/0001/0001/PRE/27001-01-001-00-00-0001-01.pdf",
    ],
    "Bogota": [
        "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/11/001/001/0001/0001/PRE/11001-01-001-00-00-0001-01.pdf",
    ]
}

for depto, urls_list in urls.items():
    for i, url in enumerate(urls_list, 1):
        out_path = OUTDIR / f"{depto}_{i:02d}.pdf"
        if out_path.exists():
            print(f"Skipping: {out_path}")
            continue
        try:
            print(f"Downloading: {depto} -> {url.split('/')[-1]}")
            result = subprocess.run(
                ["curl", "-s", "-L", "-o", str(out_path), url],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and out_path.stat().st_size > 1000:
                print(f"  OK: {out_path.stat().st_size} bytes")
            else:
                print(f"  FAIL")
                out_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"  Error: {e}")


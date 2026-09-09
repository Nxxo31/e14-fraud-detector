"""
Detector de QR/barcode — pyzbar (zbar C backend).
Extrae códigos QR y barcodes 1D de las páginas renderizadas del acta E-14.

 megfelana al contrato DB (schema_sqlite.sql):
    qr_raw_value        TEXT   — payload decodificado
    qr_decoded_match    0/1    — el QR coincide con metadatos esperados
    flag_qr_metadata_mismatch  — discrepancia cuando el QR no coincide

Sigue la regla de coordenadas SIEMPRE normalizadas (0-1) del proyecto.

R-17 / B-6: pyzbar QR/Barcode extraction.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import cv2
import numpy as np

# pyzbar requiere libzbar0 (instalado en el sistema). Las mates zbar exponen
# un protocolo estable; ocultamos el import en un try para que el pipeline
# no revienta si la lib nativa falta en otro host — el caller ya wrappea esto
# en try/except, pero manteg el fallback limpio.
try:
    from pyzbar.pyzbar import decode as _zbar_decode, ZBarSymbol
    _PYZBAR_AVAILABLE = True
except Exception:  # ImportError o OSError si libzbar falta
    _PYZBAR_AVAILABLE = False
    _zbar_decode = None  # type: ignore[assignment]
    ZBarSymbol = None  # type: ignore[assignment]


def is_available() -> bool:
    """True si pyzbar + libzbar están operativos."""
    return _PYZBAR_AVAILABLE


def _decode_symbols(image: np.ndarray) -> List[Dict[str, Any]]:
    """
    Decodifica QR + barcodes 1D de una imagen BGR/GRAY con pyzbar.

    pyzbar necesita imágenes en gris o BGR; aquí normalizamos a gris y
    pasamos la imagen sin recortar para que el detector examine toda la
    página renderizada (los QR E-14 suelen ocupar una esquina).
    """
    if not _PYZBAR_AVAILABLE:
        return []

    if image is None or image.size == 0:
        return []

    # pyzbar admite numpy arrays; prefiere uint8. Convertir BGR→GRAY mejora
    # la tasa de detección pero no es obligatorio.
    if len(image.shape) == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Forzar todos los símbolos (QR + 1D) — zbar por defecto ya los incluye,
    # pero al pasar symbols=ZBarSymbol.NONE dejamos que zbar autodetecte todo.
    try:
        results = _zbar_decode(gray, symbols=ZBarSymbol.NONE)  # type: ignore[union-attr]
    except Exception:
        # Fallback sin param symbols si la API del binding difiere
        try:
            results = _zbar_decode(gray)  # type: ignore[misc]
        except Exception:
            return []

    symbols: List[Dict[str, Any]] = []
    for r in results:
        rect = getattr(r, "rect", None)
        # rect → (x, y, width, height)
        if rect is None or len(rect) != 4:
            continue

        symbols.append({
            "type": str(getattr(r, "type", "")),
            "data": (r.data.decode("utf-8", errors="replace")
                     if isinstance(getattr(r, "data", None), (bytes, bytearray))
                     else str(getattr(r, "data", "") or "")),
            "quality": int(getattr(r, "quality", 0) or 0),
            "rect": [int(v) for v in rect],
            "polygon": [[int(p.x), int(p.y)] for p in getattr(r, "polygon", []) or []],
        })

    return symbols


def detect_qr_barcode(
    page_image: np.ndarray,
    page_index: int = 0,
    expected_mesa_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detecta QR/ barcodes en una página renderizada del acta.

    Args:
        page_image: imagen BGR o GRAY (numpy uint8) de la página renderizada.
        page_index: índice de página base-0 (solo para metadata).
        expected_mesa_key: mesa_key esperada para validar coincidencia del QR.

    Returns:
        {
            "available": bool,           # pyzbar operativo
            "page": int,                  # page_index
            "count": int,                 # total de símbolos decodificados
            "symbols": [{                 # uno por símbolo detectado
                "type": str,              # 'QRCODE', 'EAN13', 'CODE128', ...
                "data": str,              # payload decodificado
                "quality": int,           # calidad zbar
                "bbox_norm": [x,y,w,h],   # coordenadas NORMALIZADAS 0-1 (regla R-08)
                "rect_px": [x,y,w,h],     # bbox en píxeles (depuración)
            }],
            "qr_raw_value": str | None,  # payload del primer QR (contrato DB)
            "qr_decoded_match": bool | None,  # True/False/None(sin esperado)
            "discrepancia_qr": bool,       # True si mismatch contra mesa_key
            "discrepancia_razon": str | None,
        }
    """
    h, w = (page_image.shape[:2] if page_image is not None else (0, 0))

    symbols_raw = _decode_symbols(page_image)

    symbols_out: List[Dict[str, Any]] = []
    qr_raw_value: Optional[str] = None

    for sym in symbols_raw:
        sx, sy, sw, sh = sym["rect"]
        # Coordenadas NORMALIZADAS 0-1 (regla R-08 — nunca píxeles fijos).
        bbox_norm = [
            round(sx / w, 6) if w else 0.0,
            round(sy / h, 6) if h else 0.0,
            round(sw / w, 6) if w else 0.0,
            round(sh / h, 6) if h else 0.0,
        ]
        symbols_out.append({
            "type": sym["type"],
            "data": sym["data"],
            "quality": sym["quality"],
            "bbox_norm": bbox_norm,
            "rect_px": [sx, sy, sw, sh],
        })
        # Tomar el primer QR como qr_raw_value (contrato schema_sqlite.sql).
        if qr_raw_value is None and sym["type"].upper() in ("QRCODE", "QR_CODE", "QRCODE_SCALE"):
            qr_raw_value = sym["data"]

    # Validación contra mesa_key esperada (flag_qr_metadata_mismatch en DB).
    qr_decoded_match: Optional[bool] = None
    discrepancia_qr = False
    discrepancia_razon: Optional[str] = None

    if qr_raw_value is not None:
        if expected_mesa_key:
            # Los QR E-14 suelen ser un hash interno; comparamos si el payload
            # contiene la mesa_key esperada. Si no coincide → discrepancia.
            match = expected_mesa_key in qr_raw_value or qr_raw_value == expected_mesa_key
            qr_decoded_match = bool(match)
            if not match:
                discrepancia_qr = True
                discrepancia_razon = (
                    f"QR decodificado ('{qr_raw_value}') no coincide con "
                    f"mesa_key esperada ('{expected_mesa_key}')"
                )
        else:
            # Sin mesa_key esperada: el QR se decodificó pero no podemos validar.
            qr_decoded_match = None
    elif expected_mesa_key is not None:
        # Había mesa_key esperada pero NO se detectó QR → también es señal.
        qr_decoded_match = False
        discrepancia_qr = True
        discrepancia_razon = (
            f"No se detectó QR/barcode en el acta pero se esperaba "
            f"mesa_key='{expected_mesa_key}'"
        )

    return {
        "available": _PYZBAR_AVAILABLE,
        "page": page_index,
        "count": len(symbols_out),
        "symbols": symbols_out,
        "qr_raw_value": qr_raw_value,
        "qr_decoded_match": qr_decoded_match,
        "discrepancia_qr": discrepancia_qr,
        "discrepancia_razon": discrepancia_razon,
    }


def detect_qr_barcode_all_pages(
    page_images: List[np.ndarray],
    expected_mesa_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta la detección sobre todas las páginas renderizadas y agrega.

    Returns:
        {
            "available": bool,
            "total_symbols": int,
            "pages": [<detect_qr_barcode output por página>],
            "qr_raw_value": str | None,  # primer QR encontrado en cualquiera página
            "qr_decoded_match": bool | None,
            "discrepancia_qr": bool,
            "discrepancia_razon": str | None,
            "discrepancias": [<entry de discrepancia 'qr_metadata_mismatch'>],
        }
    """
    pages: List[Dict[str, Any]] = []
    first_qr: Optional[str] = None
    any_mismatch = False
    mismatch_reason: Optional[str] = None

    for idx, img in enumerate(page_images):
        page_res = detect_qr_barcode(img, page_index=idx, expected_mesa_key=expected_mesa_key)
        pages.append(page_res)
        if first_qr is None and page_res["qr_raw_value"] is not None:
            first_qr = page_res["qr_raw_value"]
        if page_res["discrepancia_qr"]:
            any_mismatch = True
            if mismatch_reason is None:
                mismatch_reason = page_res["discrepancia_razon"]

    total_symbols = sum(p["count"] for p in pages)

    # Resumen de discrepancia estilo Capa 0 (para alimentar generate_discrepancias).
    mismatches = [p for p in pages if p["discrepancia_qr"]]
    discrepancias: List[Dict[str, Any]] = []
    for p in mismatches:
        _append_discrepancy(discrepancias, p)

    return {
        "available": _PYZBAR_AVAILABLE,
        "total_symbols": total_symbols,
        "pages": pages,
        "qr_raw_value": first_qr,
        "qr_decoded_match": (pages[0]["qr_decoded_match"] if pages else None),
        "discrepancia_qr": any_mismatch,
        "discrepancia_razon": mismatch_reason,
        "discrepancias": discrepancias,
    }


def _append_discrepancy(
    target: List[Dict[str, Any]],
    page_res: Dict[str, Any],
) -> None:
    """Helper: convierte un mismatch de página en un entry de discrepancia tipada."""
    target.append({
        "tipo": "qr_metadata_mismatch",
        "capa": 0,
        "page": page_res.get("page", 0),
        "razon": page_res.get("discrepancia_razon") or "QR metadata mismatch",
        "qr_raw_value": page_res.get("qr_raw_value"),
        "qr_decoded_match": page_res.get("qr_decoded_match"),
    })


# Test rápido: decodifica el primer PDF de muestra con QR.
if __name__ == "__main__":
    import sys
    from pathlib import Path

    pdf_dir = Path(__file__).resolve().parents[2] / "data" / "pdf_muestra"
    if not pdf_dir.exists():
        print(f"No encontrado: {pdf_dir}")
        sys.exit(0)

    import fitz  # PyMuPDF

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        print(f"\n{'='*60}\n📄 {pdf_path.name}\n{'='*60}")
        doc = fitz.open(str(pdf_path))
        page_images: List[np.ndarray] = []
        for pn in range(len(doc)):
            pix = doc[pn].get_pixmap(matrix=fitz.Matrix(2, 2))
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_images.append(np.array(img))
        doc.close()

        res = detect_qr_barcode_all_pages(page_images, expected_mesa_key=pdf_path.stem)
        print(f"available={res['available']}  total_symbols={res['total_symbols']}")
        print(f"qr_raw_value={res['qr_raw_value']!r}")
        print(f"qr_decoded_match={res['qr_decoded_match']}")
        print(f"discrepancia_qr={res['discrepancia_qr']}  razon={res['discrepancia_razon']}")
        for p in res["pages"]:
            if p["count"]:
                print(f"  page {p['page']}: {p['count']} símbolo(s)")
                for s in p["symbols"]:
                    print(f"    - {s['type']}: {s['data'][:60]!r}  bbox_norm={s['bbox_norm']}")

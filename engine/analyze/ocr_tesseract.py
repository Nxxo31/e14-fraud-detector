"""
Motor OCR — Tesseract para extracción de texto y dígitos de celdas E-14.
"""
import pytesseract
import cv2
import numpy as np
from typing import Dict, Any, Optional


# Configurar path de tesseract si no está en PATH estándar
import shutil
tesseract_bin = shutil.which("tesseract")
if tesseract_bin:
    pytesseract.pytesseract.tesseract_cmd = tesseract_bin


def ocr_text(image: np.ndarray, lang: str = "spa") -> Dict[str, Any]:
    """
    Extrae texto de una imagen usando Tesseract.

    Returns:
        {"text": str, "confidence": float, "words": int}
    """
    if image is None or image.size == 0:
        return {"text": "", "confidence": 0.0, "words": 0}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Pre-procesamiento: binarización adaptativa
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    # OCR
    data = pytesseract.image_to_data(binary, lang=lang, output_type=pytesseract.Output.DICT)

    # Extraer palabras con confianza
    words = []
    confidences = []
    for i, conf in enumerate(data["conf"]):
        if conf > 30:  # Umbral mínimo de confianza
            word = data["text"][i].strip()
            if word:
                words.append(word)
                confidences.append(conf)

    text = " ".join(words)
    avg_conf = float(np.mean(confidences)) if confidences else 0.0

    return {
        "text": text.strip(),
        "confidence": round(avg_conf, 2),
        "words": len(words)
    }


def ocr_digit(cell_image: np.ndarray) -> Dict[str, Any]:
    """
    Intenta leer un dígito manuscrito de una celda E-14.

    Usa configuración optimizada para dígitos:
    - Solo números (--psm 7 = single text line)
    - Whitelist de dígitos

    Returns:
        {"digit": int | None, "text_raw": str, "confidence": float}
    """
    if cell_image is None or cell_image.size == 0:
        return {"digit": None, "text_raw": "", "confidence": 0.0}

    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY) if len(cell_image.shape) == 3 else cell_image

    # Invertir si es necesario (tinta oscura sobre fondo claro)
    if np.mean(gray) > 127:
        gray = 255 - gray

    # Configuración para dígitos
    config = "--psm 7 -c tessedit_char_whitelist=0123456789"

    text = pytesseract.image_to_string(gray, lang="spa", config=config).strip()
    data = pytesseract.image_to_data(gray, lang="spa", config=config, output_type=pytesseract.Output.DICT)

    # Confianza promedio
    confs = [c for c in data["conf"] if c > 0]
    confidence = float(np.mean(confs)) / 100.0 if confs else 0.0

    # Extraer dígito
    digit = None
    numbers = "".join(c for c in text if c.isdigit())
    if numbers:
        try:
            digit = int(numbers)
        except ValueError:
            pass

    return {
        "digit": digit,
        "text_raw": text,
        "confidence": round(confidence, 4)
    }


def ocr_metadata(image: np.ndarray) -> Dict[str, Any]:
    """
    Extrae metadatos del encabezado del acta:
    departamento, municipio, zona, puesto, mesa.
    """
    if image is None or image.size == 0:
        return {"departamento": "", "municipio": "", "zona": "", "puesto": "", "mesa": ""}

    result = ocr_text(image, lang="spa")
    text = result["text"]

    metadata = {
        "departamento": "",
        "municipio": "",
        "zona": "",
        "puesto": "",
        "mesa": "",
        "texto_completo": text,
        "confianza": result["confidence"]
    }

    # Búsqueda simple de patrones
    lines = text.split("\n") if "\n" in text else [text]
    for line in lines:
        upper = line.upper()
        if "DEPARTAMENTO" in upper:
            metadata["departamento"] = line.split(":")[-1].strip() if ":" in line else line
        elif "MUNICIPIO" in upper:
            metadata["municipio"] = line.split(":")[-1].strip() if ":" in line else line
        elif "ZONA" in upper and ":" in line:
            metadata["zona"] = line.split(":")[-1].strip()
        elif "PUESTO" in upper and ":" in line:
            metadata["puesto"] = line.split(":")[-1].strip()
        elif "MESA" in upper and ":" in line:
            metadata["mesa"] = line.split(":")[-1].strip()

    return metadata


# Test rápido
if __name__ == "__main__":
    from pathlib import Path

    # Buscar una celda de prueba
    celdas_dir = Path(__file__).parent.parent.parent / "data" / "output" / "celdas"
    test_cell = celdas_dir / "Anza_c0.png"

    if test_cell.exists():
        img = cv2.imread(str(test_cell))
        print(f"OCR texto: {ocr_text(img)}")
        print(f"OCR dígito: {ocr_digit(img)}")
    else:
        print(f"No se encontró: {test_cell}")
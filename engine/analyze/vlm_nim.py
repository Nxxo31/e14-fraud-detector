"""
Capa 2 — Análisis VLM (NVIDIA NIM).
Envía imágenes de celdas sospechosas a un modelo de visión
para obtener análisis semántico: qué número ve, si hay tachones, etc.

Rate limit: 40 req/min (NVIDIA NIM free tier).
"""
import os
import base64
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from pathlib import Path


# Modelos disponibles en NVIDIA NIM (verificados)
VLM_MODEL = "meta/llama-3.2-90b-vision-instruct"
VLM_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Rate limiter simple
_last_request_time = 0
_MIN_INTERVAL = 1.6  # segundos entre requests (~37 req/min, margen de seguridad)


def _get_api_key() -> str:
    """Obtiene la API key de NVIDIA NIM del entorno."""
    for key_name in ["NVIDIA_API_KEY_2", "NVIDIA_API_KEY_3", "NVIDIA_API_KEY"]:
        key = os.environ.get(key_name, "")
        if key.startswith("nvapi-"):
            return key
    raise RuntimeError("No NVIDIA API key found in environment (NVIDIA_API_KEY_2, _3)")


def _rate_limit():
    """Espera si es necesario para respetar el rate limit."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _call_vlm(base64_image: str, prompt: str, max_retries: int = 2) -> Dict[str, Any]:
    """
    Llama al VLM de NVIDIA NIM con una imagen y un prompt.

    Returns:
        {"ok": True, "response": str} o {"ok": False, "error": str}
    """
    api_key = _get_api_key()

    payload = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "max_tokens": 150,
        "temperature": 0.1
    }

    for attempt in range(max_retries + 1):
        _rate_limit()

        try:
            req = urllib.request.Request(
                VLM_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return {"ok": True, "response": content.strip()}

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")[:500]
            status = e.code

            if status == 429:
                if attempt < max_retries:
                    time.sleep(5)
                    continue
                return {"ok": False, "error": f"Rate limit exceeded: {error_body}"}

            return {"ok": False, "error": f"HTTP {status}: {error_body}"}

        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "Max retries exceeded"}


def analyze_cell_vlm(
    base64_image: str,
    cell_index: int,
    context: str = ""
) -> Dict[str, Any]:
    """
    Analiza una celda individual con VLM.

    Args:
        base64_image: Imagen de la celda en base64
        cell_index: Índice de la celda
        context: Contexto adicional (ej: "Acta de Turbo, candidato 1")

    Returns:
        {
            "cell_index": int,
            "digit_detected": str | None,
            "confidence": float,
            "anomalies": [str],
            "raw_response": str
        }
    """
    prompt = f"""Eres un auditor electoral colombiano analizando una celda de votación de un acta E-14.
Esta es una imagen recortada de UNA celda donde va escrito a mano un número de votos (1-3 dígitos).

{context}

Responde EXACTAMENTE en este formato JSON (sin markdown, sin explicación):
{{
  "digito": "el número que ves, o 'vacío' si no hay nada escrito",
  "confianza": 0.0 a 1.0,
  "anomalias": ["lista de anomalías: tachón, borrón, sobreescritura, doble trazo, mancha, trazo irregular"],
  "legible": true/false
}}"""

    result = _call_vlm(base64_image, prompt)

    if not result["ok"]:
        return {
            "cell_index": cell_index,
            "digit_detected": None,
            "confidence": 0.0,
            "anomalies": [],
            "raw_response": result.get("error", "Unknown error"),
            "vlm_error": True
        }

    raw = result["response"]

    # Intentar parsear JSON de la respuesta
    try:
        # Limpiar posibles markdown code blocks
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean[:-3]
        parsed = json.loads(clean)

        return {
            "cell_index": cell_index,
            "digit_detected": parsed.get("digito", ""),
            "confidence": float(parsed.get("confianza", 0)),
            "anomalies": parsed.get("anomalias", []),
            "legible": parsed.get("legible", False),
            "raw_response": raw,
            "vlm_error": False
        }
    except (json.JSONDecodeError, ValueError, KeyError):
        return {
            "cell_index": cell_index,
            "digit_detected": None,
            "confidence": 0.0,
            "anomalies": [],
            "raw_response": raw,
            "parse_error": True,
            "vlm_error": False
        }


def analyze_acta_vlm(
    cells: list,
    acta_context: str = "",
    max_cells: int = 5
) -> Dict[str, Any]:
    """
    Analiza las celdas más sospechosas de un acta con VLM.

    Solo envía las celdas con score más alto, para no exceder rate limits.

    Args:
        cells: Lista de celdas [{idx, scores, image_base64}]
        acta_context: "Acta Turbo_015, municipio Turbo"
        max_cells: Máximo de celdas a analizar (default 5)

    Returns:
        {
            "celdas_analizadas": int,
            "resultados": [{cell_index, digit_detected, confidence, anomalies}],
            "errores": int
        }
    """
    # Priorizar celdas con mayor score visual
    scored_cells = []
    for cell in cells:
        scores = cell.get("scores", {})
        score_global = scores.get("score_global", 0)
        scored_cells.append((score_global, cell))

    scored_cells.sort(key=lambda x: x[0], reverse=True)

    resultados = []
    errores = 0

    for score, cell in scored_cells[:max_cells]:
        b64 = cell.get("image_base64", "")
        if not b64:
            continue

        idx = cell.get("idx", cell.get("candidate_index", 0))
        cell_context = f"{acta_context}\nCelda #{idx + 1}. Score visual previo: {score:.2f}"

        result = analyze_cell_vlm(b64, idx, cell_context)

        if result.get("vlm_error") or result.get("parse_error"):
            errores += 1

        resultados.append(result)

    return {
        "celdas_analizadas": len(resultados),
        "resultados": resultados,
        "errores": errores
    }


# Test rápido
if __name__ == "__main__":
    # Prueba con una imagen de celda existente
    import sys

    img_path = Path(__file__).parent.parent.parent / "data" / "output" / "celdas"
    test_cell = img_path / "Anza_c0.png"

    if test_cell.exists():
        with open(test_cell, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        print("🧪 Probando VLM con celda Anza_c0...")
        result = analyze_cell_vlm(b64, 0, "Acta limpia de control")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Celda de prueba no encontrada: {test_cell}")
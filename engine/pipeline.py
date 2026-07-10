"""
Pipeline principal — Orquestador del motor de análisis E-14.
Flujo: PDF → Render → Segment → Analyze → Forensic → Output
"""
import json
import base64
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Agregar engine al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.render.pdf_renderer import PDFRenderer
from engine.segment.image_normalizer import ImageNormalizer
from engine.segment.layout_detector import LayoutDetector
from engine.segment.cell_extractor import CellExtractor
from engine.analyze.arithmetical import validate_arithmetical
from engine.analyze.visual_anomaly import analyze_all_cells_visual
from engine.forensic.rules_engine import classify_acta


class E14AnalysisPipeline:
    """Pipeline completo de análisis de actas E-14."""

    def __init__(self, dpi: int = 300, output_dir = None):
        self.dpi = dpi
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent.parent / "data" / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectorios
        self.renders_dir = self.output_dir / "renders"
        self.celdas_dir = self.output_dir / "celdas"
        self.json_dir = self.output_dir / "json"
        for d in [self.renders_dir, self.celdas_dir, self.json_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Módulos
        self.renderer = PDFRenderer(dpi=dpi)
        self.normalizer = ImageNormalizer()
        self.extractor = CellExtractor()

    def analyze_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Analiza un PDF E-14 y devuelve resultados completos.

        Returns:
            Dict con: mesa_key, filename, metadata, cells_scores,
                      score_components, veredicto, etc.
        """
        import cv2
        import numpy as np

        pdf_path = Path(pdf_path)

        # 1. Renderizar PDF → PNG
        metadata = self.renderer.get_metadata(pdf_path)
        image_paths = self.renderer.render(pdf_path, self.renders_dir)

        if not image_paths:
            raise RuntimeError(f"No se pudieron renderizar páginas de {pdf_path.name}")

        # 2. Procesar página 1 (tabla de votos)
        page1_img = cv2.imread(str(image_paths[0]))
        if page1_img is None:
            raise RuntimeError(f"No se pudo leer la imagen renderizada: {image_paths[0]}")

        # Normalizar
        norm_result = self.normalizer.process(page1_img)
        norm_img = norm_result["image"]

        # 3. Detectar regiones
        detector = LayoutDetector(norm_img.shape)
        regions = detector.detect_regions()

        # 4. Extraer celdas de la tabla de votos
        table_region = next(
            (r for r in regions if r.name == "tabla_votos"),
            None
        )

        all_cells = []
        if table_region:
            x, y, w, h = table_region.bbox_px
            table_img = norm_img[y:y + h, x:x + w]
            cells = self.extractor.extract_cells(table_img)

            # Guardar celdas
            for idx, cell_data in enumerate(cells):
                cell_id = f"{pdf_path.stem}_c{idx}"
                cell_path = self.celdas_dir / f"{cell_id}.png"
                cv2.imwrite(str(cell_path), cell_data["image"])

                all_cells.append({
                    "idx": idx,
                    "candidate_index": cell_data.get("candidate_index", idx),
                    "bbox_norm": cell_data.get("bbox_norm", []),
                    "bbox_px": cell_data.get("bbox_px", []),
                    "image": cell_data["image"],
                    "image_path": str(cell_path)
                })

        # 5. Análisis aritmético
        arith_result = validate_arithmetical(metadata, all_cells)

        # 6. Análisis visual de celdas
        visual_result = analyze_all_cells_visual(all_cells)

        # 6.5 OCR de celdas (opcional, si Tesseract está disponible)
        ocr_resultados = []
        try:
            from engine.analyze.ocr_tesseract import ocr_digit
            for cell in all_cells:
                ocr_r = ocr_digit(cell["image"])
                ocr_resultados.append({
                    "idx": cell["idx"],
                    "digit": ocr_r["digit"],
                    "confidence": ocr_r["confidence"],
                    "text_raw": ocr_r["text_raw"]
                })
        except Exception:
            ocr_resultados = []  # OCR no disponible, continuar sin

        # 7. Clasificación forense
        forensic = classify_acta(
            score_arithmetical=arith_result["score"],
            score_visual_promedio=visual_result["score_promedio"],
            score_visual_max=visual_result["score_max"],
            celdas_sospechosas=visual_result["celdas_sospechosas"],
            total_celdas=len(all_cells)
        )

        # 8. Preparar celdas para output (sin la imagen numpy)
        cells_output = []
        for cell in all_cells:
            cell_out = {
                "idx": cell["idx"],
                "bbox_norm": cell["bbox_norm"],
                "bbox_px": cell["bbox_px"],
                "image_path": cell["image_path"],
                "scores": next(
                    (cs["scores"] for cs in visual_result["cells_scores"]
                     if cs["idx"] == cell["idx"]),
                    {}
                )
            }
            # Convertir imagen a base64 para el dashboard
            if cell.get("image") is not None:
                _, buffer = cv2.imencode(".png", cell["image"])
                cell_out["image_base64"] = base64.b64encode(buffer).decode("utf-8")
            cells_output.append(cell_out)

        # 9. Extraer mesa_key del filename
        mesa_key = pdf_path.stem

        result = {
            "mesa_key": mesa_key,
            "filename": pdf_path.name,
            "metadata": {
                "pages": metadata["pages"],
                "page_dimensions": metadata.get("page_dimensions", []),
                "dpi": self.dpi,
                "rendered_at": datetime.now().isoformat()
            },
            "total_celdas": len(all_cells),
            "cells": cells_output,
            "score_components": forensic["componentes"],
            "score_global": forensic["score_global"],
            "veredicto": forensic["veredicto"],
            "arithmetical": arith_result,
            "visual_summary": {
                "score_promedio": visual_result["score_promedio"],
                "score_max": visual_result["score_max"],
                "celdas_sospechosas": visual_result["celdas_sospechosas"]
            },
            "analizado_en": datetime.now().isoformat(),
            "ocr": {
                "resultados": ocr_resultados,
                "tesseract_disponible": len(ocr_resultados) > 0
            }
        }

        # 10. Guardar JSON
        json_path = self.json_dir / f"{pdf_path.stem}.json"
        clean_result = _make_serializable(result)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(clean_result, f, indent=2, ensure_ascii=False)

        return clean_result


def _make_serializable(obj):
    """Convierte tipos numpy a tipos Python nativos para serialización JSON."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# CLI para pruebas rápidas
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline de análisis E-14")
    parser.add_argument("pdf", help="Ruta al PDF E-14 a analizar")
    parser.add_argument("--dpi", type=int, default=300, help="DPI de renderizado")
    args = parser.parse_args()

    pipeline = E14AnalysisPipeline(dpi=args.dpi)
    result = pipeline.analyze_pdf(Path(args.pdf))

    print(f"\n{'='*60}")
    print(f"RESULTADO: {result['veredicto']}")
    print(f"Score global: {result['score_global']}")
    print(f"Celdas: {result['total_celdas']}")
    print(f"Discrepancias aritméticas: {result['arithmetical']['discrepancias']}")
    print(f"Scores visuales: prom={result['visual_summary']['score_promedio']}, "
          f"max={result['visual_summary']['score_max']}")
    print(f"JSON guardado en: {pipeline.json_dir / Path(args.pdf).stem}.json")
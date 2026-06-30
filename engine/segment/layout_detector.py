"""
Layout Detector — Detecta regiones estructurales del E-14.
"""
import cv2
import numpy as np
from typing import List, Tuple, Dict
from dataclasses import dataclass, asdict


@dataclass
class Region:
    """Representa una región estructural del E-14."""
    name: str
    bbox_norm: Tuple[float, float, float, float]  # x, y, w, h (0-1)
    bbox_px: Tuple[int, int, int, int]           # x, y, w, h (pixels)
    confidence: float
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "bbox_norm": list(self.bbox_norm),
            "bbox_px": list(self.bbox_px),
            "confidence": self.confidence
        }


class LayoutDetector:
    """
    Detecta las regiones principales del formulario E-14.
    Basado en proporciones normalizadas extraídas del inventario documental.
    """
    
    def __init__(self, image_shape: Tuple[int, int]):
        self.height, self.width = image_shape[:2]
        self.regions = self._define_regions()
    
    def _define_regions(self) -> Dict[str, Tuple[float, float, float, float]]:
        """Define regiones basadas en proporciones normalizadas del inventario."""
        return {
            "encabezado": (0.00, 0.00, 0.95, 0.15),
            "tabla_votos": (0.05, 0.20, 0.90, 0.35),
            "totales": (0.05, 0.55, 0.90, 0.10),
            "zona_intermedia": (0.05, 0.65, 0.90, 0.10),
            "firmas": (0.05, 0.75, 0.90, 0.25),
        }
    
    def detect_regions(self) -> List[Region]:
        """Genera objetos Region con coordenadas en pixels."""
        regions = []
        for name, (x, y, w, h) in self.regions.items():
            bbox_px = (
                int(x * self.width),
                int(y * self.height),
                int(w * self.width),
                int(h * self.height)
            )
            regions.append(Region(name, (x, y, w, h), bbox_px, confidence=0.95))
        return regions
    
    def detect_table_columns(self, table_image: np.ndarray) -> Dict[str, Tuple[float, float, float, float]]:
        """
        Detecta las 3 columnas principales de la tabla de votos:
        candidato, partido, votos.
        """
        h, w = table_image.shape[:2]
        return {
            "candidato": (0.02, 0.00, 0.50, 1.00),  # ~50% izquierda
            "partido": (0.52, 0.00, 0.25, 1.00),   # ~25% centro
            "votos": (0.65, 0.00, 0.35, 1.00),     # ~35% derecha (columna objetivo)
        }
    
    def extract_region(self, image: np.ndarray, region: Region) -> np.ndarray:
        """Extrae la subimagen de una región."""
        x, y, w, h = region.bbox_px
        return image[y:y+h, x:x+w]


if __name__ == "__main__":
    # Prueba con una imagen renderizada
    from pathlib import Path
    import cv2
    
    img_path = Path("/home/sebas/proyectos/e14-audit-platform/fase_a_segmentacion/data/output/regiones/Anza_p1.png")
    if img_path.exists():
        image = cv2.imread(str(img_path))
        detector = LayoutDetector(image.shape)
        regions = detector.detect_regions()
        
        print(f"Detectadas {len(regions)} regiones:")
        for r in regions:
            print(f"  {r.name}: px={r.bbox_px}")

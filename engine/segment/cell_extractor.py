"""
Cell Extractor — Extrae celdas individuales de la tabla de votos.
"""
import cv2
import numpy as np
from typing import List, Tuple
from pathlib import Path


class CellExtractor:
    """Extrae celdas de votos de la columna derecha de la tabla."""
    
    def __init__(self):
        # Columna de votos: 62% - 82% del ancho de la tabla
        self.votes_col_start = 0.62
        self.votes_col_end = 0.82
    
    def detect_rows(self, table_image: np.ndarray, min_row_height: int = 20) -> List[Tuple[int, int]]:
        """
        Detecta filas en la tabla usando análisis de proyección horizontal.
        
        Returns:
            Lista de tuplas (y_start, y_end) para cada fila.
        """
        if len(table_image.shape) == 3:
            gray = cv2.cvtColor(table_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = table_image
        
        # Proyección horizontal: contar píxeles oscuros por fila
        proj = np.sum(gray < 180, axis=1)
        
        # Detectar filas con contenido usando diferencias
        rows_with_content = np.where(proj > np.mean(proj) * 0.5)[0]
        
        if len(rows_with_content) == 0:
            return []
        
        # Agrupar filas consecutivas
        rows = []
        start = rows_with_content[0]
        prev = rows_with_content[0]
        
        for y in rows_with_content[1:]:
            if y - prev > min_row_height:
                end = prev
                if end - start >= min_row_height:
                    rows.append((start, end))
                start = y
            prev = y
        
        # Agregar último grupo
        if prev - start >= min_row_height:
            rows.append((start, prev))
        
        return rows
    
    def extract_cells(self, table_image: np.ndarray) -> List[dict]:
        """
        Extrae celdas de la columna de votos.
        
        Returns:
            Lista de dicts con keys: image, bbox_norm, bbox_px
        """
        h, w = table_image.shape[:2]
        
        # Detectar filas
        rows = self.detect_rows(table_image)
        
        if not rows:
            # Fallback: dividir en filas iguales (estimación)
            n_candidatos = 8  # Estándar E-14
            row_h = h // n_candidatos
            rows = [(i * row_h, (i + 1) * row_h) for i in range(n_candidatos)]
        
        # Columna de votos
        x_start = int(self.votes_col_start * w)
        x_end = int(self.votes_col_end * w)
        
        cells = []
        for idx, (y_start, y_end) in enumerate(rows):
            cell = table_image[y_start:y_end, x_start:x_end]
            
            cells.append({
                "image": cell,
                "candidate_index": idx,
                "bbox_norm": [self.votes_col_start, y_start / h, 
                             (self.votes_col_end - self.votes_col_start), (y_end - y_start) / h],
                "bbox_px": [x_start, y_start, x_end - x_start, y_end - y_start]
            })
        
        return cells


if __name__ == "__main__":
    # Prueba
    import cv2
    from pathlib import Path
    
    img_path = Path("/home/sebas/proyectos/e14-audit-platform/fase_a_segmentacion/data/output/regiones/Anza_p1.png")
    if img_path.exists():
        image = cv2.imread(str(img_path))
        
        # Simular tabla (extraer región 20-55% de altura)
        h, w = image.shape[:2]
        table = image[int(h * 0.20):int(h * 0.55), :]
        
        extractor = CellExtractor()
        cells = extractor.extract_cells(table)
        
        print(f"Celdas extraídas: {len(cells)}")
        for cell in cells:
            print(f"  Candidato {cell['candidate_index']}: {cell['bbox_px']}")

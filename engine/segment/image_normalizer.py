"""
Image Normalizer — Corrección de rotación, perspectiva y tamaño.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Tuple


class ImageNormalizer:
    """Normaliza imágenes de actas E-14 a formato estándar."""
    
    STANDARD_WIDTH = 3609   # Ancho a 300 DPI
    STANDARD_HEIGHT = 10730 # Alto a 300 DPI
    
    def __init__(self):
        pass
    
    def detect_rotation(self, image: np.ndarray) -> float:
        """Detecta ángulo de rotación usando Hough Transform."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Detectar bordes
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=200, maxLineGap=10)
        
        if lines is None or len(lines) < 5:
            return 0.0
        
        # Calcular ángulos de líneas horizontales
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            if dx > 50 and dy < dx * 0.5:  # Líneas casi horizontales
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                if abs(angle) < 3:  # Solo rotaciones menores a 3 grados
                    angles.append(angle)
        
        if not angles:
            return 0.0
        
        # Mediana robusta contra outliers
        median_angle = np.median(angles)
        return round(median_angle, 2)
    
    def deskew(self, image: np.ndarray, angle: float = None) -> np.ndarray:
        """Corrige rotación detectada."""
        if angle is None:
            angle = self.detect_rotation(image)
        
        if abs(angle) < 0.1:
            return image  # Sin corrección necesaria
        
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Calcular nuevo tamaño para no perder contenido
        cos_angle = abs(np.cos(np.radians(angle)))
        sin_angle = abs(np.sin(np.radians(angle)))
        new_w = int(w * cos_angle + h * sin_angle)
        new_h = int(w * sin_angle + h * cos_angle)
        
        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2
        
        rotated = cv2.warpAffine(image, M, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated
    
    def normalize_size(self, image: np.ndarray) -> np.ndarray:
        """Escala la imagen al tamaño estándar E-14."""
        return cv2.resize(image, (self.STANDARD_WIDTH, self.STANDARD_HEIGHT), interpolation=cv2.INTER_LANCZOS4)
    
    def process(self, image: np.ndarray) -> dict:
        """
        Pipeline completo de normalización.
        
        Returns:
            dict con la imagen normalizada y metadatos del proceso
        """
        original_shape = image.shape
        
        # 1. Corrección de rotación
        angle = self.detect_rotation(image)
        if abs(angle) > 0.1:
            image = self.deskew(image, angle)
        
        # 2. Normalización de tamaño
        image = self.normalize_size(image)
        
        return {
            "image": image,
            "rotation_corrected": round(angle, 2),
            "original_shape": original_shape,
            "final_shape": image.shape,
            "aspect_ratio_preserved": abs((image.shape[1] / image.shape[0]) - (self.STANDARD_WIDTH / self.STANDARD_HEIGHT)) < 0.01
        }

"""
PDF Renderer — Convierte PDF E-14 a imagen PNG alta resolución.
Mantiene metadatos de origen del documento.
"""
import fitz
from pathlib import Path
from typing import List, Tuple, Dict, Any
import json


class PDFRenderer:
    """Renderiza páginas de PDF a imágenes PNG de alta resolución."""
    
    def __init__(self, dpi: int = 300):
        self.dpi = dpi
        self.zoom = dpi / 72.0
    
    def render(self, pdf_path: Path, output_dir: Path) -> List[Path]:
        """
        Renderiza todas las páginas del PDF a PNG.
        
        Args:
            pdf_path: Ruta al archivo PDF
            output_dir: Directorio de salida para los PNG
            
        Returns:
            Lista de rutas de imágenes generadas
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        doc = fitz.open(str(pdf_path))
        output_paths = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=mat)
            
            output_path = output_dir / f"{pdf_path.stem}_p{page_num+1}.png"
            pix.save(str(output_path))
            output_paths.append(output_path)
        
        doc.close()
        return output_paths
    
    def get_metadata(self, pdf_path: Path) -> Dict[str, Any]:
        """Extrae metadatos del PDF incluyendo dimensiones y fuente."""
        doc = fitz.open(str(pdf_path))
        meta = {
            "filename": pdf_path.name,
            "filepath": str(pdf_path),
            "pages": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "dpi_render": self.dpi,
        }
        
        # Extraer dimensionesDepths de cada página
        page_dims = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_dims.append({
                "page": page_num + 1,
                "width": page.rect.width,
                "height": page.rect.height
            })
        meta["page_dimensions"] = page_dims
        
        doc.close()
        return meta


def render_pdf_directory(input_dir: Path, output_dir: Path, dpi: int = 300) -> Dict[str, Any]:
    """
    Renderiza todos los PDFs de un directorio.
    
    Returns:
        Dict con estadísticas del proceso: {"rendered": int, "errors": int, "files": list}
    """
    renderer = PDFRenderer(dpi=dpi)
    pdf_files = list(input_dir.glob("*.pdf"))
    
    results = {
        "rendered": 0,
        "errors": 0,
        "files": []
    }
    
    for pdf_file in pdf_files:
        try:
            metadata = renderer.get_metadata(pdf_file)
            image_paths = renderer.render(pdf_file, output_dir)
            
            results["files"].append({
                "pdf": str(pdf_file),
                "metadata": metadata,
                "images": [str(p) for p in image_paths]
            })
            results["rendered"] += 1
        except Exception as e:
            results["errors"] += 1
            results["files"].append({
                "pdf": str(pdf_file),
                "error": str(e)
            })
    
    return results


if __name__ == "__main__":
    # Renderizar PDFs de muestra
    PROJECT = Path("/home/sebas/proyectos/e14-audit-platform")
    PDF_DIR = PROJECT / "data/pdf_muestra"
    PDF_DIR_ADD = PROJECT / "data/pdf_adicionales"
    OUTPUT_DIR = PROJECT / "fase_a_segmentacion/data/output"
    
    print("PDF Renderer — Prueba con Anza.pdf")
    renderer = PDFRenderer(dpi=300)
    
    # Renderizar Anza.pdf
    anza_pdf = PDF_DIR / "Anza.pdf"
    if anza_pdf.exists():
        meta = renderer.get_metadata(anza_pdf)
        print(f"📄 {meta['filename']}")
        print(f"   Páginas: {meta['pages']}")
        
        image_paths = renderer.render(anza_pdf, OUTPUT_DIR / "regiones")
        for path in image_paths:
            print(f"   📸 Guardado: {path.name}")
    else:
        print("❌ Anza.pdf no encontrado")

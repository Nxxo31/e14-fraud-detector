# E14 Audit Platform — Arquitectura MVC v2
## Documento de diseño (pre-implementación)
### Fecha: 2026-06-26

---

## 1. OBJETIVO

Refactorizar el código disperso del repositorio E14 Audit Platform en una arquitectura MVC limpia y funcional, reutilizando los módulos existentes que sí funcionan y eliminando el código inerte.

## 2. PRINCIPIOS

1. **Mínimo viable**: Solo instalar dependencias que realmente se usan (fitz, cv2, numpy)
2. **Reutilizar, no reescribir**: Los módulos de fase_a_segmentacion ya funcionan y se integran tal cual
3. **Arranque inmediato**: El sistema debe poder procesar un PDF hoy, no después de 3 sprints
4. **Separación real**: Cada capa MVC vive en su propio directorio y tiene contratos explícitos
5. **Sin dead code**: Todo lo que no se integre en MVC se archiva en `_legacy/`

---

## 3. ARQUITECTURA MVC

```
┌──────────────────────────────────────────────────────┐
│                    USUARIO                            │
│                 (Browser / CLI)                       │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP / subprocess
                       ▼
┌──────────────────────────────────────────────────────┐
│                  CONTROLLER                           │
│                   api/                                │
│                                                       │
│  FastAPI REST API                                     │
│  ┌─────────────────────────────────────────────┐     │
│  │ GET  /actas              → lista actas       │     │
│  │ POST /actas/analizar     → subir PDF + analizar │  │
│  │ GET  /actas/{id}         → detalle acta       │     │
│  │ PUT  /actas/{id}/veredicto → marcar legítima/ilegítima │
│  │ GET  /dashboard/stats    → estadísticas        │     │
│  │ GET  /celdas/{acta_id}   → celdas extraídas    │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  Persistencia: SQLite (e14_audit.db)                  │
└──────────┬───────────────────────────┬───────────────┘
           │                           │
           ▼                           ▼
┌──────────────────────┐    ┌──────────────────────────┐
│       MODEL          │    │         VISTA             │
│     engine/          │    │     dashboard/            │
│                      │    │                           │
│  Motor de análisis:  │    │  HTML+JS autónomo         │
│  ┌────────────────┐  │    │  ┌─────────────────────┐  │
│  │ render/        │  │    │  │ index.html           │  │
│  │  pdf_renderer  │  │    │  │  - Lista de actas    │  │
│  ├────────────────┤  │    │  │  - Stats (legítimas  │  │
│  │ segment/       │  │    │  │    vs ilegítimas)    │  │
│  │  layout_detect │  │    │  │  - Formulario upload │  │
│  │  cell_extract  │  │    │  │  - Visor de celdas   │  │
│  ├────────────────┤  │    │  └─────────────────────┘  │
│  │ analyze/       │  │    │                           │
│  │  arithmetical  │  │    │  Consume la API           │
│  │  visual_anomaly│  │    │  (fetch a /actas, etc.)   │
│  ├────────────────┤  │    │                           │
│  │ forensic/      │  │    │                           │
│  │  rules_engine  │  │    │                           │
│  └────────────────┘  │    │                           │
└──────────────────────┘    └──────────────────────────┘
```

### Contratos (interfaces entre capas)

**Modelo → Controlador:**
```python
# engine/pipeline.py
def analyze_pdf(pdf_path: Path) -> dict:
    """Procesa un PDF y devuelve dict con: metadatos, celdas, scores, veredicto"""
    return {
        "mesa_key": "01-034-01-001-000",
        "filename": "Anza.pdf",
        "departamento": "01",
        "municipio": "034",
        "celdas": [{"idx": 0, "bbox_norm": [...], "scores": {...}, "image_base64": "..."}],
        "score_global": 0.58,
        "veredicto": "LEGITIMA"  # LEGITIMA | SOSPECHOSA | ILEGITIMA
    }
```

**Controlador → Vista:**
```json
// GET /actas → [{id, mesa_key, filename, score_global, veredicto, fecha_analisis}]
// GET /actas/{id} → {id, mesa_key, ... celdas: [{idx, scores, image_base64}], veredicto}
// GET /dashboard/stats → {total, legitimas, sospechosas, ilegítimas, pendientes}
```

---

## 4. ESTRUCTURA DE DIRECTORIOS (post-refactor)

```
e14-audit-platform/
├── api/                          # CONTROLLER
│   ├── main.py                   # FastAPI app + endpoints
│   ├── database.py               # SQLite connection (nuevo, compartido con engine si es necesario)
│   └── requirements.txt          # fastapi, uvicorn
│
├── engine/                       # MODEL
│   ├── __init__.py
│   ├── pipeline.py               # Orquestador: render → segment → analyze → score
│   ├── render/
│   │   └── pdf_renderer.py       # ← Migrado de fase_a_segmentacion/src/render/
│   ├── segment/
│   │   ├── layout_detector.py    # ← Migrado de fase_a_segmentacion/src/detect/
│   │   └── cell_extractor.py     # ← Migrado de fase_a_segmentacion/src/extract/
│   ├── analyze/
│   │   ├── arithmetical.py       # ← Adaptado de fase2/validar_muestra.py
│   │   └── visual_anomaly.py     # ← Adaptado de fase4/capa1_opencv.py
│   └── forensic/
│       └── rules_engine.py       # Scoring + clasificación LEGITIMA/SOSPECHOSA/ILEGITIMA
│
├── dashboard/                    # VISTA
│   ├── index.html                # Dashboard autónomo (fetch a /actas, etc.)
│   └── static/
│       └── (CSS/JS inline en HTML para simplicidad)
│
├── data/
│   ├── e14_audit.db              # SQLite database (existente)
│   ├── pdf_muestra/              # PDFs de entrada (existente)
│   └── output/                   # Imágenes + JSON generados (nueva ubicación unificada)
│       ├── renders/              # PNGs renderizados
│       ├── celdas/               # Recortes de celda
│       └── json/                 # Resultados JSON por acta
│
├── _legacy/                      # Código no integrado (archivado, no eliminado)
│   ├── acquisition/
│   ├── analysis/
│   ├── fase2/
│   ├── fase3/
│   ├── fase4/
│   ├── calibration/
│   ├── mvp/
│   └── scripts/
│
├── schema_sqlite.sql             # Mantener
├── schema_postgresql.sql         # Mantener
├── PROJECT.md                    # Actualizar post-refactor
└── README.md                     # Nuevo: cómo ejecutar el sistema
```

---

## 5. PLAN DE MIGRACIÓN (orden de implementación)

### Paso 1: Instalar dependencias mínimas
```bash
pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn
```
Esto es todo lo necesario. Sin PaddleOCR, sin Celery, sin Redis, sin MinIO.

### Paso 2: Crear engine/ (MODEL)
- Migrar `pdf_renderer.py` → `engine/render/`
- Migrar `layout_detector.py` → `engine/segment/`
- Migrar `cell_extractor.py` → `engine/segment/`
- Crear `engine/analyze/arithmetical.py` (validación de sumas)
- Crear `engine/analyze/visual_anomaly.py` (adaptado de capa1_opencv.py)
- Crear `engine/forensic/rules_engine.py` (scoring + clasificación)
- Crear `engine/pipeline.py` (orquestador)

### Paso 3: Crear api/ (CONTROLLER)
- FastAPI con 6 endpoints
- Conexión a SQLite
- Llamadas a engine.pipeline.analyze_pdf()

### Paso 4: Crear dashboard/ (VISTA)
- HTML+JS autónomo
- Fetch a la API
- Tabla de actas + formulario upload + visor de celdas

### Paso 5: Mover código legacy a _legacy/
### Paso 6: Probar end-to-end con un PDF real
### Paso 7: Actualizar PROJECT.md

---

## 6. REGLAS FORENSES (motor de clasificación)

El `engine/forensic/rules_engine.py` implementa:

```
score_global = 0.25 * score_arithmetical + 0.25 * score_visual + 0.50 * score_celdas

Clasificación:
  score_global < 0.30  → LEGITIMA
  0.30 ≤ score < 0.60  → SOSPECHOSA
  score_global ≥ 0.60  → ILEGITIMA
```

**score_arithmetical:** Suma de votos = total reportado. Diferencia > 0 → score += 0.5
**score_visual:** Anomalías en celdas (grosor, tinta, separador). Promedio de los 3 scores.
**score_celdas:** Variabilidad entre celdas del mismo candidato (desviación estándar de densidad).

Nota: La Capa 1 actual produce muchos falsos positivos. El peso de score_visual es solo 0.25 para mitigar esto. A futuro, cuando tengamos OCR funcionando, score_arithmetical pasará a ser el dominante.

---

## 7. LO QUE NO SE INCLUYE (por ahora)

- **Capa 2 (VLM NIM):** Se integrará como etapa opcional post-MVP
- **OCR (Tesseract/TrOCR):** Bloqueado hasta tener sudo o instalar alternativas
- **Supabase:** SQLite es suficiente para el MVP local
- **Celery/Redis:** Procesamiento secuencial para MVP
- **acquisition/ y analysis/:** Archivados en _legacy/
- **Docker:** No necesario para MVP de escritorio

---

## 8. CONTRATO DE DATOS

### Tabla actas (ya existe en e14_audit.db)
```sql
actas_oficiales (
    id INTEGER PRIMARY KEY,
    mesa_key TEXT UNIQUE,
    departamento TEXT,
    municipio TEXT,
    filename TEXT,
    score_global REAL,
    score_arithmetical REAL,
    score_visual REAL,
    score_celdas REAL,
    veredicto TEXT,  -- LEGITIMA | SOSPECHOSA | ILEGITIMA
    celdas_json TEXT, -- JSON array de celdas con scores
    metadata_json TEXT, -- Metadatos del PDF
    fecha_analisis TEXT,
    revisado_por TEXT,
    fecha_revision TEXT
)
```

La tabla existente `actas_oficiales` se extiende con columnas adicionales vía ALTER TABLE (SQLite lo soporta).

---

*Fin del documento de diseño. Proceder a implementación.*
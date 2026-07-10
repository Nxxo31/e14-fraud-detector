# E14 Audit Platform — Quick Start

## Requisitos
- Python 3.14+
- pip (incluido en el venv)

## Instalación

```bash
cd ~/proyectos/e14-audit-platform

# Activar venv (ya tiene pip)
source venv/bin/activate  # o usar ./venv/bin/python directamente

# Instalar dependencias
./venv/bin/pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn
```

## Ejecutar

### Dashboard completo

```bash
# Iniciar servidor API
./venv/bin/python api/main.py

# Abrir en el navegador:
# http://localhost:8700/dashboard
```

### Pipeline desde CLI

```bash
# Analizar un PDF
./venv/bin/python engine/pipeline.py data/pdf_muestra/Anza.pdf

# Analizar otro PDF
./venv/bin/python engine/pipeline.py data/pdf_muestra/Turbo_015.pdf
```

### API directa

```bash
# Health check
curl http://localhost:8700/

# Listar actas
curl http://localhost:8700/actas

# Subir y analizar PDF
curl -X POST -F "file=@data/pdf_muestra/Anza.pdf" http://localhost:8700/actas/analizar

# Ver detalle de acta
curl http://localhost:8700/actas/1

# Actualizar veredicto
curl -X PUT "http://localhost:8700/actas/1/veredicto?veredicto=LEGITIMA"

# Estadísticas
curl http://localhost:8700/dashboard/stats
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | / | Health check |
| GET | /actas | Listar actas (?veredicto=LEGITIMA) |
| POST | /actas/analizar | Subir y analizar PDF (multipart) |
| GET | /actas/{id} | Detalle de acta |
| PUT | /actas/{id}/veredicto | Actualizar veredicto |
| GET | /celdas/{id} | Celdas del acta (con imágenes) |
| GET | /dashboard/stats | Estadísticas |
| GET | /dashboard | Dashboard HTML |

## Estructura

```
e14-audit-platform/
├── api/              # CONTROLLER — FastAPI REST
│   ├── main.py       # App + endpoints
│   └── database.py   # SQLite CRUD
├── engine/           # MODEL — Motor de análisis
│   ├── pipeline.py   # Orquestador
│   ├── render/       # PDF → PNG
│   ├── segment/      # Layout + celdas
│   ├── analyze/      # Aritmética + visual
│   └── forensic/     # Clasificación
├── dashboard/        # VISTA — HTML+JS
│   └── index.html
├── data/             # PDFs, DB, outputs
└── _legacy/          # Código anterior archivado
```
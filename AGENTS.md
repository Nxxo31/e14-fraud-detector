# e14-audit-platform — Contexto del agente

## Proyecto
Prototipo de auditoría ciudadana de actas electorales E-14 de Colombia.
Procesa PDFs de muestra (5-18 actas). Repo de escala: e14-auditoria (122k actas).

## Stack
- Python 3.14 + venv en ./venv/
- Framework: FastAPI + uvicorn (puerto 8700)
- Análisis: PyMuPDF + OpenCV + Tesseract + NVIDIA NIM VLM
- DB: SQLite (local) + Supabase PostgreSQL (producción)
- Arquitectura: MVC — engine/ (MODEL) / api/ (CONTROLLER) / dashboard/ (VIEW)

## Comandos
- API: `./venv/bin/python api/main.py`
- Pipeline CLI: `./venv/bin/python engine/pipeline.py data/pdf_muestra/Anza.pdf`
- Instalar deps: `./venv/bin/pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn`

## Estado actual (2026-06-26)
- ✅ F1-F4 completadas (DB, aritmética, workers, OpenCV)
- ✅ Capa 2 VLM integrada (llama-3.2-90b-vision via NVIDIA NIM)
- ✅ Batch processing (18 muestras, 0 errores)
- ⬜ F5+ pendientes (ingesta ciudadana, comparación, dashboard público)

## Reglas críticas
- Coordenadas normalizadas (0-1) SIEMPRE — coordenadas fijas en píxeles RECHAZADAS
- Capa 1 (OpenCV) analiza SOLO firmas — nunca números ni texto
- NVIDIA NIM: 3 API keys rotadas, límite ~37 req/min
- Credenciales Supabase SOLO en variables de entorno — nunca en archivos .md

## Loop de trabajo
1. `cat CURRENT_TASK.md` → ejecutar tarea
2. Activar venv: `source venv/bin/activate`
3. Commit atómico en español → push inmediato

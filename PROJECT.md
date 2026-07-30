# E-14 — Auditoría Ciudadana de Actas E-14 (Colombia)

**Última actualización:** 2026-07-30
**Estado:** 🟢 ACTIVO — F5 integrado, avanzando a F6. Limitación de calibración aceptada.
**Repositorio:** https://github.com/Nxxo31/e14-fraud-detector.git
**License:** MIT

---

## Proyecto

Plataforma de auditoría ciudadana de actas electorales E-14 de Colombia.
Pipeline multi-capa: ingesta de PDFs → validación aritmética → visión por computador → VLM → comparación oficial vs ciudadano → dashboard público.

**Alcance:** 5-18 actas de muestra (prototipo). Arquitectura escalable a 122K actas.

---

## Stack

| Capa | Tecnología | Estado |
|------|-----------|--------|
| Lenguaje | Python 3.14 + venv (`venv/`) | ✅ Operativo |
| Framework API | FastAPI + uvicorn (puerto 8700) | ✅ Operativo |
| Parser PDF | PyMuPDF (fitz) | ✅ Operativo |
| Visión (Capa 1) | OpenCV + numpy | ✅ Operativo |
| VLM (Capa 2) | NVIDIA NIM (llama-3.2-90b-vision) | ✅ Integrado |
| DB local | SQLite (`data/e14_audit.db`) | ✅ Operativo |
| DB producción | Supabase PostgreSQL | ✅ Conectado |
| OCR | Tesseract | ✅ Integrado |
| QR/Barcode | pyzbar | ⬜ Pendiente |
| Frontend/Dashboard | — | ⬜ Pendiente |

---

## Estado de Fases

| Fase | Descripción | Estado | Detalles |
|------|-------------|--------|----------|
| F1 | Base de datos + Supabase | ✅ Completada | 11 tablas, 2 views, triggers, 5 actas migradas |
| F2 | Capa 0 — validación aritmética | ✅ Completada | 7 discrepancias (excede_total, no_coincide, nivelacion, firmas) |
| F3 | Cola de slots + workers concurrentes | ✅ Completada | Worker pool paralelo validado, 0 colisiones |
| F4 | Capa 1 — visión por computador (OpenCV) | ✅ Completada | 3 scores: grosor, separador, tinta. 30 discrepancias 'trazo_anomalo' |
| F5 | Capa 2 — VLM dirigido (NVIDIA NIM) | ✅ Integrado | Batch processing 18 muestras, 0 errores. Pendiente: separar scores > 0.6 |
| F6 | Ingesta de evidencia ciudadana | ⬜ Pendiente | Endpoint para subir fotos + Capa 1/2 |
| F7 | Motor comparación oficial vs ciudadano | ⬜ Pendiente | Generar discrepancias 'discrepancia_oficial_vs_ciudadano' |
| F8 | Flujo de verificación ciudadana (consenso) | ⬜ Pendiente | Endpoint votos + trigger consenso |
| F9 | Dashboard público (3 vistas) | ⬜ Pendiente | Mapa, mesas legítimas, cola verificación |
| F10 | Panel admin + exportación impugnaciones | ⬜ Pendiente | Vista admin + PDF exportable |

---

## Supabase

- **Project:** `oawxinjygprnftkgcjyr` (E-14)
- **11 tablas + 2 views**
- **5 actas migradas**
- **37 discrepancias totales:**
  - Capa 0 (aritmética): 7
  - Capa 1 (visión): 30

## Resultados Capa 1 (OpenCV)

Scores por acta (votos_candidato_1):
- Anza (clean): 0.58 ✅
- Turbo 015 (controversial): 0.70 ⚠️
- Turbo 001 (nivelación+faltan firmas): 0.70 ⚠️
- Turbo 002 (trazo_grueso reportado): 0.70 ⚠️
- Turbo 006 (clean): 0.70 ⚠️

**Limitación conocida:** Las coordenadas de celdas son aproximadas. Los scores actúan como señal de dirección, no como verdad absoluta. Necesita calibración manual para precisión real.

## Bloqueo resuelto: Calibración visual — Decisión 2026-07-30

**Decisión:** Aceptar los scores de Capa 1 como señal de dirección, no como verdad absoluta.
La limitación de coordenadas aproximadas está documentada y no bloquea F6+.
Los scores de Capa 1 (grosor, separador, tinta) funcionan como heurística de priorización
para el VLM (Capa 2), no como evidencia definitiva. Avanzar a F6 (ingesta ciudadana).

---

## Datos de muestra

5 PDFs E-14 en `data/pdf_muestra/`:

| Archivo | Mesa | Municipio |
|---------|------|-----------|
| Anza.pdf | 01-034-01-001-000 | Anzá |
| Turbo_015.pdf | 01-280-00-000-015 | Turbo |
| Turbo_001.pdf | 01-280-00-000-001 | Turbo |
| Turbo_002.pdf | 01-280-00-000-002 | Turbo |
| Turbo_006.pdf | 01-280-00-000-006 | Turbo |

## Archivos clave

- `schema_sqlite.sql` — Esquema SQLite
- `schema_postgresql.sql` — Schema completo PostgreSQL (11 tablas + views + triggers)
- `create_db.py` — Script para crear la base de datos
- `seed_data.py` — Script para poblar datos de muestra
- `pipeline_fraude.py` — Orquestador principal del pipeline
- `fase4/capa1_opencv.py` — Pipeline de visión por computador con OpenCV
- `fase4/deteccion_dinamica.py` — Detección dinámica de celdas
- `fase4/ocr_anchor.py` — OCR con anclas
- `generate_discrepancias_supabase.py` — Generación de discrepancias Capa 0
- `migrate_data_supabase.py` — Migración SQLite → Supabase
- `ingestion/` — Servicios de cola, descarga, rate limiting
- `acquisition/` — Microservicio Docker (routers para PDFs y tablas)
- `scripts/` — Utilidades (generate_report, validate_pipeline, calibrate_capa1, run_vlm_batch)

## Decisiones de diseño

1. **SQLite para dev, PostgreSQL/Supabase paraprod** — No se pudo instalar PostgreSQL local (requiere sudo). Schema adaptado con tipos SQLite. Migración a PostgreSQL planificada para producción.

2. **Código de departamento DIVIPOLA** — Antioquia = código 01. Anzá = 034, Turbo = 280.

3. **Formato mesa_key** — `{depto}-{municipio}-{zona}-{puesto}-{mesa}` con zero-padding (3 dígitos municipio/mesa, 2 dígitos puesto).

4. **Coordenadas normalizadas (0-1) SIEMPRE** — Coordenadas fijas en píxeles RECHAZADAS.

5. **Capa 1 analiza SOLO firmas** — Nunca números ni texto.

6. **NVIDIA NIM: 3 API keys rotadas** — Límite ~37 req/min.

---

## Reglas críticas

- Coordenadas normalizadas (0-1) SIEMPRE — coordenadas fijas en píxeles RECHAZADAS
- Capa 1 (OpenCV) analiza SOLO firmas — nunca números ni texto
- NVIDIA NIM: 3 API keys rotadas, límite ~37 req/min
- Credenciales Supabase SOLO en variables de entorno — nunca en archivos
- Commit atómico en español → push inmediato

## Comandos

- API: `./venv/bin/python api/main.py`
- Pipeline CLI: `./venv/bin/python engine/pipeline.py data/pdf_muestra/Anza.pdf`
- Instalar deps: `./venv/bin/pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn`
- Activar venv: `source venv/bin/activate`

---

## Historial

- **2026-07-29:** Fusión de e14-audit-platform y e14-fraud-detector en un único repositorio. Proyecto pausado.
- **2026-07-02:** Fases F1-F4 completadas, Supabase conectado, 37 discrepancias generadas.
- **2026-06-29:** Capa 1 OpenCV con detección dinámica y OCR anchor.
- **2026-06-22:** F1 completada, schema SQLite + PostgreSQL, 5 actas de muestra.

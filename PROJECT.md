# PROJECT.md — E-14 Fraud Detector

> **Estado:** Activo | **Versión:** 0.3.0 | **Última actualización:** 2026-07-31

---

## 🎯 Objetivo Principal

Auditoría forense ciudadana de actas electorales E-14 de Colombia mediante un pipeline multi-capa: ingesta de PDFs → validación aritmética → visión por computador (OpenCV) → VLM dirigido → comparación oficial vs ciudadano → dashboard público.

## 🎯 Objetivos Secundarios

1. Detectar discrepancias aritméticas (Capa 0): totales inconsistentes, firmas faltantes, nivelación fraudulenta
2. Detectar anomalías visuales en firmas (Capa 1): grosor de trazo, separador entre firmas, tinta anómala
3. Validar con VLM dirigido (Capa 2): NVIDIA NIM llama-3.2-90b-vision para inspección de zonas sospechosas
4. Ingesta ciudadana: endpoint para subir fotos de actas y reproducir Capas 0-2
5. Motor de comparación oficial vs ciudadano y consenso democrático
6. Dashboard público con mapa de mesas, mesas legítimas y cola de verificación
7. Arquitectura escalable de 18 muestras a 122K actas nacionales
8. 100% confidencialidad: credenciales Supabase SOLO en variables de entorno

---

## 📐 Arquitectura

### Stack Tecnológico

| Capa | Tecnología | Versión | Propósito |
|------|-----------|---------|-----------|
| Lenguaje | Python | 3.14 (venv/) | Procesamiento async, pipeline |
| Framework API | FastAPI + uvicorn | latest | API REST en puerto 8700 |
| Parser PDF | PyMuPDF (fitz) | latest | Extracción de texto + coordenadas normalizadas |
| Visión (Capa 1) | OpenCV + numpy | latest | Heurística grosor/separador/tinta |
| VLM (Capa 2) | NVIDIA NIM (llama-3.2-90b-vision) | — | VLM dirigido para scores > 0.6 |
| OCR | Tesseract | latest | OCR con anclas para detectar celdas |
| DB local | SQLite (`data/e14_audit.db`) | bundled | Dev/testing — 11 tablas + 2 views + triggers |
| DB producción | Supabase PostgreSQL | — | 5 actas migradas, prod-readiness |
| Container | Docker (acquisition/) | latest | Microservicio para PDFs y tablas |
| QR/Barcode | pyzbar | 0.1.9 | ✅ Decodificación QR + 1D (CODE39/EAN13) — coord. normalizadas |
| Frontend | — | — | Dashboard pendiente |

### Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│                   CAPA CLIENTE                                │
│  [PDFs data/pdf_muestra/]  [evidencia ciudadana (POST)]      │
│                [Dashboard público (pendiente)]                │
├──────────────────────────────────────────────────────────────┤
│                   CAPA API (FastAPI :8700)                    │
│  POST /api/evidence/upload (F6 ingesta)                       │
│  GET  /api/actas, /api/discrepancias, /api/audit/{id}         │
├──────────────────────────────────────────────────────────────┤
│              CAPA PIPELINE (engine/pipeline_fraude.py)        │
│                                                               │
│  ┌── Ingesta ────────┐  ┌── Capa 0 (Aritmética) ────┐        │
│  │ download + cache   │  │ Validación de totales      │        │
│  │ rate limit (Sup.)   │  │ Excede_total, no_coincide  │        │
│  │ cola de slots       │  │ Nivelacion, firmas          │        │
│  └─────────────────────┘  └────────────────────────────┘        │
│                                                               │
│  ┌── Capa 1 (OpenCV vis) ───┐  ┌── Capa 2 (VLM) ──────┐      │
│  │ capa1_opencv.py            │  │ nvidia_nim_vlm         │      │
│  │ deteccion_dinamica.py      │  │ llama-3.2-90b-vision    │      │
│  │ ocr_anchor.py              │  │ Batch 18 muestras       │      │
│  │ Score 0-1 (grosor, sep.,   │  │ Scores > 0.6 → VLM     │      │
│  │            tinta)           │  │ Prompt dirigido         │      │
│  └─────────────────────────────┘  └─────────────────────────┘    │
│                                                               │
│  ┌── Comparación ────────┐  ┌── Verificación ────────┐       │
│  │ Oficial vs ciudadano   │  │ Consenso democrático     │       │
│  │ discrepancia_oficial_v │  │ Endpoint votos + trigger │       │
│  │ s_ciudadano             │  │ Cuórum configurable      │       │
│  └─────────────────────────┘  └──────────────────────────┘      │
├──────────────────────────────────────────────────────────────┤
│                   CAPA DATOS                                   │
│  [SQLite local] ↔ [Supabase PostgreSQL (prod)]                 │
│  11 tablas + 2 views + triggers                               │
│  migrate_data_supabase.py — SQLite → Supabase                  │
└──────────────────────────────────────────────────────────────┘
```

### Flujo de Datos

```
[PDF E-14 (Anza.pdf, Turbo_*.pdf)]
  → [PyMuPDF extract texto + coords normalizadas 0-1]
  → [genera_discrepancias_capa0] (aritmética)
       ↓
  [deteccion_dinamica de celdas (firma al final de página)]
  → [ocr_anchor con Tesseract] (text + boxes)
  → [capa1_opencv preprocess ROI firma]
  → [scores: grosor_trazo, separador, tinta anómala]
  → (score > 0.6 → VLM-driven prompt)
  → [NVIDIA NIM llama-3.2-90b-vision] (prompted con coords)
  → [VLM responde: confident score, reasoning]
  → [todas discrepancias] → SQLite (dev) o Supabase (prod)
  → [future: dashboard visualizar mapa de mesas]
```

Coordenadas siempre normalizadas (0-1) — nunca en píxeles fijos. Capa 1 analiza SOLO firmas, nunca números ni texto.

---

## 📊 Matriz de Trazabilidad

| Req ID | Descripción | Componente | Estado | Verificación |
|--------|-------------|------------|--------|--------------|
| R-01 | Capa 0 validación aritmética (7 discrepancias) | `generate_discrepancias_supabase.py` | ✅ | 7 discrepancies detected (excede_total, no_coincide, nivelacion, firmas) |
| R-02 | Worker pool concurrente con 0 colisiones | `ingestion/` (slot queue) | ✅ | F3 validado, 0 colisiones paralelas |
| R-03 | Capa 1 visión (3 scores de firmas) | `fase4/capa1_opencv.py` | ✅ | 30 discrepancias 'trazo_anomalo' detectadas |
| R-04 | Detección dinámica con anchor OCR | `fase4/deteccion_dinamica.py`, `ocr_anchor.py` | ✅ | Tests con 5 PDFs, Anza (clean) 0.58, Turbo 015 (controversial) 0.70 |
| R-05 | Capa 2 VLM con NVIDIA NIM (3 API keys rotadas) | `scripts/run_vlm_batch.py` | ✅ | 18 muestras batch, 0 errores |
| R-06 | Schema SQLite + PostgreSQL (11 tablas + 2 views) | `schema_sqlite.sql`, `schema_postgresql.sql` | ✅ | create_db.py, 5 actas migradas |
| R-07 | Migración SQLite → Supabase | `migrate_data_supabase.py` | ✅ | 5 actas, 37 discrepancies en Supabase |
| R-08 | Coordenadas SIEMPRE normalizadas (0-1) | All CV code | ✅ | Code review —永远不会hardcoded pixel coords |
| R-09 | Capa 1 SOLO firmas (nunca números/texto) | `fase4/capa1_opencv.py` | ✅ | Por diseño, ROI crop restricts |
| R-10 | API key rotation NVIDIA NIM (~37 req/min) | `run_vlm_batch.py` | ✅ | 3 keys captcha rotation |
| R-11 | F6 Ingesta evidencia ciudadana | `api/main.py` POST /api/evidence/upload | ✅ | Endpoint implementado |
| R-12 | F7 Motor comparación oficial vs ciudadano | — | ⏳ | Pendiente — generará discrepancia_oficial_vs_ciudadano |
| R-13 | F8 Flujo verificación ciudadana (consenso) | — | ⏳ | Pendiente — endpoint votos + trigger |
| R-14 | F9 Dashboard público (3 vistas) | — | ⏳ | Pendiente — mapa, mesas legítimas, cola |
| R-15 | F10 Panel admin + exportación impugnaciones | — | ⏳ | Pendiente — PDF exportable |
| R-16 | F7 VLM workers (dedicated, concurrent batches) | — | ⏳ | Issue #1 — pendiente |
| R-17 | pyzbar QR/Barcode extraction | `engine/analyze/qr_barcode.py` | ✅ | Decodifica QR+CODE39 en 5 PDFs muestra, bbox normalizadas, integra pipeline |
| R-18 | Dashboard front-end | — | ⏳ | Pendiente |
| R-19 | Calibración manual de coordenadas | `scripts/calibrate_capa1.py` | ⚠️ | Limitación aceptada: scores como señal de dirección, no verdad absoluta |

---

## 🏗️ Marcos Conceptuales

### Multi-Capa Forense Cascada
Cada capa produce una fuente de evidencia independiente:
- **Capa 0** (Aritmética): low-cost, determinística, alta precisión. Detecta errores humanos o intencionales de suma.
- **Capa 1** (Vision heurística): OpenCV con scores 0-1 (grosor, separador, tinta). Produce 30 discrepancies `trazo_anomalo`.
- **Capa 2** (VLM dirigido): se invoca SOLO para scores > 0.6 de Capa 1 — razona sobre la zona, produce verdict final.

Las capas son aditivas y cada una tiene threshold independiente. Capa 2 NO se invoca con todas las muestras (costo), solo con priorización vía Capa 1.

### Coordenadas Normalizadas (0-1)
Regla fundamental — nunca en píxeles fijos. Esto permite:
- Robustez a diferente DPI/scanning
- Comparación cross-documentada
- Serialización en DB sin multiplicación dimensional

### Incident-Driven Audit Trail
Cada `discrepancia` es una fila tipada en Supabase con `tipo`, `mesa_key`, `capa`, `score`, `coordenadas` (normalizadas), `details_json`. Permite reconstruir el timeline de auditoría ciudadana.

### Ciudadano como Validator
El flujo F8 (verificación ciudadana por consenso) permite que múltiples ciudadanos verifiquen una discrepancia. Cuando el cuórum alcanza X, se cierra el caso con 'verificado' o 'impugnado'.

### Calibración como Heurística, No Verdad
Decisión 2026-07-30: los scores de Capa 1 son señales de dirección (priorización), no verdad absoluta. Las coordenadas de celdas son aproximadas — la calibración manual se hace con `scripts/calibrate_capa1.py` como referencia, pero no bloquea F6+.

---

## ✅ Justificación de Decisiones Técnicas

| Decisión | Opción elegida | Alternativas evaluadas | Razón |
|----------|---------------|----------------------|-------|
| Lenguaje | Python 3.14 + venv | Node, Go | Ecosistema CV/análisis (OpenCV, numpy, PyMuPDF), venv ligero |
| DB dev | SQLite | PostgreSQL local (sin sudo) | No require sudo para instalar, schema_adaptado con tipos SQLite |
| VLM Provider | NVIDIA NIM (llama-3.2-90b-vision) | OpenAI GPT-4-vision, Anthropic Claude | Gratis, modelo grande open-weight, API REST-compatible con rate limiting lui 3 keys rotation |
| Coordenadas | Normalizadas (0-1) SIEMPRE | Píxeles fijos | Robustez cross-DPI/scanning, comparable across docs |
| Capa 1 alcance | SOLO firmas (nunca números) | Full-page scoring | Anomalías visuales más específicas firmas son focal — reduce FP |
| Rate limiting | 3 API keys rotación (~37 req/min) | Single key with backoff | NVIDIA NIM límite por key, rotation evita throttling |
| Credenciales | SOLO en variables entorno | .env en repo, hardcoded | Seguridad — aspiración de 122K actas nacionales requiere zero secrets leaks |
| GUI/dashboard | Pendiente (priority post-engine) | Streamlit earlier | Separa concerns — algoritmo primero, UX es f9 separado |
| Container | Docker para `acquisition/` microservice | Single process monolith | Aislar rate-limit heavy download, paralelo con API engine |
| Main framework | FastAPI + uvicorn | Flask, Django | Async para VLM calls + WebSocket future para dashboard live |

---

## 📦 Estado de Implementación

### Fases Completadas

| Fase | Descripción | Commit | Verificación |
|------|-------------|--------|--------------|
| F1 | Base de datos + Supabase | [init] | 11 tablas, 2 views, triggers, 5 actas migradas |
| F2 | Capa 0 aritmética | [prev] | 7 discrepancias (excede_total, no_coincide, nivelacion, firmas) |
| F3 | Cola de slots + workers concurrentes | [prev] | Worker pool paralelo validado, 0 colisiones |
| F4 | Capa 1 visión por computador (OpenCV) | [prev] | 3 scores (grosor, separador, tinta). 30 discrepancies 'trazo_anomalo' |
| F5 | Capa 2 VLM dirigido (NVIDIA NIM) | 3ebdfb3 | 18 muestras, 0 errores. Scores > 0.6 separar pendiente |
| F6 | Ingesta de evidencia ciudadana | 3ebdfb3 | `POST /api/evidence/upload` implementado |
| Consol | Fusión e14-audit-platform + e14-fraud-detector | 1d60c94 | Proyecto único unificado |
| Templates | GitHub issue/PR templates + CI 3-layer gates | 97e108b | Workflow files committed |

### Próximos Pasos (Backlog)

| ID | Descripción | Prioridad | Issue |
|----|-------------|-----------|-------|
| B-1 | F7 VLM workers dedicados con batches concurrentes | Alta | #1 |
| B-2 | F7 Motor comparación oficial vs ciudadano | Alta | #2 |
| B-3 | F8 Flujo verificación ciudadana (consenso) | Media | #3 |
| B-4 | F9 Dashboard público (3 vistas: mapa, mesas legítimas, cola) | Media | #4 |
| B-5 | F10 Panel admin + exportación impugnaciones PDF | Media | #5 |
| B-6 | pyzbar QR/Barcode extraction | ✅ Done | #6 |
| B-7 | Calibración precisa de coords (post-f6+) | Baja | #7 |

---

## ⚠️ Limitaciones Conocidas

1. **Coordenadas aproximadas**: Las celdas de firma se detectan dinámicamente, sus scores actúan como señal de dirección, no como verdad absoluta. Calibración manual mejora precisión pero no es automática.
2. **Dataset limitado a 18 muestras**: Escalabilidad a 122K actas requiere infraestructura distribuida (rate limits NVIDIA NIM ~37 req/min con 3 keys).
3. **VLM costo**: A 122K actas × 6 muestras por acta formas avg, con Capa 1 priorización el 30% llega a Capa 2 → ~220K VLM calls. Necesaria ChileController.
4. **NVIDIA NIM límite ~37 req/min por key**: 3 keys rotation, pero escala lineal requiere más keys o self-hosted VLM.
5. **Sin auth ciudadana**: F8 (verificación) necesita esquema de identidad anti-bot antes de consenso.
6. **Sin dashboard público**: Frontend completo pendiente, visualización actual es via Supabase Studio.
7. **Formato mesa_key rígido**: Requiere DIVIPOLA codes estrictos, falla con docs no estandarizados.
8. **DPI asumption**: PyMuPDF extract asume DPI uniforme en el PDF; docs mixtos pueden romper la detección.

---

## 🔐 Seguridad

- **Credenciales Supabase SOLO en variables de entorno** — nunca en archivos/.env _checked-in_
- **3 API keys NVIDIA NIM rotadas** — límite ~37 req/min evita bloqueo pero no protege contra leak
- **NVIDIA NIM API keys en environment**: rotar manual + auditar use cada X calls
- **No PII standalone files**: nombres/firmas viven en DB, no se guardan PNGs intermedios
- **Pipeline reproducible**: cualquier duda, re-run con `engine/pipeline_fraude.py archivo.pdf` regenera todo
- **Commit rule**: atómico en español → push inmediato, no dejar branches stale con discrepancias sensibles

---

## 📚 Referencias

- OpenCV CV hints: https://docs.opencv.org/
- NVIDIA NIM llama-3.2-90b-vision: https://docs.api.nvidia.com
- Supabase docs: https://supabase.com/docs
- FastAPI: https://fastapi.tiangolo.com/
- DIVIPOLA Colombia codes: https://www.dane.gov.co
- Formato acta E-14: Registraduría Nacional
- Calibración: `scripts/calibrate_capa1.py`
- Repo: https://github.com/Nxxo31/e14-fraud-detector

---

*Generado por SophIA — Sebastian Velasco's autonomous operating system*

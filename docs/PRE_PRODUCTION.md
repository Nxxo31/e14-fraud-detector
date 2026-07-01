# E14 Fraud Detector — Estado Pre-Producción

**Fecha:** 2026-01-11
**Versión:** 0.1.0-preprod
**Autor:** SophIA (operador autónomo)

---

## ✅ Estado del Sistema

```
Componente                      Estado    Versión/Fecha
─────────────────────────────────────────────────────────
Python Environment                ✅ OK      3.14.4 + pip global
OpenCV                          ✅ OK      4.13.0.92
PyMuPDF                         ✅ OK      1.27.2.3
Tesseract OCR                   ✅ OK      5.5.0
FastAPI                         ✅ OK      0.115+
Uvicorn                         ✅ OK      0.32+
NVIDIA NIM Client               ✅ OK      openai 2.44.0
HTTP Client                     ✅ OK      httpx 0.28+
Pillow                          ✅ OK      12.2.0
Numpy                           ✅ OK      2.4.6
PostgreSQL Client               ✅ OK      psycopg2-binary (preparado)
Celery                          ⏳ pendiente (requiere Redis)
Redis                           ⏳ pendiente (no esencial en dev)
```

---

## 🏛 Arquitectura Operativa

```
┌─────────────────────────────────────────────────────────────────┐
│                     E14 FRAUD DETECTOR                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐ │
│  │ INGEST   │───▶│ PROCESSING   │───▶│ OUTPUT               │ │
│  │          │    │              │    │                      │ │
│  │ downloader│    │ pdf_renderer │    │                      │ │
│  │ rate_limit│    │ normalizer   │    │                      │ │
│  │ queue     │    │ layout_detect│    │                      │ │
│  │           │    │ cell_extract │    │                      │ │
│  │           │    │ arithmetical │    │                      │ │
│  │           │    │ visual_anom  │    │ JSON per acta        │ │
│  │           │    │ ocr_tesseract│    │ Base64 images        │ │
│  │           │    │ vlm_nim      │    │ Veredicto            │ │
│  │           │    │ forensic     │    │                      │ │
│  └──────────┘    └──────────────┘    └──────────────────────┘ │
│         │                │                                       │
│         ▼                ▼                                       │
│  ┌─────────────────────────────────────────────────────┐      │
│  │              API REST (FastAPI 8700)                   │      │
│  │    /api/v1/analyze/{mesa_key}   → POST analizar acta   │      │
│  │    /api/v1/batch               → POST batch            │      │
│  │    /api/v1/dashboard           → GET resumen            │      │
│  └─────────────────────────────────────────────────────┘      │
│                           │                                       │
│                           ▼                                       │
│  ┌─────────────────────────────────────────────────────┐      │
│  │              DASHBOARD (React + Vite)               │      │
│  └─────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Roadmap Sprint Pre-Producción

### Sprint 1: Pipeline E2E Robustecido (COMPLETAR)
- [ ] Script de validación del pipeline (ejecutar sobre 5 muestras)
- [ ] Tests unitarios para cada módulo del engine
- [ ] Manejo de errores robusto en pdf_renderer.py
- [ ] Calibración automática de coordenadas (LayoutDetector)
- [ ] Logging estructurado en cada etapa del pipeline

### Sprint 2: Capa 2 VLM (Integración NVIDIA NIM)
- [ ] Prompts finales de extracción de votos con contexto E-14
- [ ] Client NIM con retry y rate limiting (37req/min)
- [ ] Fallback automático: NIM → Tesseract → manual
- [ ] Validación cruzada Capa 1 (OpenCV) + Capa 2 (VLM)

### Sprint 3: Infraestructura de Producción
- [ ] Docker Compose con PostgreSQL + Redis
- [ ] Celery workers para procesamiento asíncrono
- [ ] MinIO para almacenamiento de PDFs e imágenes
- [ ] CI/CD para tests automatizados

### Sprint 4: Dashboard y API
- [ ] API REST completa con autenticación
- [ ] Dashboard React con visualización de resultados
- [ ] Cola de revisión priorizada para auditores humanos

---

## 🎯 Criterios de "Done" para Pre-Producción

1. **Pipeline ejecutable:** `python engine/pipeline.py data/pdf_muestra/*.pdf` produce JSON sin errores
2. **Capa 1 calibrada:** Scores OpenCV < 0.5 en actas normales, > 0.8 en actas con anomalías
3. **Capa 2 operativa:** NIM extrae votos con >70% accuracy vs datos manuales
4. **Tests existen:** Coverage > 60% en módulos críticos (renderer, segment, analyze)
5. **Logging:** Cada ejecución genera log estructurado con timestamp y etapas
6. **Documentación:** todos los módulos tienen docstrings y README.md actualizado

---

## 🚀 Próximos pasos inmediatos

1. Ejecutar el script `scripts/validate_pipeline.py` sobre las 5 actas de muestra
2. Si pasa sin errores → commit + push como tag `v0.1.0-preprod`
3. Iniciar Sprint 1 (tests unitarios y calibración)

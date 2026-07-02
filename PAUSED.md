# E14 Fraud Detector — ESTADO DE PAUSA

**Fecha de pausa:** 2026-07-01
**Versión:** v0.2.1
**Motivo:** Proyecto en estado funcional, listo para reanudar cuando sea prioritario

---

## ✅ Estado al momento de pausar

| Componente | Estado | Nota |
|-----------|--------|------|
| Pipeline E2E | ✅ Funcional | 5/5 actas procesadas sin errores |
| README | ✅ Completo | Publicado en GitHub con arquitectura y uso |
| Tag v0.2.1 | ✅ Publicado | https://github.com/Nxxo31/e14-fraud-detector/releases/tag/v0.2.1 |
| Capa 1 (OpenCV) | ⚠️ Calibración pendiente | Umbrales por defecto pueden ser muy sensibles |
| Capa 2 (VLM NIM) | ⚠️ Prompts en desarrollo | Integración lista, necesita entrenamiento |
| Tests | ⚠️ 0% cobertura | Sprint E1 pendiente: pytest + cobertura 80%+ |
| API REST | ✅ Básica | FastAPI en puerto 8700, endpoints simples |
| Dashboard | ❌ No existe | Sprint E4 pendiente: React + Vite |

---

## 📋 Para reanudar (Próximos pasos)

1. **Sprint E1 — Tests y Calibración**
   - Datos de suelo (ground truth) para las 5 actas de muestra
   - Tests unitarios con pytest (cobertura 80%+)
   - Calibrar umbrales de veredicto con validación cruzada

2. **Sprint E2 — Capa 2 VLM**
   - Diseñar prompts finales de extracción de votos
   - Implementar retry y rate limiting (37 req/min límite NVIDIA)
   - Validar accuracy vs ground truth

3. **Sprint E3 — Infraestructura**
   - Docker Compose: PostgreSQL + Redis + MinIO
   - Celery workers para procesamiento asíncrono
   - CI/CD con GitHub Actions

4. **Sprint E4 — Dashboard**
   - React + Vite con visualización de resultados
   - Cola de revisión priorizada para auditores humanos

---

## 🔗 Recursos disponibles

- **Repositorio:** https://github.com/Nxxo31/e14-fraud-detector
- **Documentación:** `docs/PRE_PRODUCTION.md`, `docs/RELEASE_v0.1.0.md`
- **Script validación:** `scripts/validate_pipeline.py`
- **Pipeline CLI:** `python engine/pipeline.py <ruta_pdf>`

---

## 🎯 ¿Cuándo retomar?

- Cuando tengas datos de suelo (ground truth) para calibración
- Cuando necesites priorizar el sistema para un proceso electoral
- Cuando quieras integrar el sistema con un frontend/dashboard

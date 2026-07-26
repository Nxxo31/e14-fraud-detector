# E14 AUDIT PLATFORM — Technical Reality Audit

**Fecha:** 2026-06-26
**Auditor:** Principal Architect
**Scope:** Repositorio completo (`/home/sebas/proyectos/e14-audit-platform`)
**Mandato:** Estado real sin suavizar; nada se asume; cada conclusión esta fundamentada.

---

## 1. Executive Summary (Sin filtro)

| Métrica | Valor |
|---|---|
| Archivos Python | 92 |
| Líneas de código | ~12,657 |
| Archivos Markdown | 16 |
| Esquemas SQL (PostgreSQL + SQLite) | 2 |
| Archivos Docker | 5 |
| **Pipeline E2E funcional** | **NO** |
| **Tests automatizados ejecutables** | **NO** |
| **Sistema deployable** | **NO** |
| **Capa 1 (OpenCV) confiable** | **NO** (coordenadas sin calibrar) |
| **Capa 2 (VLM) implementada** | **NO** |
| **Capa 0 (validación aritmética) en producción** | **Parcial** (datos hardcodeados) |
| **Dependencias críticas instaladas** | **50%** |

**Diagnóstico en una frase:** El repositorio contiene múltiples experimentos aislados que nunca fueron integrados en un pipeline coherente; la mayor parte del código es texto inerte.

---

## 2. Inventario de Componentes

### 2.1 Capa de Adquisición (`acquisition/`)

| Archivo | Líneas | Estado | Problema |
|---|---|---|---|
| `app/config.py` | ~120 | ✅ Escrito | Sin ejecutar nunca |
| `app/database.py` | ~20 | ✅ Escrito | Sin ejecutar nunca |
| `app/models.py` | ~90 | ✅ Escrito | Sin ejecutar nunca |
| `app/main.py` | ~80 | ✅ Escrito | Sin ejecutar nunca |
| `app/routers/tables.py` | ~95 | ✅ Escrito | Sin ejecutar nunca |
| `app/routers/pdfs.py` | ~96 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/metadata.py` | ~105 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/downloader.py` | ~207 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/storage.py` | ~92 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/rate_limiter.py` | ~47 | ✅ Escrito | Sin ejecutar nunca |
| `worker/celery_app.py` | ~52 | ✅ Escrito | Sin ejecutar nunca |
| `worker/tasks.py` | ~409 | ✅ Escrito | Sin ejecutar nunca |
| `tests/test_integration.py` | ~175 | ✅ Escrito | Sin ejecutar nunca |

**Veredicto:** Servicio FastAPI + Celery completamente escrito pero nunca desplegado ni probado. Celery, Redis y MinIO no están instalados en el entorno.

### 2.2 Capa de Análisis (`analysis/`)

| Archivo | Líneas | Estado | Problema |
|---|---|---|---|
| `app/main.py` | ~90 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/pdf_renderer.py` | ~148 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/signature_detector.py` | ~152 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/ocr_engine.py` | ~249 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/validation.py` | ~254 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/pipeline.py` | ~218 | ✅ Escrito | Sin ejecutar nunca |
| `app/services/storage.py` | ~85 | ✅ Escrito | Sin ejecutar nunca |

**Veredicto:** Ningún pipeline OCR real ha sido ejecutado desde analysis/. Los intentos OCR exitosos fueron scripts standalone en `fase2/`, `fase4/`, `scripts/`, etc.

### 2.3 Experimentos Históricos (scripts sueltos)

| Directorio | Archivos | Propósito | Estado |
|---|---|---|---|
| `fase2/` | 2 | Validación Capa 0 | Parcial: datos manuales, no automatizado |
| `fase4/` | 3 | Capa 1 OpenCV | Funciona pero coordenadas no calibradas |
| `fase3/` | 2 | Workers concurrentes | Teórico, nunca productivizado |
| `scripts/` | 4 | Análisis integrado | Scripts sueltos, no pipeline |
| `calibration/` | 8 | Calibración de coordenadas | Incompleto, resultados mixtos |
| `mvp/` | 5 | Pipeline MVP | Abandonado en favor de fases posteriores |
| `fase_a_segmentacion/` | 7 | Segmentación | Funcional para 4 muestras, sin generalizar |

### 2.4 Esquemas de Base de Datos ?
n
| Archivo | Tablas/Objs | Estado |
|---|---|---|
| `schema_postgresql.sql` | 11 tablas + 2 views + triggers | ✅ Diseño robusto; Supabase creado pero no validado |
| `schema_sqlite.sql` | 11 tablas SQLite | ✅ Funcional en `data/e14_audit.db` |
| `create_db.py` | SQLite wrapper | ✅ Ejecutado; 5 actas insertadas con datos manuales |
| `seed_data.py` | Datos de prueba | ✅ Funcional pero limitado a 5 actas |

### 2.5 Datos de Muestra

| Categoría | Cantidad |
|---|---|
| PDFs de control | 14 |
| PDFs de muestra local | 5 |
| Imágenes de firma extraídas | 95 |
| Imágenes de celdas | 36 |
| Resultados JSON | 10 |
| Archivos de debug | 5 |

**Nota crítica:** Solo se han procesado ~9 actas E-14 reales de forma manual o semi-manual. Sin automatización.

---

## 3. Qué Funciona Realmente

### 3.1 ✅ Funcional (con limitaciones conocidas)

| Componente | Qué hace | Limitación |
|---|---|---|
| `schema_sqlite.sql` + `create_db.py` | Crea y pobla SQLite con 5 actas | Datos manuales, no conectado a fuente real |
| `fase4/capa1_opencv.py` | Detecta anomalías visuales en recortes | Coordenadas sin calibrar; genera falsos positivos |
| `fase_a_segmentacion/pipeline.py` | Segmenta PDFs en celdas y regiones | Solo 4 muestras; no probado con variedad de formatos |
| `scripts/analisis_integrado_final.py` | Análisis forense combinado Tesseract+OpenCV | Tesseract requiere sudo; script no automatizado |
| `benchmark_tecnologias.py` | Renderiza PDFs y mide contornos | Sin OCR real, solo estadísticas de imagen |

### 3.2 ⚠️ Parcial / Con problemas graves

| Componente | Problema root |
|---|---|
| `calibration/` | Múltiples iteraciones sin lograr coordenadas estables. Normalización no estándar. |
| `fase4/capa1_opencv.py` (scores) | Scores 0.70 en actas limpias. Las coordenadas de celdas son aproximaciones. Umbral 0.6 genera falsos positivos. |
| `generate_discrepancias_supabase.py` | Genera discrepancias de Capa 0 pero sobre datos manuales, no sobre pipeline real. |

### 3.3 ❌ No funciona / No existe

| Componente | Estado |
|---|---|
| Pipeline end-to-end | No existe. Ningún PDF va de entrada a informe automáticamente |
| Capa 2 (VLM NIM) | No implementada. Prompts no diseñados. |
| Motor de detección de firmas automático | Solo extracción zonal a mano; sin detección de firma faltante robusta |
| OCR de números manuscritos | ZERO números votos extraídos automáticamente y verificados |
| Dashboard / Frontend | No existe |
| API REST funcional | No existe servicio levantado |
| Workers concurrentes | Diseñados pero nunca ejecutados |
| Tests unitarios ejecutables | No existen |

---

## 4. Deuda Técnica Crítica
性感### 4.1 Dependencias sin instalar (ambiente dev)

| Dependencia | Requerida por | Impacto |
|---|---|---|
| `easyocr` | `pipeline_fraude.py` | OCR alternativo no probado |
| `supabase` (cliente Python) | Conexión Supabase | Bloquea migración real a PostgreSQL |
| `celery` | Workers asincrónicos | Bloquea procesamiento concurrente |
| `redis` | Broker Celery / cache | Bloquea workers y cacheo |
| `pyzbar` | Decodificación QR | QR no implementado |
| `minio` | Object storage | Bloquea almacenamiento de PDFs/caché |
| `alembic` | Migraciones DB | Bloquea migraciones estructuradas |

### 4.2 Fragmentación arquitectural

Sintoma: 92 archivos Python en múltiples directorios temáticos (`fase2/`, `fase4/`, `calibration/847/`, `scripts/`, `mvp/`, `fase_a_segmentacion/`) sin un framework de integración claro.

- Cada fase se desarrolló en aislamiento.
- No existe un `main.py` unificado que orqueste el flujo completo.
- Los datos fluyen manualmente (copiar archivos entre carpetas) en lugar de programáticamente.

### 4.3 Ausencia de tests

- Zero tests unitarios.
- Zero tests de integración ejecutables (existe `test_integration.py` pero solo en texto).
- La única "validación" es visual/manual del usuario.

### 4.4 Acoplamiento con datos hardcodeados

- Coordenadas de celdas en múltiples scripts.
- IDs de Supabase y claves API hardcodeadas en archivos.
- 5 actas de muestra con datos manuales no representativos de la varianza real E-14.

---

## 5. Cuellos de Botella Identificados

### 5.1 Cuellos de botella algorítmicos

1. **Segmentación de celdas de votación**: No hay un algoritmo probado que, dado cualquier PDF E-14, sepa localizar con precisión las celdas de votos. Es el bloqueante técnico #1.
2. **OCR de manuscritos**: Tesseract/EasyOCR/PaddleOCR fallan en dígitos manuscritos colombianos; TrOCR/DONUT/Florence-2 nunca fueron probados.
3. **Detección de firmas faltantes**: No hay un identificador automático de "casilla de firma vacía vs llena".

### 5.2 Cuellos de botella operativos

1. **Sin sistema de cola real**: Los workers están diseñados pero no ejecutados.
2. **Sin caché de datos**: Cada ejecución re-procesa desde cero.
3. **Sin logging estructurado**: Impossible debuggar en escala.

### 5.3 Cuellos de botella organizativos

1. **Mezcla de fases y arquitecturas en un solo repositorio**: Fase A, Fase 2, Fase 3, Fase 4, MVP... conviven sin una estructura clara de "qué está activo".
2. **Documentos arquitectónicos desactualizados**: `system_architecture_v1.md` describe una arquitectura nunca implementada (servicios FastAPI separados).

---

## 6. Inventario de decisiones previas cuestionables

| Decision | Análisis | Impacto |
|---|---|---|
| SQLite en dev sin migración a PostgreSQL | "No se pudo instalar PostgreSQL (requiere sudo)" es un workaround que se convirtió en estándar | Riesgo de incompatibilidad de tipos, triggers, y funcionalidades avanzadas |
| Coordenadas fijas aproximadas para Capa 1 | Rechazadas por el usuario posteriormente | Los scores de Capa 1 son no-calibrados y generan falsos positivos |
| PaddleOCR para OCR de votos | Nunca fue probado en números manuscritos reales | Dependencia pesada sin beneficio demostrado |
| EasyOCR vía subprocess (según `pipeline_fraude.py`) | Patrón anti-patrón de seguridad y estabilidad | Llamadas a shell para OCR son lentas y poco confiables |
| Acoplamiento con datos manuales (5 actas) | Datos de prueba no representativos de la varianza real | Generalización incierta de los resultados |

---

## 7. Conclusión de la Fase 1 (Estado Real)

### Porcentaje real de avance: **15 – 20%**

Este número no es optimista. Refleja:

- **~30%** de la infraestructura de datos (esquemas, SQLite, Supabase schema).
- **~45%** de la Capa 0 (validación aritmética, pero sobre datos manuales).
- **~15%** de la Capa 1 (detección de anomalías visuales con coordenadas no calibradas).
- **~0%** de la Capa 2 (VLM NIM nunca implementada).
- **~0%** de frontend/API consumible.
- **~10%** del pipeline de adquisición de datos (escrito pero nunca ejecutado).

### Riesgos críticos inmediatos:

1. **Bloqueante técnico #1**: No se puede extraer reliable los votos manuscritos de un PDF E-14 arbitrario.
2. **Bloqueante técnico #2**: No se puede detectar automáticamente la presencia/ausencia de firm Authorizedlizas.
3. **Bloqueante operativo #1**: El 50% de dependencias críticas no está instalado; el sistema no es ejecutable como un todo.
4. **Bloqueante de calidad**: Sin tests ni datos de validación, cada cambio puede romper lo que "funciona" sin advertencia.

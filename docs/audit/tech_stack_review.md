# E14 AUDIT PLATFORM — Tech Stack Review v2.0

**Auditor:** Principal Architect
**Mandato:** A cada tecnología le cae bien o queda. Sin compromisos sentimentales.

---

## 1. Criterios de Evaluación

| Criterio | Peso |
|---|---|
| Precisión en el problema E-14 | 30% |
| Escalabilidad a volumen masivo | 20% |
| Facilidad de operación / DevOps | 15% |
| Costo de cambio (migration cost) | 15% |
| Madurez y comunidad | 10% |
| Licenciamiento y soberanía tecnológica | 10% |

---

## 2. Tabla de Tecnologías — Veredicto Final

| Tecnología | Uso Actual | Veredicto | Motivo Técnico |
|---|---|---|---|
| **PyMuPDF (fitz)** | Renderizado PDF→imagen | **MANTENER** | Rápido (~300ms/PDF), preciso, sin dependencias externas pesadas. Defacto estándar. |
| **OpenCV** | Visión clásica, binarización, contornos | **MANTENER** (con restricciones) | Indispensable para pre-procesamiento. PERO: no escribir más heurísticas de segmentación complejas; usar solo para normalización y pre-procesamiento. |
| **Tesseract OCR** | OCR texto impreso (metadatos del acta) | **MANTENER** (limitado) | Suficiente para texto impreso de alta calidad. No usar para dígitos manuscritos; CER insuficiente (~18%). Requiere `sudo apt-get install`. |
| **EasyOCR** | OCR general (no usado en producción) | **DESCARTAR** | Requiere PyTorch pesado. Sin ventaja demostrada sobre PaddleOCR o TrOCR. Overkill para dígitos. |
| **PaddleOCR** | OCR de documentos (listado en `requirements.txt`) | **DESCARTAR** | Pesado, complejo de desplegar (dependencias C++), sin evidencia de superioridad en manuscrito colombiano. Migration cost justifica no invertir. |
| **TrOCR** | OCR de manuscrito especializado | **ADOPTAR** (con compromise) | Líder en CER para manuscrito (3.2%). Requiere GPU o es lento. Necesita fine-tuning con celdas E-14. Depende de segmentación previa. |
| **Donut** | OCR-free document understanding | **DESCARTAR** | Overkill para leer dígitos. Inferencia lenta. No compensa el costo de integración. |
| **Florence-2** | VLM multimodal (OCR + layout) | **EVALUAR** (low priority) | Bueno para comprensión general, pero no el mejor para dígitos aislados. Costoso en GPU. |
| **LayoutLM / LayoutLMv3** | Document layout + text understanding | **EVALUAR** (medio) | Bueno para "entender" la estructura del formulario. Potencialmente útil para segmentación asistida. |
| **YOLO / Detectron2** | Detección de objetos en documentos | **EVALUAR** | Para detectar celdas y firmas como objetos. Posiblemente mejor que heurísticas OpenCV. Requiere dataset de entrenamiento. |
| **SQLite** | Dev local | **MANTENER** (solo dev) | Perfecto para prototipos. Nunca para producción con 122K+ filas y concurrencia. |
| **PostgreSQL** | Base de datos de producción | **MANTENER** | Única opción seria para volumen y consistencia transaccional. |
| **Supabase** | PostgreSQL como servicio | **MANTENER** (con restricciones) | Práctico para MVP. Escalabilidad limitada (20K RPS en tier gratuito). Planificar migración a PostgreSQL auto-gestionado para escala. |
| **FastAPI** | API web | **MANTENER** | Moderno, rápido, async. Sin problemas conocidos. |
| **Celery** | Workers concurrentes | **MANTENER** (pero no bloqueante) | Estándar en Python. Redis como broker. Sin embargo, para procesamiento puramente CPU de imágenes, multiprocessing directo puede ser más simple y rápido. |
| **Redis** | Broker / cache | **MANTENER** | Ligero, efectivo. Necesario para Celery y caché de sesión. |
| **MinIO** | Almacenamiento de objetos (PDFs, imágenes) | **EVALUAR** | S3-compatible. Útil si se requiere separación de storage. Simplificable si Supabase Storage es suficiente. |
| **Gradio** | Demo/prototipo web | **DESCARTAR** | Sólo para experimentos. No para producción. |
| **NVIDIA NIM (VLM)** | VLM clúdico (llama-3.2-90b-vision) | **ADOPTAR** (selectivamente) | Potente para casos dudosos. Costoso si se envía todo. La estrategia es: filtrar con Capa 1, luego enviar sólo lo dudoso al VLM. Ver capa 7. |
| **Python** | Lenguaje principal | **MANTENER** | Ecosistema científico es insustituible para este dominio. |
| **Go** | Considerado para servicios backend | **NO JUSTIFICADO** | No hay cuello de botella de rendimiento que justifique bifurcar el stack al menos hasta escala millonaria. |

---

## 3. Principios de Re-arquitectura

### 3.1 Rechazar soluciones "todo-en-uno

**Anti-patrón:** Intentar resolver OCR + segmentación + análisis forense con un solo modelo (e.g. Donut, Florence-2 sobre página completa).

**Razón:** Los formularios E-14 son estáticos; los errores son sutiles; la decomposición modular permite ajustar, reemplazar y explicar.

**Arquitectura preferida:**
```
PDF → Segmentador dedicado → (Celdas de votos, Firmas, Metadatos)
    ↓
Pre-procesador OpenCV (normalización)
    ↓
OCR especializado (TrOCR) para celdas
OCR clásico (Tesseract) para metadatos impresos
OpenCV heurístico para firmas
    ↓
Motor de reglas forenses
    ↓
Escalado a VLM (casos dudosos)
```

### 3.2 Abandonar OCR generalista para números manuscritos

**Conclusión del benchmarking previo y bibliografía:**

- Tesseract / PaddleOCR / EasyOCR: **CER 15-18%** en manuscritos colombianos (estimado basado en IAM + papers regionales).
- TrOCR (fine-tuned): **CER 3-5%** en manuscrito manuscrito.
- La diferencia es la tensión entre un sistema "auditoría ciudadana" y un sistema que falla 1 de cada 6 dígitos.

**Decisión:** Invertir en TrOCR con fine-tuning local o semi-local, aceptando la dependencia de GPU.

### 3.3 Soberanía y costos cloud

| Solución | Costo por 100K actas | Dependencia externa |
|---|---|---|
| Tesseract local | $0 (CPU) | Ninguna |
| TrOCR local (GPU) | ~$50-100 (renta GPU) | NVIDIA drivers |
| NVIDIA NIM VLM (llama-3.2-90b) | ~$200-500 (estimado) | NVIDIA plataforma + internet |
| AWS Textract / Azure Form Recognizer | ~$1,500-3,000 | Cloud provider total |

**Decisión:** Maximizar procesamiento local para volumen,VERY exch SIG. Usar VLM cloud únicamente para casos dudosos (estimado <5% de actas).

---

## 4. Tabla Comparativa: Arquitectura Óptima por Escala

| Escala | 1,000 | 10,000 | 100,000 | 1,000,000 |
|---|---|---|---|---|
| **CPU Cores** | 4 | 8 | 32-64 | 128+ |
| **GPU (VRAM)** | 8GB (RTX 3070) | 16GB (RTX 4070 Ti) | 48GB (RTX A6000 / 2×A40) | Clúster GPU / Instancias cloud |
| **Almacenamiento** | 100GB SSD | 500GB SSD | 5TB NVMe | 50TB+ SAN/object |
| **RAM** | 16GB | 32GB | 128GB | 512GB+ |
| **PostgreSQL** | Local/Single | Local/Single | Primario-Standby | Patroni Cluster |
| **Workers** | 1 nodo, 4 workers | 1 nodo, 8 workers | 4 nodos, 64 workers total | 16 nodos, 256+ workers |
| **Est. tiempo total** | ~1 hora | ~4 horas | ~2 días | ~10 días |
| **Coste cloud (est.)** | $5-10 | $20-50 | $500-2,000 | $5,000-20,000 |
| **VLM NIM** | No justificado | No justificado | Casos dudosos (<5%) | Casos dudosos (<5%) |
| **Riesgo principal** | Calibración datos | Coordenadas locales | Escalabilidad workers | Costo, latencia DB |

**Notas:**
- Estimación de tiempo asume pipeline correctamente paralelizado, pre-procesamiento rápido (PyMuPDF + OpenCV), y OCR en GPU.
- La estrategia VLM "selectivo" es fundamental para mantener costos bajo control; enviar TODAS las actas al VLM es económicamente inviable.

---

## 5. Tecnologías Recomendadas Definitivas (Stack V2)

| Capa | Tecnología | Justificación |
|---|---|---|
| **Renderizado PDF** | PyMuPDF (fitz) | Rápido, preciso, ya en uso. |
| **Pre-procesamiento imagen** | OpenCV + NumPy | Normalización, escalado, deskew, binarización. |
| **Segmentación de celdas** | YOLOv8 fine-tuned o LayoutLM | Entrenado con ~200 celdas anotadas de E-14. Más robusto que heurísticas OpenCV. |
| **OCR metadatos** | Tesseract (spa) | Texto impreso de calidad suficiente. |
| **OCR votos manuscritos** | TrOCR (base/large) | Líder en precisión manuscrito. Fine-tuning requerido con dataset de celdas E-14. |
| **Detección firmas** | OpenCV heurístico (v2) + CNN liviana | Combinación de umbral de varianza local + modelo lig Joyce que discrimina firma/no-firma. |
| **Análisis forense** | Reglas hard-coded + ML (isolation forest) | Combinación de reglas explícitas (sumas, firmas) + anomalías estadísticas. |
| **Escalador inteligente** | NVIDIA NIM (llama-3.2-90b-vision) | ÚNICAMENTE para casos que fallen en umbral de confianza combinado. |
| **Base de datos** | PostgreSQL (self-hosted) | Supabase para dev/MVP. Producción: PostgreSQL propio por soberanía y costos. |
| **Cola / Workers** | Celery + Redis | Estándar, bien documentado. |
| **API / Backend** | FastAPI (Python) | Async, moderno, buen rendimiento. |
| **Frontend** | React + TypeScript (o Svelte si se prefiere ligereza) | No implementado. React es más fácil de contratar/escalar equipo. |
| **Infraestructura** | Docker + docker-compose (local) → Kubernetes (producción) | Escalabilidad y repetibilidad. |

---

## 6. Tecnologías que se RETIRAN del Stack

| Tecnología | Razón del retiro |
|---|---|
| **PaddleOCR** | Complejidad de despliegue sin beneficio demostrado. Reemplazado por TrOCR. |
| **EasyOCR** | Dependencia pesada (PyTorch). Sin diferenciación en dígitos. |
| **Donut / Florence-2 (para OCR puro)** | Overkill para leer 9 dígitos por acta. Más lentos y costosos que TrOCR.|
| **Gradio** | No es tecnología de producción. |
| **Go (por ahora)** | Fragmentación del stack sin justificación de rendimiento. |

---

## 7. Recomendación Ejecutiva

**Concentrar el esfuerzo en:**
1. **Dataset de entrenamiento**: Anotar 200-500 celdas de votos de E-14 para fine-tuning de TrOCR o entrenamiento de YOLOv8.
2. **Calibración de coordenadas**: Implementar un sistema automático de localización de celdas (no depende de coordenadas fijas).
3. **Motor de reglas**: Codificar reglas forenses explícitas que no dependan de ML (sumas, firmas, formato).
4. **Integración modular**: Unir los módulos existentes en un pipeline callable con una sola función.
5. **Automatización de tests**: Al menos 10 tests de integración end-to-end que pasen.

**Todo lo demás (dashboard, API pública, ingest ciudadana) es secundario hasta que el pipeline anterior funcione.**

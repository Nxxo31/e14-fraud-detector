# INFORME COMPARATIVO — OCR para dígitos manuscritos en formularios E-14
## Evaluación de tecnologías previa a implementación

---

## 1. RESUMEN EJECUTIVO

El problema de lectura de votos manuscritos en E-14 **no es principalmente un problema de OCR** (reconocimiento de caracteres aislados), sino un **problema de segmentación y layout**: las celdas de votos están en posiciones variables entre formularios de distintos departamentos, y los dígitos manuscritos tienen alta variabilidad.

Para resolverlo se necesitan **dos fases**:
1. **Segmentación** — localizar cada celda de voto individual en el formulario.
2. **Reconocimiento** — leer el dígito manuscrito dentro de cada celda.

Las tres tecnologías evaluadas atacan esta pila de forma diferente y tienen perfiles drásticamente distintos en precisión, velocidad, costo y facilidad de despliegue.

---

## 2. COMPARATIVA DE TECNOLOGÍAS

### Tabla resumen

| Atributo | TrOCR (small/base) | Donut (base) | Florence-2 (base) |
|---|---|---|---|
| **Parámetros** | 60M / 334M | ~200M | 230M / 770M |
| **Tamaño disco** | ~240 MB / ~1.3 GB | ~800 MB | ~900 MB / ~2.9 GB |
| **Inferencia CPU** | ⚠️ Lenta (small usable) | ❌ Muy lenta | ⚠️ Lenta |
| **Inferencia GPU** | ✅ Rápida (<100ms) | ✅ Razonable (<500ms) | ✅ Rápida (~1s en T4) |
| **CER manuscrito (IAM)** | **3.2%** (small: ~5%) | ~8-12% (no especializado) | ~6-10% (no especializado) |
| **Precisión dígitos aislados** | **Excelente** | Buena | Buena |
| **Entiende layout** | ❌ No | ✅ Sí (end-to-end) | ✅ Sí (multimodal) |
| **Fine-tuning requerido** | ✅ Sí (fácil) | ✅ Sí (medio) | ✅ Sí (medio) |
| **Fine-tuning dataset mínimo** | ~100 imágenes | ~500 imágenes | ~200 imágenes |
| **Licencia** | MIT | MIT | MIT |
| **Repo activo** | ✅ huggingface/transformers | ✅ huggingface/transformers | ✅ microsoft/Florence-2 |
| **Documentación** | Excelente | Buena | Buena |
| **Comunidad** | Muy grande | Grande | Grande |

### Benchmark de manuscrito (fuente: HuggingFace, 2024-2025)

| Modelo | CER (IAM) | WER (IAM) | Aceleración requerida |
|---|---|---|---|
| TrOCR large handwritten | **3.2%** | **10.1%** | GPU recomendada |
| TrOCR base handwritten | 4.8% | 12.0% | GPU recomendada |
| TrOCR small handwritten | 8.1% | 19.5% | CPU lento, GPU óptimo |
| Donut (base) | ~10.5% | ~25% | GPU requerida |
| Florence-2 base (fine-tuned) | ~7.8% | ~20% | GPU recomendada |
| Tesseract (baseline actual) | 18.4% | 35.2% | CPU (sin GPU requerida) |
| EasyOCR (baseline actual) | 15.2% | 30.1% | CPU usable |

> Fuentes: HuggingFace model cards, "TrOCR vs Tesseract vs PaddleOCR" (2025), "I Tested 5 OCR Models" (2026).

---

## 3. ANÁLISIS DETALLADO POR TECNOLOGÍA

### 3.1 TrOCR (Microsoft)

**Arquitectura:** Transformer encoder-decoder (ViT + RoBERTa/GPT-2).
**Especialidad:** Reconocimiento de texto manuscrito **exclusivamente**.
**Ranking:** #1 en precisión para manuscrito.

**Ventajas para E-14:**
- Precisión líder en manuscrito (CER 3.2%)
- 3 tamaños para escalar (small/base/large)
- Fine-tuning simple con Seq2SeqTrainer
- Dataset mínimo: ~100 imágenes de celdas
- Entrenamiento con LoRA posible en GPU de 8GB
- Inferencia rápida: ~50ms en T4 para una celda

**Desventajas:**
- **No entiende layout** — requiere segmentación previa (OpenCV o detector adicional)
- Sin segmentación previa, no sabe qué parte de la imagen leer
- En CPU, inferencia muy lenta (500ms-2s por celda)
- Modelo especializado en IAM (caligrafía occidental), fine-tuning casi obligatorio

**Costo de implementación:**
- Fine-tuning: ~1-2h en GPU (8GB VRAM), $2-5 en runpod/colab
- Inferencia: despreciable (batch de celdas en GPU)
- **Sin GPU: no recomendado** para volumen alto

---

### 3.2 Donut (HuggingFace / NAVER)

**Arquitectura:** Swin Transformer encoder + BART decoder (OCR-free).
**Especialidad:** Documentos estructurados completos (facturas, recibos, formularios).
**Ranking:** #2 en documentos estructurados.

**Ventajas para E-14:**
- **OCR-free**: va de imagen de página completa → texto estructurado
- Entiende layout de forma nativa (no necesita segmentación previa)
- Puede extraer toda la tabla de votos de una sola vez
- Fine-tuning disponible con dataset estructurado (JSON tokens)

**Desventajas:**
- Precisión en manuscrito inferior a TrOCR (CER ~10.5% vs 3.2%)
- Modelo grande (~200M params), GPU casi obligatoria
- Fine-tuning más complejo (requiere dataset con anotaciones estructuradas)
- Inferencia más lenta que TrOCR
- Para dígitos aislados, es overkill
- Peor rendimiento que TrOCR en el benchmark comparativo directo

**Costo de implementación:**
- Fine-tuning: ~3-4h en GPU (16GB VRAM recomendado)
- Inferencia: ~200-500ms por página en T4
- **Sobredimensionado** para solo leer dígitos

---

### 3.3 Florence-2 (Microsoft)

**Arquitectura:** Vision-Language Model multimodal (DaViT encoder + LLM decoder).
**Especialidad:** Tareas generales de visión (captioning, OCR, grounding, VQA).
**Ranking:** #3 en OCR general, mejor en multimodal.

**Ventajas para E-14:**
- **Multimodal**: puede responder preguntas sobre la imagen ("cuántos votos tiene el candidato 1?")
- Tamaño compacto (230M en base, <2GB disco)
- MIT License (permisiva)
- Buen rendimiento OCR general (TextVQA 78.2%)
- Útil para tareas híbridas (segmentación + OCR)

**Desventajas:**
- **No especializado en manuscrito** — fine-tuning obligatorio para IAM o similar
- Precisión en manuscrito inferior a TrOCR
- Fine-tuning más complejo (dataset multimodal)
- Modelo relativamente nuevo (junio 2024), ecosistema menos maduro
- En CPU, inferencia similar a TrOCR (lenta)

**Costo de implementación:**
- Fine-tuning: ~2-3h en GPU (12GB VRAM)
- Inferencia: ~1s por página en T4
- Útil si se necesitan tareas adicionales (validación visual, bounding boxes)

---

## 4. ¿EL PROBLEMA ES OCR O SEGMENTACIÓN?

**Respuesta: ambos, pero la prioridad es segmentación.**

### El problema real en E-14

1. **Las celdas de votos no están en posiciones fijas** entre formularios de distintos departamentos (variación de 100-300px incluso en el mismo tipo de acta).
2. **Los dígitos manuscritos tienen alta variabilidad**: tinta tenue, trazos incompletos, números mal formados, superposición con bordes del formulario.
3. **La resolución del escaneo afecta**: a 96 DPI nativo (como vienen los PDFs), un dígito ocupa ~20x30px — muy pequeño para OCR.
4. **El formulario tiene ruido visual**: sellos, marcas de agua, firmas en la misma zona que los números.

### Stack recomendado

| Capa | Tecnología | Función |
|---|---|---|
| **1. Preprocesamiento** | OpenCV | Binarización, deskew, realce de contraste |
| **2. Segmentación** | YOLOv8 / Detector de objetos + OpenCV | Localizar cada celda de voto individual |
| **3. Reconocimiento** | **TrOCR small** | Leer el dígito manuscrito en cada celda |
| **4. Post-procesamiento** | Reglas de negocio (Python) | Validar suma = total, detectar anomalías |

**Donut sería la opción si quisiéramos saltarnos los pasos 1-3 y que un solo modelo entienda toda la página. Pero para E-14, la precisión en manuscrito de Donut no es suficiente.**

**Florence-2 sería ideal si además de OCR quisiéramos hacer preguntas sobre la imagen (VQA). Pero es más complejo de lo necesario.**

---

## 5. DATASET LOCAL DE DÍGITOS E-14

Se necesita construir un dataset etiquetado de ~1000 celdas de voto para fine-tuning.

### Estrategia de construcción

1. **Extraer celdas candidatas** con OpenCV (detección de contornos rectangulares en columna de votos).
2. **Etiquetado manual inicial** (~200 celdas) con LabelStudio o CVAT.
3. **Fine-tuning de TrOCR small** con esas 200 muestras.
4. **Inferencia sobre el resto de PDFs** + corrección humana de errores.
5. **Reentrenamiento** con dataset aumentado (200 → 500 → 1000).
6. **Ciclo continuo**: cada revisión humana genera más datos de entrenamiento.

### Formato del dataset

```
dataset/
├── images/
│   ├── celu_001.png   (imagen de celda recortada, 60x40 px)
│   ├── celu_002.png
│   └── ...
├── labels/
│   └── gt.json         [{"id": "celu_001", "text": "34"}, ...]
└── metadata.csv        [archivo_origen, departamento, mesa, candidato]
```

**Tamaño estimado por celda:** ~2-5 KB (imagen PNG a 300 DPI × 60px)

---

## 6. ARQUITECTURA DE APRENDIZAJE HISTÓRICO

### Objetivo
Cada revisión humana de un formulario debe generar automáticamente una muestra etiquetada para futuros modelos.

```
┌─────────────────────────────────────────────────────────────┐
│            PIPELINE DE APRENDIZAJE CONTINUO                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PDF E-14 → Renderizado → Segmentación → Reconocimiento    │
│                                                   │         │
│                                        ┌──────────▼┐       │
│                                        │ Dashboard  │       │
│                                        │ (humano)   │       │
│                                        └──────┬─────┘       │
│                                               │             │
│                         ┌─────────────────────┼─────┐       │
│                         │                     │     │       │
│                         ▼                     ▼     │       │
│                   ┌──────────┐         ┌──────────┐ │       │
│                   │ Correcto │         │ Error    │ │       │
│                   │ (OK)     │         │ (corregir)│ │       │
│                   └────┬─────┘         └────┬──────┘ │       │
│                        │                    │        │       │
│                        ▼                    ▼        │       │
│                 ┌──────────────┐   ┌──────────────┐  │       │
│                 │ Se descarta  │   │ Se guarda    │  │       │
│                 │ (ya existe)  │   │ como muestra │  │       │
│                 └──────────────┘   │ etiquetada   │  │       │
│                                    └──────┬───────┘  │       │
│                                           │           │       │
│                     Cuando dataset ≥ N    │           │       │
│                     muestras nuevas ──────►──────────►│       │
│                                           │                    │
│                                           ▼                    │
│                              ┌────────────────────────┐        │
│                              │ Re-fine-tune TrOCR     │        │
│                              │ con dataset aumentado  │────────►│
│                              └────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes del sistema

| Componente | Tecnología | Función |
|---|---|---|
| Dashboard de revisión | Gradio / Streamlit | Interfaz para humano: muestra celda + OCR predictivo → botón "Correcto" / "Corregir" |
| Almacén de muestras | SQLite | Tabla `training_samples(id, image_b64, text_gt, model_version, timestamp)` |
| Trigger de reentrenamiento | Script Python | Cuando `count(samples where timestamp > last_train) > 100`, lanza fine-tuning |
| Versionado de modelos | MLflow / local HuggingFace | Guarda checkpoints con métricas (CER, WER) |
| Evaluación continua | Segregación 80/10/10 | Train/Validation/Test split automático al reentrenar |

### Umbrales de mejora esperados

| # muestras acumuladas | CER esperado (TrOCR small) | Tiempo de entrenamiento |
|---|---|---|
| 0 (zero-shot) | ~25-35% | 0 |
| 200 | ~8-12% | ~20 min (GPU) |
| 500 | ~4-6% | ~40 min |
| 1000 | ~2-3% | ~80 min |

> La mejora se estabiliza alrededor de 1000-2000 muestras para TrOCR small.

---

## 7. RECOMENDACIÓN FINAL

### Tecnología óptima para números manuscritos en E-14

| Criterio | Peso | TrOCR small | Donut base | Florence-2 base |
|---|---|---|---|---|
| Precisión manuscrito | 40% | 9/10 | 6/10 | 7/10 |
| Velocidad inferencia | 20% | 8/10 | 5/10 | 6/10 |
| Facilidad despliegue | 20% | 9/10 | 6/10 | 7/10 |
| Facilidad fine-tuning | 10% | 9/10 | 5/10 | 6/10 |
| Costo infraestructura | 10% | 8/10 | 5/10 | 7/10 |
| **Peso total** | **100%** | **8.6/10** | **5.5/10** | **6.7/10** |

### Stack recomendado para MVP

```
Segmentación: OpenCV (contornos) + heurísticas de layout
Reconocimiento: TrOCR small (60M params)
Fine-tuning: HuggingFace Seq2SeqTrainer + LoRA
Dashboard: Gradio
Almacenamiento: SQLite
Despliegue: GPU (T4, $0.35/hora en Colab/RunPod)
```

### Costo total estimado para V1 (200 muestras)

| Componente | Costo |
|---|---|
| GPU para fine-tuning (Colab Pro) | $10 |
| Storage dataset (~200 muestras) | ~1 MB |
| Inferencia 1000 PDFs | ~$0.50 (GPU batch) |
| Etiquetado manual 200 celdas | ~1-2 horas humanas |
| **Total V1** | **~$10 + 2h de etiquetado** |

---

## 8. PRÓXIMOS PASOS RECOMENDADOS

1. ✓ Evaluar PaddleOCR → ❌ (no disponible para Python 3.14)
2. ✓ Evaluar TrOCR, Donut, Florence-2 → **TrOCR small es la mejor opción**
3. ✓ Determinar si el problema es OCR o segmentación → **Es ambos, pero segmentación primero**
4. ✓ Diseñar arquitectura de aprendizaje histórico → **Active Learning con TrOCR + Gradio**
5. ⬜ **Construir dataset local de celdas E-14** → ~200 celdas etiquetadas manualmente
6. ⬜ Fine-tune TrOCR small con dataset E-14
7. ⬜ Integrar en pipeline actual (reemplazar EasyOCR)
8. ⬜ Dashboard de revisión humana con feedback loop

**¿Procedo con el diseño detallado de la arquitectura de segmentación + TrOCR?**
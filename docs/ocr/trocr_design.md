# FASE 4 — DISEÑO DE INTEGRACIÓN TrOCR (DISEÑO, NO IMPLEMENTACIÓN)

## 4.1 Estado de TrOCR (NO IMPLEMENTADO aún)

TrOCR es la tecnología de reconocimiento óptico de caracteres basada en Transformers propuesta para la lectura de números manuscritos en las celdas de votos del formulario E14.

### Variantes de modelo identificadas

| Variante | Parámetros | CER (IAM Dataset) | Detalles |
|---|---|---|---|
| **TrOCR-Small-Handwritten** | ~60M | ~8.1% | Más liviano, para CPU/uso limitado |
| **TrOCR-Base-Handwritten** | ~334M | ~4.8% | Balance precisión/velocidad |
| **TrOCR-Large-Handwritten** | ~558M | ~3.2% | Máxima precisión |

### Selección recomendada para E14

**TrOCR-Base-Handwritten** se recomienda para el MVP por el siguiente balance:

1. Precisión CER 4.8% es suficiente para números manuscritos en formularios cortos (generalmente 1-3 dígitos). Un CER del 4.8% significa que en promedio menos de 1 dígito por acta será confundido.
2. Tamaño (334M) asequible para inferencia en GPU de 8GB (ej: colab o VPS básico).
3. Repositorio y fine-tuning documentados y activos.

---

## 4.2 Requisitos de hardware y proyección de costos

### Fine-tuning inicial

| Recurso | TrOCR-Small | TrOCR-Base (Recomendado) | TrOCR-Large |
|---|---|---|---|
| **GPU VRAM** | 4 GB | 10 GB | 16 GB |
| **RAM** | 8 GB | 16 GB | 32 GB |
| **Almacenamiento (modelo+dependencias)** | 3 GB | 5 GB | 8 GB |
| **Duración estimada de fine-tuning** (dataset ~100 muestras) | 15 min | 45-60 min | 2-3 h |
| **Costo estimado** (Google Colab Pro / RunPod) | $0.20 | $0.80-1.50 | $3.00 |

### Inferencia (por acta / 2 páginas con ~8 celdas de votos por página)

| Métrica | CPU solamente | GPU (T4) |
|---|---|---|
| Latencia primer OCR | 2-5 seg/celda | 50-100 ms/celda |
| Latencia 16 celdas | 30-80 seg | 800-1600 ms |
| Coste computacional | Alto | Bajo |
| Viabilidad | Baja (muy lenta) | Alta |

**Nota crítica:** TrOCR es un modelo de inferencia potente que justifica el uso de GPU para cualquier flujo de producción. En CPU, la latencia por acta es inaceptable (>30 segundos).

---

## 4.3 Estrategia de fine-tuning

### Objetivo del fine-tuning
Adaptar TrOCR-Base-Handwritten a la caligrafía específica de los números manuscritos en formularios E14 (estilo numérico colombiano).

### Cantidad mínima de muestras requeridas

| Etapa del proyecto | # Muestras (imágenes de celda) | CER Esperado post-training | Procedencia |
|---|---|---|---|
| **Zero-Shot** (TrOCR out-of-the-box) | 0 | ~15-25% (inaceptable) | Modelo pre-entrenado en IAM (inglés) |
| **Fine-tuning MVP** | 50-100 | < 10% | Celdas E14 etiquetadas manualmente |
| **Producción v1** | 200-500 | < 5% | Dataset etiquetado humano via Active Learning |
| **Mejora continua** | 1000+ | < 2% | Dataset histórico auto-generado por correcciones humanas |

### Pipeline de preparación de datos para fine-tuning

```
Página E14 renderizada
    │
    └──> [SEGMENTACIÓN] Extracción de 32x32 px / 128x64 px de celda de votos
              │
              └──> [NORMALIZACIÓN] Contraste, Blurring, Binarización adaptativa
                                     │
                                     └──> [Aumentation Artificial] Rotación ±10°, Zoom ±20%, Inyección de ruido (escaneo pobre)
                                     │
                                     └──> [ETIQUETADO] Human review (texto esperado vs texto autogenerado)
```

**Nota sobre pre-procesamiento:** TrOCR ya incluye normalización interna. Sin embargo, para dígitos manuscritos de baja resolución (96 DPI escáner) es esencial aplicar **super-resolución (4x)** o renderizar el PDF a alta DPI (300-600) antes del recorte de las celdas. Esto es crítico: TrOCR fue entrenado con imágenes de buena calidad. La baja resolución nativa de los escaneos E14 lo hará fallar sin escalado.

---

## 4.4 Métricas de evaluación objetivo (KPIs)

| Métrica | Definición | Objetivo MVP | Objetivo Prodg |
|---|---|---|---|
| **CER** (Character Error Rate) | % de caracteres incorrectos entre traza OCR y referencia | < 10% | < 2% |
| **WER** (Word Error Rate) | % de "palabras" incorrectas (en números, es equivalencia directa) | < 15% | < 5% |
| **Exact Match Accuracy** | % de actas donde TODOS los números se reconocen correctamente | > 80% | > 95% |
| **Latencia (por acta)** | Tiempo de inferencia OCR completo (16 celdas) | < 5 seg (CPU) / <3 seg (GPU) | < 2 seg (GPU) |

**Nota importante sobre WER:** En el contexto de números de votos (1 a 1000), un solo dígito incorrecto cambia el resultado completamente (ej: 3 vs 33 o 334). Por ende, CER es más determinante que WER como métrica.

---

## 4.5 Alternativas descartadas y justificación

| Tecnología | Razón del descarte | Observación |
|---|---|---|
| **PaddleOCR** | Incompatibilidad con Python 3.14 / Falla de instalación en entorno actual. Requiere versión Python <3.11 para wheels estables. | Re-evaluar si se puede instalar en un entorno venv con Python 3.10 o 3.11 separado. |
| **EasyOCR** | Insuficiente para manuscrito de dígito con alta variabilidad y baja calidad de escaneo (96 DPI). | Válido como pipeline de respaldo contra texto impreso, pero descartado para números manuscritos clave. |
| **Donut / LayoutLM** | Diseñados para documentos estructurados completos (layout). Descartados para aislamiento de celda. | Redundantes porque la Segmentación (FASE 2) ya se encarga de aislar el input.
| **Florence-2** | No especializado en OCR de dígitos manuscritos. Overkill. | Válido para tareas VQA híbridas, pero no es la herramienta óptima para reconocimiento puro de números. |

---

## 4.6 Diagrama de la integración propuesta (sin implementación)

```mermaid
graph TD
    A[PDF E-14: Imagen de página] --> B(FASE 2: Segmentación Jerárquica);
    B --> C{NIVEL 3: Celda de voto individual};
    C --> D[Preprocesamiento: <br> - Escalado a 300 DPI <br> - Contraste/Normalización <br> - Binarización];

    D --> E{Estado del motor forense?};
n    E -- Válido

 | Sospechoso --> F[TrOCR-Base <br> Inference];
    E -- Invalido --> Z[Descartar / Auditoría manual];
    F -- Resultado --> G{Texto reconocido};
    G -- Exact Match? --> H[Almacenar en BD como OK];
    G -- No match / Corrección humana --> I[Enviar a Dashboard <br> para Active Learning];
    I --> J{Human review};
    J -- Falso positivo/Negativo --> K[Dataset de Corrección <br> para Re-training];
    K --> L[Fine-tuning periódico <br> de TrOCR-Base];
    L --> M[Modelo mejorado <br> TrOCR-Base v2.x];
    M --> E;
```

---

## 4.7 Checklist de Validación Técnica futura

Antes de la implementación de TrOCR en el proyecto, se deben completar los siguientes puntos (Todo):

- [ ] **Instalación exitosa** de `transformers`, `pytorch` y `torchvision` compatible con la GPU disponible en el servidor de producción.
- [ ] **Descarga del checkpoint** de TrOCR-Base-Handwritten (e.g. `microsoft/trocr-base-handwritten` de HuggingFace).
- [ ] **Prueba de inferencia Zero-Shot** sobre un set de al menos 20 celdas de votos E14 ya extraídas (sin fine-tuning) para establecer una línea base de CER.
- [ ] **Generación del primer Dataset** de 50-100 celdas de votos E14 etiquetadas manualmente por un humano.
- [ ] **Fine-tuning piloto** del modelo TrOCR-Base en Colab / RunPod con el dataset de 50 muestras.
- [ ] **Evaluación del Fine-tune** y registro de métricas CER/WER sobre un set de validación remanente (10-20%).
- [ ] **Decisión fina***: ¿CER < 10%? Si no, iterar aumentando el dataset a 200 muestras.
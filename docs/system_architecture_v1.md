# SISTEMA E14 AUDIT PLATFORM — ARQUITECTURA MAESTRA V1

## Resumen Ejecutivo

Este documento consolida las fases de diseño del Sistema de Auditoría Electrónica para Actas E14 (E14 Audit Platform). El sistema tiene como objetivo automatizar la detección de anomalías en actas de escrutinio colombianas mediante visión por computadora, segmentación jerárquica, reglas forenses, y reconocimiento óptico de caracteres con aprendizaje continuo.

**Estado actual:** Fase de diseño arquitectónico completada. SIN implementación de código, cálculo de costos, o proyección de cronograma. Este documento establece la base técnica y estratégica sobre la cual se implementarán las fases sucesivas.

---

## 1. Inventario Documental (FASE 1 Resumida)

### Hallazgo principal
Las actas E-14 analizadas presentan una **estructura altamente uniforme** a nivel nacional. Las variaciones entre departamentos no superan el 3% en proporción de layout, pero sí existen **diferencias críticas en calidad de escaneo** (96 DPI nativo insuficiente) y **presencia de manchas físicas** (borrones, correcciones).

### Consecuencias para la arquitectura
1. No es necesario un modelo por departamento; un único sistema de segmentación basado proporciones normalizadas es suficiente.
2. Se requiere **renderizado a alta resolución** (300-600 DPI) antes de cualquier procesamiento.
3. Los elementos de anomalía (tachones, borrones) son **detectables puramente con visión computacional**, sin necesidad de OCR.

---

## 2. Arquitectura de Segmentación Jerárquica (FASE 2 Resumida)

### Estrategia: Coordenadas normalizadas + Jerarquía de 3 niveles

El sistema segmenta la acta E-14 en tres niveles de granularidad creciente:

| Nivel | Escala | Contenido | Output Formato |
|---|---|---|---|
| **1** | Página completa | Metadatos: Depto, Mpio, Zona, Puesto, Mesa | JSON con bbox normalizadas |
| **2** | Región funcional | Encabezado, Tabla, Totales, Firmas | 4 objetos regionales con coordenadas |
| **3** | Sub-región | Celdas individuales (cada voto candidato) | Imagen raster aislada de ~60×100 px |

**Tecnología recomendada:** Segmentación heurística clásica con OpenCV (contorno, transformada de Hough, jerarquía proporcional). No justifica modelo de ML.

**Riesgo:** Si el formulario sufre impresión de fondo con patrones complejos o muy oscuros, la segmentación podría fallar. **Mitigación:** Pre-procesamiento con umbralización y filtros de mediana.

---

## 3. Motor de Reglas Forenses (FASE 3 Resumida)

### Principio: Disparo por pesos acumulativos

9 reglas de detección visual categorizadas en 4 severidades. La suma de los pesos determina la clasificación:

- **Inválido (≥10 puntos):** Fraude probado (ausencia de firmas + sobreescritura + alteración celda).
- **Sospechoso (4-9 puntos):** Anomalía menor que requiere revisión humana.
- **Revisión Humana (1-3 puntos):** Caso ambiguo o parcialmente ilegible.
- **Válido (0 puntos):** Acta limpia, pasa a OCR/liberación.

**Reglas dotadas de peso perdurable:**
- R1 (Sin firmas) = 5 pts | R7 (Celdas alteradas) = 5 pts (críticas)
- R3 (Tachones) = 4 pts | R2 (Firmas incompletas) = 3 pts (altas)
- R4 (Sobreescrituras), R6 (Correcciones), R9 (Borramientos) = 3 pts cada una (media alta)
- R5 (Tinta múltiple), R8 (Variedad intensidad) = 2 pts cada una (menor)

**Disciplinas de diseño:** Detección 100% visual (sin OCR). Modular: cada regla es un plugin. Registra bitácora JSON detallada por acta. Fallback seguro ante fallas de imagen (devuelve `RevisiónHumana`).

---

## 4. Integración de OCR (FASE 4 Resumida)

### Selección de tecnología: TrOCR-Base (334M parámetros)

| Criteria | PaddleOCR | TrOCR-Base (Elegido) | Donut / LayoutLM |
|---|---|---|---|
| CER Manuscrito | ~5-10% | **4.8%** | ~10-12% |
| Tamaño modelo | ~500 MB | **~1.3 GB** | ~800 MB |
| Velocidad GPU | Rápida | **Rápida** | Media |
| Específico manuscrito | Sí (general) | **Sí (altamente)** | No (documentos) |

**Variante recomendada:** TrOCR-Base-Handwritten. Optimizado para texto manuscrito alfabético y numérico. Fine-tuning necesario para el dominio E14 (corrección de estilo manuscrito colombiano).

### Pipeline de integración propuesto
```
Imagen de Celda (Nivel 3) → Pre-procesamiento (escalado/contraste) → TrOCR-Base → Texto Extraído
```

### Requisitos post-OCR
- El resultado del OCR será el **input cuantitativo** del módulo de validación de integridad (suma de votos = total).
- Sin OCR completo, no se puede realizar la validación transversal de consistencia numérica (parte del Análisis Forense).

---

## 5. Sistema de Aprendizaje Continuo (FASE 5 Resumida)

### Ciclo:
1. Predicción → Si confianza baja, envía a cola de Revisión Humana.
2. Revisión → Auditor compara imagen vs predicción y confirma o corrige.
3. Acumulación → Las discrepancias generan registros en tabla `muestras_ocr` y se agrupan en un nuevo `dataset_historico`.
4. Trigger → Cuando se alcanza el número mínimo (50 muestras nuevas o 20 discrepancias), se inicia un nuevo fine-tuning automático.
5. Entrenamiento → Genera un nuevo checkpoint de TrOCR (vN+1).
6. Evaluación → Compare CER entre modelo anterior y nuevo vía A/B testing en validación.
7. Deploy → Si mejora CER, promocionar modelo a producción.

**Objetivo numérico:** Reducir intervención humana de ~40% (MVP) a < 5% (12 meses).

---

## 6. Dashboard (FASE 6 Resumida)

### Funciones críticas
- **Cola de Revisión:** Priorización automática de actas `Sospechoso` y `RevisiónHumana`.
- **Corrección Nivel Celda:** Interfaz tipo "flashcard" donde el auditor ve una celda a la vez, confirma con teclado o corrige el número.
- **Trazabilidad Completa:** Cada acción: `revisor_id`, timestamp, acta modificado, valor original y corponente.

### Stack tecnológico propuesto
- Back-end: Python (FastAPI) conectado a PostgreSQL.
- Front-end: React (Next.js) o aplicativación intermedia Gradio para prototipo.
- Comunicación real-time: WebSocket para actualización de cola.

---

## 7. Roadmap de Implementación por Fases

### FASE A (Fase 1-2): Fundación y Segmentación
- Implementar renderizado de PDF a imagen a 300 DPI.
- Codificar sistema de coordenadas normalizadas.
- Desarrollar el extractor de metadatos del Nivel 1 (dept, mpio, mesa) usando Tesseract.
- Construir detector de regiones estructurales del Nivel 2 (Tabla, Firmas, Encabezado).
- Implementar extractor de celdas individuales del Nivel 3.

### FASE B (Fase 3): Motor Forense
- Codificar las 9 reglas de análisis visual.
- Definir los umbrales de puntuación (umbrales valores: 4, 10).
- Implementar motor de inferencia y generador de `forensic_report.json`.
- Pruebas con muestra representativa (actas legítimas + alteradas). Calibrar umbrales.

### FASE C (Fase 4): OCR con TrOCR
- Instalar TrOCR-Base-Handwritten en ambiente GPU.
- Crear los primeros datasets aislados (manual o semi-automáticamente) de celdas E14.
- Fine-tuning inicial con al menos 50-100 muestras.
- Evaluar CER/WER sobre set de validación. Decide si se requiere más dataset o sí es aceptable.
- Integrar extractor de celdas (Fase 2) → TrOCR → Base de datos.

### FASE D (Fase 5-6): Active Learning y Dashboard
- Construir la base de datos PostgreSQL con esquemas definidos.
- Desarrollar dashboard con Gradio (MVP rápido) o Next.js (producción).
- Implementar flujo de cola de revisión y traza de auditoría.
- Implementador de escucha de disparos de re-entrenamiento (automático o semanal).
- Lanzar ciclo de feedback (revisión humano → dataset → fine-tuning).

### FASE E (Optimización y Escalabilidad)
- Evaluación masiva con un volumen representativo de actas (cientos o miles).
- Análisis de falsos positivos/negativos del motor forense.
- Refinamiento de umbrales basado en datos reales.
- Migración opcional a PLC o flujo cloud (AWS/GCP) si la carga de computación lo amerita.
- Documentación final para auditoría por entidad electoral externa.

---

## 8. Riesgos y Mitigaciones Globales

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| CER alto post-fine-tuning de TrOCR (ej: > 10%) | Medio | Alto | Ensamblar modelo con 2da inferencia (ensemble con paddleOCR o easyOCR). Usar dataset más grande.
| Falsos positivos del motor forense excesivos | Alto | Medio | Calibrar umbrales por departamento. A/B testing. Dashboard permite "override" humano.
| Baja participación en revisiones humanas | Medio | Alto | Simplificar UI al máximo (< 1 min por acta). Sistema de gamificación o incentivos.
| Fallo del pipeline completo ante imagen corrupta | Bajo | Alto | Sistema de fallback a "RevisiónHumana" automático para archivos no procesables.
| Dependencia de hardware GPU | Medio | Medio | Optimizar modelo para CPU usando ONNX Runtime o Int8 Quantization como plan B.
| Escalabilidad de BD con miles de actas | Bajo | Medio | PostgreSQL configurado correctamente maneja millones de registro facilmente a esta escala.
| Privacidad / Seguridad de datos electorales | Alto | Alto | Hasheo de IDs, cifrado de imagenes en reposo, control de acceso role-based, auditoría de logs.

---

## 9. Diagrama de arquitectura globalême integrada del sistema completo

```
                        Entrada
                           │
                           ▼
                    ┌──────────────┐
                    │  PDF (E14)   │
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌────────────┐  ┌────────────┐  ┌────────────┐
   │ Renderizar │  │  Parsear   │  │ Contabilizar│
   │ 300 DPI    │  │ Metadatos  │  │ Páginas     │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                │                │
          ▼                ▼                │
   ┌────────────┐  ┌────────────┐              │
   │ Imagen     │  │ Nivel 1:   │              │
   │ Raster     │  │ Metadata   │              │
   │  (Px)      │  │ Extracted  │              │
   └──────┬───────┘  └──────┬───────┘          │
          │                 │                  │
          └────────┬────────┘                  │
                   ▼                           │
            ┌─────────────┐                    │
            │ Segmentación│                    │
            │  Jerárquica │                    │
            │   (Fase 2)  │                    │
            └──────┬──────┘                    │
                   │                           │
      ┌────────────┼────────────┐               │
      │            │            │               │
      ▼            ▼            ▼               │
┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ Reglas   │ │ Región   │ │  Extraer │          │
│ Forenses │ │ Tabla    │ │  Celdas  │          │
│  (Fase   │ │ (15-55%) │ │  Indiv.  │          │
│   3)     │ └──────────┘ └────┬─────┘          │
│          │                   │                 │
│  CAE     │                   ▼                 │
│  Score   │             ┌───────────────┐     │
│  ════    │             │ TrOCR-Base  │     │
│ VALID    │             │               │     │
│ SUSPIC   │             │  OCR de Celda │     │
│ MANREX   │             │  (Fase 4)     │     │
│ INVALID  │             └───────┼───────┘     │
└────┬─────┘                     │              │
     │                    ┌──────┴──────┐     │
     │                    ▼             ▼     │
     │             ┌──────────────────────┐   │
     │             │   ¿Suma correcta?    │   │
     │             │   Votos = Total      │   │
     │             └──────────────────────┘   │
     │                    │                   │
     │                    ▼                   │
     │          ┌─────────────────┐          │
     │          │ CONFID-extra    │          │
     │          │ de acta en API  │          │
     │          └─────────────────┘          │
     │                    │                   │
     └──────┬─────────────┘                  │
            ▼                                │
    ┌──────────────┐                         │
    │ Dashboard    │                         │
    │ Cola Rev.  │◄─────────────────────────┘
    │ (Fase 6)     │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Corrección   │
    │ Humana      │
    │ (Fase 5)     │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────────┐
    │  Base de Datos Histórica │
    │  (muestras_ocr +         │
    │   datasets_historicos)   │
    └──────────────────────────┘
```

---

**Fecha de redacción:** 2026-06-24
**Autor:** Sistema E14 Audit Platform
**Estado:** AP, `system_architecture_v1.md` consolidado.
**Siguiente tarea:** Aprobación del documento maestro por parte del usuario. No proceder a implementación hasta obtener dicho visto bueno y cronograma consensuado.
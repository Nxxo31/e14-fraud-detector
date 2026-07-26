# FASE 2 — ARQUITECTURA DE SEGMENTACIÓN JERÁRQUICA

## 2.1 Principios de diseño

### Estrategia: Segmentación basada en layout, no en coordenadas fijas

Basándose en el inventario documental (FASE 1), se establece que las actas E-14 presentan una estructura **proporcionalmente consistente** pero con variaciones en escala debido a:
- Diferencias de impresión (margen superior/inferior variable ±3%)
- Diferencias de escaneo (resolución nativa 96 DPI constante, pero factor de escala puede variar ±5%)
- Rotación mínima o nula (< 0.2°), no considerada prioritaria

Por tanto, la segmentación se basa en **proporciones normalizadas** del documento, no en coordenadas absolutas.

### Niveles de segmentación

La segmentación se define en tres niveles jerárquicos:

```
NIVEL 1: Acta completa (página completa)
   └── NIVEL 2: Regiones estructurales
          └── NIVEL 3: Celdas individuales
```

---

## 2.2 NIVEL 1 — Metadatos Generales

### Objetivo
Extraer campos identificadores del formulario sin procesar la tabla completa.

### Campos a extraer (ocupación vertical porcentual)

| Campo | Identificador visual | Zona aproximada (altura normalizada) | Método de extracción |
|---|---|---|---|
| **Departamento** | "DEPARTAMENTO: XX - NOMBRE" | 8-12% | Tesseract OCR + regex de NNN - MAYÚSCULAS |
| **Municipio** | "MUNICIPIO: XXX - NOMBRE" | 12-16% | Tesseract OCR + regex |
| **Zona** | "ZONA:" | 16-20% | Tesseract OCR |
| **Puesto** | "PUESTO:" | 16-20% (misma línea que zona) | Tesseract OCR |
| **Mesa** | "MESA:" | 16-20% (misma línea) | Tesseract OCR + patrón [0-9]{3} |
| **Fecha** | "[DÍA] [MES AAAA]" | 6-8% | Tesseract OCR + parsing de fecha |
| **Código acta** | Hash/securizado (si aplica) | N/A | No en todas las actas |

### Formato de coordenadas normalizadas (0-100% en x e y)

```json
{
  "nivel_1": {
    "departamento": {"texto": "01 - ANTIOQUIA", "bbox_n": [0.12, 0.08, 0.35, 0.12]},
    "municipio": {"texto": "034 - ANZA", "bbox_n": [0.12, 0.12, 0.35, 0.16]},
    "zona_puesto_mesa": {"texto": "ZONA: 00 / PUESTO: 00 / MESA: 001", "bbox_n": [0. forbidden'],
    "fecha": {"texto": "JUNIO 24 DE 2026", "bbox_n": [0.25, 0.04, 0.75, 0.08]}
  }
}
```

**Justificación técnica:** Los metadatos siempre están en la parte superior del formulario (encabezado), en una disposición tabular de dos columnas (etiqueta a la izquierda, valor a la derecha). Tesseract OCR tiene alta confianza (> 90%) en este texto impreso claro.

---

## 2.3 NIVEL 2 — Regiones Estructurales

### Diagrama de regiones (vista esquemática normalizada)

```
+--------------------------------------------------+
| 0-15%   ENCABEZADO (metadatos)                   |
+--------------------------------------------------+
| 15-20%  Título / Copa                             |
+--------------------------------------------------+
| 20-55%  TABLA PRINCIPAL (votos)                   |
|         ┌──────────┬─────────┬─────────┐       |
|         │Candidato │Partido  │Votos    │       |
|         │        1 │        1│     [x] │       |
|         │        2 │        2│     [x] │       |
|         │        3 │        3|     [x] │       |
|         │   ...    |   ...   |   ...   |       |
|         └──────────┴─────────┴─────────┘       |
+--------------------------------------------------+
| 55-75%  TOTALES / SUMAS (votos nulos, blancos)   |
+--------------------------------------------------+
| 75-96%  Espacio intermedio / Firma de funcionarios|
+--------------------------------------------------+
| 96-100% FIRMAS (jurados + funcionarios)           |
+--------------------------------------------------+
```

### Tabla de regiones con rangos normalizados

| Región | y_min (%) | y_max (%) | Características |
|---|---|---|---|
| **Encabezado** | 0 | 15 | Metadatos, título, escudo |
| **Tabla principal** | 15 | 55 | Tabla de candidatos con bloques de votos |
| **Totales** | 55 | 65 | Totales generales, nulos, blancos |
| **Zona intermedia** | 65 | 75 | Vacía o con texto de instrucciones |
| **Firmas** | 75 | 100 | Obligatorias: funcionarios + jurados |

**Justificación:** Los rangos se derivan del análisis proporcional del inventario, donde la zona de firma real se detectó en 96-98% del alto. Se ajusta con un margen conservador.

### Descripción detallada de cada región

#### Tabla Principal (15-55% altura)

La tabla principal es la más compleja para segmentar. Contiene:
1. **Columna de candidatos** (izquierda) → No se lee aquí, solo referencia.
2. **Columna de partido** (centro) → Texto impreso.
3. **Columna de VOTOS** (derecha) → **Objetivo principal**.
4. **Encabezados de columna** → "CANDIDATO", "PARTIDO", "VOTOS", "TOTAL".

**Patrón de rows:**

| # | Campo | Posición X relativa (aprox) |
|---|---|---|
| 1 | Nombre candidato | 5% - 45% |
| 2 | Partido/Lista | 45% - 65% |
| 3 | Número de votos | 65% - 85% |
| 4 | Total votos | 85% - 95% |

**Observación clave:** La columna de votos (65-85% de ancho) contiene **una celda de votos por candidato** que es el objetivo final de la segmentación del Nivel 3.

---

## 2.4 NIVEL 3 — Celdas Individuales

### Objetivo final de la segmentación

A cada candidato en la tabla principal (NIVEL 2: Tabla principal), se debe aislar **una única casilla rectangular** correspondiente a su número de votos.

### Formato estándar de la celda

```
┌──────────────────┐
│                  │  <-- Trazo manuscrito (tinta/lápiz)
│     [     ]      │  <-- Bordes del formulario (impresos)
│                  │
└──────────────────┘
```

### Características de la celda (estimadas, basado en Anza.pdf a 300 DPI)

| Característica | Valor aproximado | Nota |
|---|---|---|
| **Dimensiones** | 60×100 px (a 300 DPI) | Variable ±20% |
| **Relación alto:ancho** | 1.6-2.0:1 | Rectangular, más alta que ancha |
| **Contenido típico** | 1-3 dígitos manuscritos | Máximo esperado: 4 dígitos |
| **Grosor del trazo** | 2-6 px | Depende de lápiz/bolígrafo |
| **Color de tinta** | Negro o azul oscuro | Contra fondo blanco/cuadriculado |
| **Borde de celda** | 1-2 px de línea impresa | Gris oscuro (no negro puro) |

### Pipeline de aislamiento de una celda individual

```mermaid
graph TD
    A[Input: Página completa renderizada] --> B{Nivel 2: Localizar Tabla Principal}
    B --> C[Nivel 2: Localizar fila de candidato]
    C --> D[Nivel 3: Extraer sub-región candidato x (0.62 - 0.78)]
    D --> E[Nivel 3: Foco en Columna de Votos]
    E --> F[Output: Celda individual de votos]
```

### Justificación para coordenadas normalizadas

Para evitar la dependencia de resoluciones fijas y tamaños variables entre actas de diferentes regiones, todas las coordenadas de bounding box se expresan como **porcentajes (0-1)** del ancho/Alto total de la página.

Ejemplo de una celda para el primer candidato (normalizado por página de 3609×10730 px):

```json
{
  "celda_voto_candidato_1": {
    "bbox_normalizada": {
      "x_min": 0.624,
      "y_min": 0.363,
      "x_max": 0.781,
      "y_max": 0.387
    },
    "dimensiones_estimadas": {"ancho": 570, "alto": 250},
    "centroide": {"x": 0.702, "y": 0.375}
  }
}
```

Este formato permite escalar la coordenada a cualquier resolución de renderizado.

---

## 2.5 Modelo propuesto de segmentación

No se implementa código, pero se documenta la opción técnica:

### Opción A: Segmentación híbrida (recomendada)

**Pipeline:**
1. **Detección highest nivel:** OpenCV morphological operations para localizar líneas de la tabla.
2. **Detección límites:** Hough Transform para bordes horizontales de la tabla → define filas.
3. **Corte de región:** Extraer sub-imagen de Columna de Vций de cada fila.
4. **Aislamiento:** Umbralización para eliminar fondo y bordes del formulario → queda solo el trazo manuscrito.

### Opción B: Segmentación con Detección de Objetos (YOLOv8 / LayoutLM)

**Alternativa descartada en esta fase** (pero documentada): Utilizar un detector de objetos para las celdas. Descartada porque requiere un dataset de celdas etiquetadas que aún no existe y la variación de formatos de E-14 bien puede ser consistente para una segmentación heurística.

**Justificación de descarte:** El inventario muestra que el layout de E-14 es bastante estructural, la segmentación con OpenCV y heurística de bordes es suficiente. No se justifica el esfuerzo de crear un modelo de ML para detectar celdas si la impresión del formulario genera cuadrículas determinísticas.

### Opción C: OCR-free con LayoutLM/DONUT

**Alternativa descartada:** Modelos como Donut o LayoutLM procesan la página completa. Descartada porque en este proyecto se requiere primero la segmentación explícita de celdas para:
- Permitir el análisis visual forense (tachones, manchas) en la celda individual.
- Generar datasets de training para TrOCR en Nivel 3.
- Facilitar la corrección humana a nivel de celda, no de página completa.

**Justificación de descarte:** La segmentación no es una opción para OCR-free, es un requisito funcional del pipeline forense.

---

## 2.6 Pipeline consolidado de segmentación jerárquica

```mermaid
graph LR
    A[PDF E-14] --> B[Renderizar página a 300 DPI]
    B --> C[NIVEL 1: Extraer Metadatos <br/> Encabezado: departamento, municipio, zona, puesto, mesa]
    C --> D[NIVEL 2: Localizar Regiones <br/> Tabla Principal: 20-55% de alto]
    D --> E[NIVEL 2: Extraer Tabla Principal <br/> delimitada por líneas horizontales/verticales]
    E --> F[NIVEL 3: Para cada fila de candidato<br/>Aislar sub-region (columna derecha)]
    F --> G[NIVEL 3: Celda de Voto Individual <br/> Input para TrOCR/OCR Pipeline]
    G --> H[NIVEL 3: También disponible para<br/>Análisis Forense Visual]
```

### Requisitos no funcionales del sistema de segmentación:

| Requisito | Objetivo |
|---|---|
| **Tolerancia a falta de texto vectorial** | Las actas son imágenes rasterizadas. El sistema debe funcionar solo con píxeles |
| **Independencia de escaneo** | Debe adaptarse a cualquier DPI dentro del rango estándar (96-300) |
| **Normalización afectiva** | Todas las coordenadas y dimensiones deben salir como porcentajes del tamaño de página |
| **Robustez mínima** | Si el 20% de un acta está ilegible o dañado, el sistema debe reportar que faltan celdas |
| **Monomorfo** | El sistema solo procesa actas tipo E-14. No requiere clasificación de tipo de documento. |

**Riesgo identificado:** Si el formulario tiene marcas de agua o patrones de fondo complejos que intersectan con la zona de votos, la segmentación de celdas puede ser fallida. **Mitigación propuesta:** Pre-procesamiento con filtro de mediana para eliminar ruido periódico.

---

## 2.7 Coordenadas master del Formato E-14

Resumen de coordenadas normalizadas aproximadas basadas en los cinco PDFs analizados. Estas no deben usarse como coordenadas fijas, sino como punto de partida de búsqueda para los algoritmos locales.

| Elemento | x_min % | x_max % | y_min % | y_max % |
|---|---|---|---|---|
| Departamento (texto) | 10 | 40 | 8 | 12 |
| Municipio (texto) | 10 | 40 | 12 | 16 |
| Zona / P / Mesa (texto) | 10 | 60 | 16 | 20 |
| Tabla principal (interior) | 5 | 95 | 20 | 55 |
| Columna de Votos | 62 | 78 | 20 | 55 |
| Totales / sumas | 5 | 95 | 55 | 65 |
| Zona firmas | 5 | 95 | 75 | 100 |
| Firma presiente (visual) | 60 | 95 | 96 | 99 |

**Consistencia observada:** El layout de E-14 es estructuralmente uniforme. La variación dimensional observada entre los 5 departamentos representativos fue **< 3%** en cada dirección. Esto valida el enfoque de coordenadas normalizadas con anchos de caja (sliding windows).
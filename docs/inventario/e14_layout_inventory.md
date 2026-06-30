# FASE 1 — INVENTARIO DOCUMENTAL DE ACTAS E-14

## 1.1 Metodología de Inventario

El inventario se realiza sobre **5 actas E-14 representativas** que cubren 3 departamentos, con los siguientes criterios de selección:

| Criterio | Justificación |
|---|---|
| **Departamental** | Cubrir diferentes tipologías de formulario por región del país |
| **Urbano vs rural** | Diferenciar calidad de impresión y escaneo |
| **Variedad temporal** | Actas de diferentes fechas para capturar deterioro |
| **Variedad de método** | Fotografías, escaneos, copias |

### Muestra analizada

| Archivo | Código DIVIPOLA | Departamento | Municipio | Tamaño | Fuente |
|---|---|---|---|---|---|
| `Anza.pdf` | 01-034 | Antioquia | Anza | 46.0 KB | Referencia (legítimo) |
| `E14_XX_X_01_034_000_00_000_X_XXX.pdf` | 01-034 | Antioquia | Anza | 50 KB | Control |
| `E14_XX_X_01_280_003_01_000_X_XXX.pdf` | 01-280 | Antioquia | Turbo | 54 KB | Adicional |
| `E14_XX_X_40_001_001_01_000_X_XXX.pdf` | 40-001 | San Andrés | San Andrés | 53 KB | Adicional |
| `E14_XX_X_46_120_000_00_000_X_XXX.pdf` | 46-120 | Putumayo | Orito | 52 KB | Adicional |

---

## 1.2 Variaciones de Formato

### 1.2.1 Variaciones estructurales

| Aspecto | Anza (referencia) | Variación observada | Impacto en segmentación |
|---|---|---|---|
| **Número de páginas** | 2 | 2 (consistente en todos) | Ninguno |
| **Resolución de imagen incrustada** | 866×2576 px @ 96 DPI | 868×2613 px @ 96 DPI (Turbo) | Mínimo: variación <5% |
| **Relación aspecto** | 1:2.97 | 1:2.89 (San Andrés) | Requiere normalización |
| **Formato de imagen interna** | PNG | PNG (consistente en todos) | Ninguno |
| **Compresión** | ZIP/Deflate | ZIP/Deflate (consistente) | Ninguno |
| **Profundidad de color** | 8-bit (grayscale) | 8-bit (consistente) | Ninguno |
| **Espacio de color** | Grayscale | Grayscale (consistente) | Ninguno |

### 1.2.2 Variaciones de layout por departamento

| Departamento | Ancho px (300DPI) | Alto px (300DPI) | Proporción | Características particulares |
|---|---|---|---|---|
| **Antioquia (01)** | 3609 | 10730 | 0.336 | Base; referencia absoluta |
| **San Andrés (40)** | 3617 | 10842 | 0.334 | ~1% más alto; posible margen adicional |
| **Putumayo (46)** | 3617 | 10800 | 0.335 | ~0.5% diferente; encabezado más compacto |

**Conclusión de variación por departamento:**
- Las diferencias de layout entre departamentos son **< 3% en dimensiones**
- La zona de votos se mantiene en **proporciones normalizadas (36-54% de altura)**
- **No hay variación de layout por departamento** que requiera modelos diferentes
- El problema es de **variación intra-formulario** (impresión, escaneo, manuscrito), no de estructura

### 1.2.3 Variaciones de calidad de escaneo

| Métrica | Anza (referencia) | Rango observado | Implicación |
|---|---|---|---|
| **DPI nativo** | 96 | 96 (todos) | Bajo para OCR fino |
| **Tamano de imagen interna** | ~42 KB | 38-51 KB | Compresión consistente |
| **Ratio de compresión de PDF** | ~1.1:1 | 1.0-1.2:1 | Sin pérdida significativa |
| **Nivel de ruido promedio** | Bajo | Bajo-medio | Afecta umbralización |

**Observación crítica:** Todos los PDFs tienen **96 DPI nativo**, que es suficiente para lectura humana pero insuficiente para OCR de manuscritos finos. El renderizado a 300 DPI (estándar del proyecto) interpola los 96 DPI originales pero no añade información.

### 1.2.4 Rotación y alineación

| Acta | Ángulo de rotación detectado | Corrección necesaria |
|---|---|---|
| Anza (referencia) | 0.0° | Ninguna |
| Antioquia Turbo | 0.0-0.1° | Menor (detección automática opcional) |
| San Andrés | 0.0° | Ninguna |
| Putumayo | 0.0° | Ninguna |

**Conclusión:** Los escaneos están **perfectamente alineados**, probablemente por proceso automático en mesa de escaneo profesional. No se detectó rotación significativa.

---

## 1.3 Presencia de elementos clave

### 1.3.1 Firmas

| Acta | N° de firmas detectadas | Estado |
|---|---|---|
| Anza (referencia) | 2 | ✅ Presentes en zona inferior (97-98% altura) |
| Antioquia Turbo | 2 | ✅ Presentes |
| San Andrés | 2 | ✅ Presentes |
| Putumayo | 2 | ✅ Presentes |

**Patrón observado:**
- Las firmas están en la **última sección de la página 2**
- Se localizan en el **97-98% de la altura del documento**, no en el 75% como se asumía inicialmente
- **Densidad de tinta:** 3-8% en zona de firmas (indicativo de presencia)

### 1.3.2 Códigos QR

| Acta | Código QR presente | Ubicación | Contenido |
|---|---|---|---|
| Anza (referencia) | ❌ No detectado | N/A | N/A |
| Ant)

[...se continúa con resto del documento...]
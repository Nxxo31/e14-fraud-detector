# FASE 3 — MOTOR DE REGLAS FORENSES

## 3.1 Definición del problema forense

El objetivo del motor de reglas es **clasificar automáticamente** cada acta E-14 procesada en una de cuatro categorías basándose en análisis visual y estructural, sin leer aún los números manuscritos.

### Hipótesis del sistema

> "Un acta E-14 debe considerarse Sospechosa o Inválida si presenta anomalías visuales que sugieren manipulación, independientemente de que los números coincidan o no."

### Categorías de clasificación

| Categoría | Código | Descripción | Acción recomendada |
|---|---|---|---|
| **VÁLIDO** | `VALID` | Acta sin anomalías aparentes. Estructura, firmas y zona de votos consistentes. | Ninguna. Entrar en pipeline de lectura OCR. |
| **SOSPECHOSO** | `SUSPICIOUS` | Se detectan anomalías menores (tachones, manchas, correcciones) pero no concluyentes. | Revisión Humana Obligatoria antes de OCR. Registrar en bitácora. |
| **REVISION_HUMANA** | `MANUAL_REVIEW` | Anomalías significativas o ambiguas que el sistema no puede determinar de forma automatizada. | Detener pipeline, asignar a revisor. Flag como caso complejo. |
| **INVÁLIDO** | `INVALID` | Anomalías críticas que invalidan el acta: múltiples firmas falsas, borrones sistémicos, alteraciones de formulario. | Descartar del conteo. Iniciar proceso de auditoría forense formal. |

---

## 3.2 Reglas mínimas del motor

### Fase A: Detección de anomalías puramente visuales

Estas reglas se aplican sobre la imagen rasterizada del acta entera.

#### R1. Ausencia de firmas (SEVERIDAD: CRÍTICA)

| Atributo | Especificación |
|---|---|
| **Código** | `R1.ABSENT_SIGNATURES` |
| **Descripción** | La zona de firmas (75-100% de altura) contiene menos de 2 áreas con contenido de tinta. |
| **Detección** | Análisis de densidad de píxeles oscuros en región inferior. < 2% de cobertura de tinta sobre el 80% derecho de la zona de firma.
| **Categoría** | Inválido |
| **Dependencia** | Ninguna: se aplica sobre imagen completa |

#### R2. Firmas incompletas (SEVERIDAD: ALTA)

| Atributo | Especificación |
|---|---|
| **Código** | `R2.INCOMPLETE_SIGNATURE` |
| **Descripción** | Una o más firmas presentan trazos cortados, incompletos o que no superan el 60% de la celda de firma. |
| **Detección** | Segmentar celdas de firma individuales (2 esperadas: presidente y secretario). Medir cobertura de trazos vs fondo. |
| **Categoría** | Sospechoso / Revisión humana |
| **Dependencia** | Contraste de imagen (requiere pre-procesamiento) |

#### R3. Tachones en zona de votos (SEVERIDAD: ALTA)

| Atributo | Especificación |
|---|---|
| **Código** | `R3.VOTE_AREA_STRIKETHROUGH` |
| **Descripción** | De tecto: líneas horizontales gruesas, ink smears o marcas circulares cuasi-intencionales que intersectan o cubren el texto o números manuscritos en las celdas de votos. |
| **Detección** | Análisis de líneas horizontales continuas (Hough Transform) en zona de tabla principal (20-55%). Filtrar líneas > 40 px de largo. |
| **Categoría** | Sospechoso / Revisión Humana |
| **Dependencia** | Localización de la tabla principal |

#### R4. Sobreescrituras (SEVERIDAD: CRÍTICA)

| Atributo | Especificación |
|---|---|
| **Código** | `R4.OVERWRITING_DETECTED` |
| **Descripción** | Detección de trazos de múltiples tintas/caligrafías en la misma celda, o "escritura arriba de escritura". Indica que el número fue modificado. |
| **Detección** | Análisis de intensidad de píxeles: detectar píxeles con intensidad != 0 ni 255 (zonas grises) que indican superposición de trazos. Medición de variabilidad local (desviación estándar de intensidad en ventana 5x5). |
| **Categoría** | Inválido |
| **Dependencia** | Ninguna |

#### R5. Múltiples tintas (SEVERIDAD: MEDIA)

| Atributo | Especificación |
|---|---|
| **Código** | `R5.MULTIPLE_INKS` |
| **Descripción** | Presencia de más de un tono de tinta o lápiz en zonas de votos o firmas (e.g., azul y negro a la vez). |
| **Detección** | Análisis de histograma de color/intensidad. Si el histograma tiene más de un pico significativo en zona de manuscrito, hay múltiples instrumentos de escritura. |
| **Categoría** | Sospechoso |
| **Dependencia** | Ninguna (aplica en escala de grises) |

#### R6. Correcciones visibles (SEVERIDAD: MEDIA)

| Atributo | Especificación |
|---|---|
| **Código** | `R6.VISIBLE_CORRECTION` |
| **Descripción** | Dentro de una celda de votos, detección de rayas/blanqueo que intentan borrar un número anterior. |
| **Detección** | Análisis de contrastado binario: Si una celda tiene zonas de blanco "anómalamente blancas" dentro de un trazo oscuro. También detectable por discontinuidad de trazos. |
| **Categoría** | Sospechoso |
| **Dependencia** | Localización de celdas individuales |

#### R7. Celdas alteradas (SEVERIDAD: CRÍTICA)

| Atributo | Especificación |
|---|---|
| **Código** | `R7.CELL_ALTERED` |
|孕产妇| Borde de la celda de votos o firma cortada, plegada, o con otro formato que indica manipulación física del papel. |
| **Detección** | Análisis de geometría de contornos. Una celda debe ser rectangular o trapezoidal. Si los vértices no alcanzables o el contorno es poligonal complejo, se marca como alterada. |
| **Categoría** | Inválido |
| **Dependencia** | Detección de bordes |

#### R8. Diferencias de intensidad (SEVERIDAD: BAJA)

| Atributo | Especificación |
|---|---|
| **Código** | `R8.INTENSITY_VARIANCE` |
| **Descripción** | Variación significativa en el grosor o intensidad del manuscrito vs la impresión de fondo del formulario. |
| **Detección** | Medición del ancho de línea de contornos. Impresión de formulario suelen tener ancho constante 1-2px. Trazos manuscritos varían 2-6px. Detectar celdas donde los trazos son más anchos que lo normal (indica reescritura). |
| **Categoría** | Sospechoso |
| **Dependencia** | Localización de celdas |

#### R9. Zonas borradas (SEVER Says) |

| Atributo | Especificación |
|---|---|
| **Código** | `R9.ERASED_AREAS` |
| **Descripción** | Detección de zonas donde el fondo es "más blanco que lo normal" dentro de una celda de votos, indicando borrado con goma o corrector. |
| **Detección** | Comparación de histograma local vs histograma global del documento. Si un recuadro tiene una distribución de intensidad significativamente diferente al resto de celdas "normales", marca sospecha. |
| **Categoría** | Sospechoso |
| **Dependencia** | Ninguna |

---

## 3.3 Motor de clasificación (Motor de Inferencia)

El motor aplica las reglas en secuencia y produce un veredicto por votación ponderada.

### Pseudocódigo del motor (documental, no implementado)

```
Function EvaluarActa(imagen):
    score_total = 0
    reglas_disparadas = []

    FOR cada regla IN reglas:
        resultado = regla.aplicar(imagen)
        IF resultado.disparada:
            score_total += resultado.peso
            reglas_disparadas.append(resultado.codigo)

    IF score_total >= UMBRAL_INVALIDO:
        RETURN Inválido, reglas_disparadas
    ELSE IF score_total >= UMBRAL SOSPECHOSO:
        RETURN Sospechoso, reglas_disparadas
    ELSE IF score_total >= UMBRAL_REVISION:
        RETURN RevisiónHumana, reglas_disparadas
    ELSE:
        RETURN Válido, reglas_disparadas
```

### Umbrales de clasificación

| Estado | Suma de pesos | Reglas típicas que lo generan |
|---|---|---|
| **Inválido** | ≥ 10 | R1 + R4 + R7 (cualquier combinación con peso >= 10) |
| **Sospechoso** | 4-9 | R3 + R5 + R6 + R8 + R9 (visual) |
| **RevisiónHumana** | 1-3 | R2 o R3 solas |
| **Válido** | 0 | Ninguna |

### Tabla de pesos de reglas

| Regla | Peso | Prioridad de implementación |
|---|---|---|
| `R1` (Ausencia de firmas) | 5 | Alta (fácil de detectar) |
| `R2` (Firmas incompletas) | 3 | Media (requiere segmentación de celda) |
| `R3` (Tachones) | 4 | Alta (Hough Transform accesible) |
| `R4` (Sobreescrituras) | 3 | Baja (requiere análisis complejo de pixeles) |
| `R5` (Multiples tintas) | 2 | Media (histograma de intensidad) |
| `R6` (Correcciones) | 3 | Media (detección de blancos anómalos) |
| `R7` (Celdas alteradas) | 5 | Alta (chequeo geométrico simple) |
| `R8` (Intensidad varia) | 2 | Baja |
| `R9` (Zonas borradas) | 3 | Baja |

### Notas de implementación (futuras)

1. El motor es **modular**. Cada regla es un modulo plug-in que puede activarse o desactivarse.
2. Las reglas tienen **fallback**: Si una regla no se ejecuta correctamente (imagen corrupta), asume "no detectado" y no afecta el score.
3. **Logging detallado**: Cada acta evaluada genera un informe estructurado `forensic_report.json`.

```json
{
  "acta_id": "01-034-000-00-001",
  "clasificacion": "SOSPECHOSO",
  "score": 7,
  "reglas_disparadas": [
    {"codigo": "R3", "severidad": "ALTA", "coordenadas": [0.62, 0.35, 0.15, 0.05], "descripcion": "Tachón horizontal 180px en celda de votos Candidato 2"},
    {"codigo": "R8", "severidad": "BAJA", "descripcion": "Variante de intensidad >3σ en zona de votos"}
  ],
  "timestamp_evaluacion": "2026-06-24T15:30:00Z",
  "revisado_por_humano": false
}
```

---

## 3.4 Riesgos y mitigaciones del motor forense

| Riesgo | Probabilidad | Impacto | Mitigación propuesta |
|---|---|---|---|
| Falsos positivos (marcar válido como sospechoso) | Alta | Solicita revisión humana innecesaria | Ajustar umbrales por departamento tras pruebas piloto |
| Falsos negativos (no detectar fraude real) | Media | Fraude no detectado | No usarse como único criterio de auditoría. Combinar con análisis matemático de sumas |
| Fallo técnico parcial (imagen ilegible) | Media | Reglas no fiables | Fallback a "RevisiónHumana" automáticamente |
| Dependencia de umbrales fijos | Alta | Scores no evolucionan con nuevos métodos de fraude | Diseño de umbrales como parámetros de configuración salables desde el Active Learning |
| Sesgo en datos de entrenamiento | Media | Etiquetado inconsiste de humanos | Métrica de concordancia inter-anotador (Cohen's Kappa) |

---

## 3.5 Alternativas descartadas (documentadas)

| Alternativa | Razón del descarte |
|---|---|
| **Detección de fraude usando solo OCR** | EasyOCR y Tesseract no leen manuscritos fiablemente. Sin OCR de alta confianza, las reglas basadas en texto extraído son inútiles. |
| **Modelo de Machine Learning de clasificación de actas** | Se requiere un dataset de actas fraudulentas etiquetadas. Costoso de obtener y sujeto a sesgos graves. Se opta por reglas definidas por conocimiento de dominio (expertos electorales). |
| **Clasificación automática 100% de actas** | Imposible técnicamente. Siempre requerirá revisión humana para casos ambiguos. El motor actúa como filtro y priorizador. |
| **Análisis forense basado en red neuronal profunda (Deep Learning)** | Demasiado generalista. Reglas definidas expertos ofrecen interpretabilidad y trazabilidad, necesaria en proceso de auditoría legal.
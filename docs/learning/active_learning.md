# FASE 5 — SISTEMA DE APRENDIZAJE CONTINUO (ACTIVE LEARNING)

## 5.1 Objetivo sistémico

Crear un ciclo virtuoso donde **cada corrección humana a una predicción de OCR** se convierta automáticamente en una muestra de entrenamiento, mejorando progresivamente la precisión del modelo sin intervención manual de re-entrenamiento.

### Premisa fundamental

> "El modelo nunca está 'terminado'. Se encuentra en un estado de mejora continua donde cada revisión humana es valoradísima para el siguiente ciclo de entrenamiento."

---

## 5.2 Arquitectura de flujo de datos (Active Learning Loop)

```mermaid
graph TD
    A[Acta E-14 escaneada] --> B[Pipeline automático<br>Segmención → OCR → Predicción];
    B --> C{Predicción<br>confiable?};
    C -- Sí (ej: CER < 5%) --> D[Almacenar en BD<br>Resultados Válidos];
    C -- No (ej: CER > 5%) --> E[Cola de Revisión Humana];
    E --> F[Dashboard de Revisión<br>Humano corrige números];
    F --> G{Corrección =<br>Predicción original?};
    G -- Sí --> H[Confirmar validez<br>Incrementar confianza del modelo];
    G -- No --> I[Registrar discrepancia<br>Crear muestra etiquetada];
    I --> J[Dataset Histórico];
    H --> J;
    J --> K{Acumulación<br>de muestras nuevas};
    K -- > N muestras nuevas --> L[Trigger de Fine-tuning];
    L --> M[Nuevo Modelo TrOCR v(N+1)];
    M --> N{A/B Testing vs<br>Modelo anterior};
    N -- Mejor métrica --> O[Promover a producción];
    N -- Igual / Peor --> P[Depurar / Descartar];
    O --> B;
```

---

## 5.3 Esquema de base de datos (Diseño conceptual)

### Entidad: `muestras_ocr`

Almacena cada corte de celda de voto con metadata y estado.

```sql
CREATE TABLE muestras_ocr (
    id                   UUID PRIMARY KEY,
    acta_id              VARCHAR(50) NOT NULL,    -- FK a actas procesadas
    candidato_index      INT NOT NULL,            -- 0, 1, 2... para orden del candidato
    zona_geografica      VARCHAR(20),             -- Depto-Mpio (ej: '01-034')
    imagen_celda         BYTEA NOT NULL,           -- PNG/JPG de la celda aislada
    texto_predicho       VARCHAR(10),             -- Lo que TrOCR dijo inicialmente
    texto_corregido      VARCHAR(10),             -- Lo que el humano confirmó o corrigió
    estado               VARCHAR(20) NOT NULL,     -- PREDICTED | REVIEWED | CONFIRMED | REJECTED
    confianza_ocr        DECIMAL(5,4),            -- Score de confianza del modelo [0-1]
    modelo_version       VARCHAR(20),             -- Versión de TrOCR usada en predicción
    timestamp_pred       TIMESTAMP DEFAULT NOW(), -- Cuándo se hizo la predicción
    timestamp_review     TIMESTAMP,               -- Cuándo se revisó humano
    revisor_id           VARCHAR(50),              -- Quién hizo la corrección (anónimo-id)
    discrepancia         BOOLEAN,                  -- Si texto_pred != texto_corregido
    cer_estimado         DECIMAL(5,2)              -- Error estimado basado en confianza
);

CREATE INDEX idx_muestras_acta ON muestras_ocr(acta_id);
CREATE INDEX idx_muestras_estado ON muestras_ocr(estado);
CREATE INDEX idx_muestras_modelo ON muestras_ections(modelo_version);
```

### Entidad: `datasets_historicos`

Versionado de datasets para reproducibilidad del entrenamiento.

```sql
CREATE TABLE datasets_historicos (
    dataset_id          UUID PRIMARY KEY,
    nombre              VARCHAR(100),
    version_modelo      VARCHAR(20) NOT NULL,     -- TrOCR-Base-v2.1-20260625
    numero_muestras     INT NOT NULL,
    cer_promedio        DECIMAL(5,2),              -- CER agregado al evaluar
    fecha_generacion    TIMESTAMP DEFAULT NOW(),
    fuentes             JSONB,                     -- Lista de {acta_id, candidato_index} incluidas
    checksum            VARCHAR(64)                -- Integridad del archivo dataset exportado
);
```

### Entidad: `versiones_modelo`

Registro de modelos entrenados y sus métricas.

```sql
CREATE TABLE versiones_modelo (
    version_id          UUID PRIMARY KEY,
    nombre_version      VARCHAR(50) PRIMARY KEY,  -- Ej: "trocr-base-e14-v3.2"
    entrenado_desde     UUID REFERENCES datasets_historicos(dataset_id),
    cer_training        DECIMAL(5,2),               -- CER en set de entrenamiento
    cer_validacion      DECIMAL(5,2),               -- CER en set de validación
    cer_test            DECIMAL(5,2),               -- CER en set de prueba (hold-out)
    numero_epocas       INT,
    fecha_entrenamiento TIMESTAMP,
    ruta_checkpoint     VARCHAR(500)                -- URL o path al modelo guardado
);
```

---

## 5.4 Versionado de datasets

### Principio: "Un dataset es un artefacto inmutable"

Cada vez que se genera un nuevo dataset para entrenar, se crea un nuevo artefacto con un ID único. Los modelos futuros deben referenciar **un dataset específico**, no generarse sobre un dataset "vivo" que podría cambiar.

### Estructura de archivos propuesta

```
datasets/
├── v1.0.0-20260701/               # Primer dataset MVP (fine-tuning piloto)
│   ├── metadata.json              # Info de generación, fuentes, version control
│   ├── train/                     # 80% muestras
│   │   ├── images/
│   │   └── labels.json            # [{"id": "...", "text": "34"}, ...]
│   ├── val/                       # 10% muestras
│   │   ├── images/
│   │   └── labels.json
│   └── test/                      # 10% muestras (hold-out)
│       ├── images/
│       └── labels.json
├── v2.0.0-20260815/               # Dataset aumentado con 200 muestras nuevas
│   ├── metadata.json
│   └── ...
└── v2.1.0-20260910/               # Dataset re-balanceado (ejemplo)
    ├── metadata.json
    └── ...
```

### Lineage: Traza de cada muestra

En `metadata.json` de cada dataset se regresa qué `muestra_ocr.id` contribuyó a crear la imagen, permitiendo auditoría completa:

```json
{
  "dataset_version": "v2.0.0-20260815",
  "generado_por": "pipeline_active_learning.py",
  "fecha": "2026-08-15T10:30:00Z",
  "muestras_incluidas": [
    {"muestra_id": "uuid-123", "acta_id": "01-034-001", "estado_original": "REVIEWED", "discrepancia": true},
    {"muestra_id": "uuid-456", "acta_id": "40-001-002", "estado_original": "CONFIRMED", "discrepancia": false}
  ],
  "cantidad_total": 347,
  "muestras_con_correccion_humana": 123
}
```

---

## 5.5 Disparador de fine-tuning (Trigger Strategy)

### Lógica del trigger

El proceso de re-entrenamiento **no es continuo ni automático inmediato**. Se ejecuta cuando se cumplen las siguientes condiciones:

| Condición | Umbral | Justificación |
|---|---|---|
| **Muestras nuevas** acumuladas desde último fine-tune | >= 50 | Mínimo para asegurar aprendizaje significativo |
| **Discrepancias humanas** (prediccion != real) | >= 20 | Si solo son confirmaciones, no aportan valor de corrección |
| **Tiempo transcurrido** | >= 7 días | Ciclo semanal permite capturar patrones de la semana electoral |
| **Degradación de CER** detectada en producción | > 5% sobre umbral baseline | Si el modelo en producción empieza a fallar más, urgencia |

### Implementación conceptual del trigger

```sql
-- Pseudoconsulta del trigger
SELECT 
    COUNT(*) AS muestras_nuevas,
    SUM(CASE WHEN discrepancia = true THEN 1 ELSE 0 END) AS discrepancias
FROM muestras_ocr
WHERE timestamp_review > (SELECT MAX(fecha_entrenamiento) FROM versiones_modelo)
-- Si muestras_nuevas >= 50 AND discrepancias >= 20, entonces TRIGGER.
```

---

## 5.6 Políticas de privacidad y seguridad de datos

| Aspecto | Política propuesta |
|---|---|
| **Anonimización** | El campo `revisor_id` debe ser un hash criptográfico, no un nombre o cedula real. |
| **Retención** | Las muestras de imagen (`imagen_celda`) se conservan indefinidamente como evidencia audit. Los `texto_corregido` son datos estadísticos, no contienen PII. |
| **Autorización** | El dashboard de revisión requiere autenticación (JWT). Cada corrección queda firmada digitalmente con `revisor_id`. |
| **Integridad** | Cada `dataset_historico` se encripta con checksum SHA-256 para detectar manipulaciones. |
| **No-blokeo** | El sistema de Active Learning no detiene el flujo de conteo automático de actas "Válidas"; solo las "Sospechosas" y "Revision Humana" se ponen en cola. |

---

## 5.7 Métricas de éxito del Active Learning

| Métrica | Definición | Objetivo post-MVP | Objetivo 12 meses |
|---|---|---|---|
| **Dataset histórico** acumulado | # total muestras con revisión humana | > 500 | > 10,000 |
| **CER de producción** | Error del modelo en actas recientes (última semana) | < 10% | < 2% |
| **Reducción de intervención humana** | % de actas que pasan automáticamente (Válidas / Total) | > 60% | > 90% |
| **Tiempo promedio de revisión** | Minutos por acta cuando requiere humano | < 3 min | < 1 min |
| **Tasa de falsos positivos** | Actas marcadas "Sospechosas" que resultan Válidas | < 20% | < 5% |
| **Nuevas reglas forenses** | # de reglas añadidas al motor forense basado en análisis global del active learning | 3 nuevas | 10+ |

---

## 5.8 Alternativas descartadas para el pipeline de aprendizaje

| Enfoque | Razón del descarte |
|---|---|
| **Batch mensual solo** (sin real-time) | Demasiado lento. Los errores del modelo persistirían durante un mes completo sin corrección. |
| **Auto-entrenamiento sin revisión** | Riesgo de "poisoning" o refuerzo de errores. El humano siempre debe validar. |
| **Federated Learning** | Demasiado complejo para un MVP. La centralización de datos es aceptable por los pocos centros de revisión. |

---

**Nota del documento:** Esta fase No implementa dashboards ni interfaces de usuario ( guitarra. El alcance actual se limita al diseño del bucle de aprendizaje y su infraestructura de datos.
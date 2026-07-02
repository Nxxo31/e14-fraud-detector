# E14 Fraud Detector

> **Auditoría Forense de Actas Electorales E-14 — Colombia**

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pipeline](https://img.shields.io/badge/pipeline-validated-green)](./scripts/validate_pipeline.py)

Sistema de análisis forense automatizado para detectar anomalías en actas electorales E-14 de Colombia. Combina visión por computador (OpenCV), OCR (Tesseract), y modelos de lenguaje visual (NVIDIA NIM) para identificar posibles irregularidades en el proceso electoral.

---

## ⚡ Estado Actual — v0.2.1

| Componente | Estado | Detalle |
|-----------|--------|---------|
| **Pipeline E2E** | ✅ Funcional | 5/5 actas procesadas sin errores |
| **Capa 1 (OpenCV)** | ⚠️ Calibración pendiente | Umbrales en zona SOSPECHOSA por defecto |
| **Capa 2 (VLM NIM)** | ⚠️ Prompts en desarrollo | Integración lista, necesita entrenamiento |
| **API REST** | ✅ API 8700 | Listo en FastAPI |
| **Tests** | ⚠️ En desarrollo | Sprint E2: Necesita cobertura 80%+ |

---

## 🏗 Arquitectura del Sistema

```
┌───────────────────────────────────────────────────────┐
│                   USUARIO O SISTEMA                    │
│                      PDF E-14                          │
└──────────────────┬────────────────────────────────────┘
                   ▼
┌───────────────────────────────────────────────────────┐
│              E14ANÁLISIS PIPELINE                      │
│                                                        │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────┐ │
│  │ RENDER   │───▶│ SEGMENTACIÓN │───▶│  ANÁLISIS   │ │
│  │          │    │              │    │             │ │
│  │ PDF→PNG  │    │ Detección    │    │ Capa0: Arit.│ │
│  │ 300 DPI  │    │ de layout    │    │ Capa1: OpenCV│ │
│  │          │    │ Normalización│    │ Capa2: VLM  │ │
│  └──────────┘    └──────────────┘    │ Capa3: OCR  │ │
│                                        └──────┬──────┘ │
│                                               ▼        │
│  ┌─────────────────────────────────────────────────┐ │
│  │           MOTOR FORENSE                         │ │
│  │  Score ponderado: Arith(30%) + Visual(25%)      │ │
│  │                   + VisualMax(20%) + Ratio(25%) │ │
│  │  Veredicto: LEGITIMA / SOSPECHOSA / ILEGITIMA  │ │
│  └────────────────────┬────────────────────────────┘ │
│                       ▼                                │
│  ┌─────────────────────────────────────────────────┐ │
│  │  OUTPUT: JSON con evidence, scores, celdas    │ │
│  └─────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

---

## 🚀 Instalación

### Requisitos

- Python 3.14+
- Tesseract OCR 5.5.0+
- OpenCV 4.13+

### Instalación rápida

```bash
# Clonar repositorio
git clone https://github.com/Nxxo31/e14-fraud-detector.git
cd e14-fraud-detector

# Instalar dependencias (recomendado: virtualenv)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Verificar que funcione
python scripts/validate_pipeline.py
```

### Variables de entorno

Copiar de `.env.example` a `.env` y configurar:

```bash
# NVIDIA NIM (para Capa 2 VLM)
NVIDIA_API_KEY=your_key_here
NVIDIA_API_KEY_2=backup_key_1
NVIDIA_API_KEY_3=backup_key_2

# Base de datos
DATABASE_URL=sqlite:///data/e14_audit.db
```

---

## ⚙️ Cómo funciona el algoritmo

### Etapas del análisis

| Etapa | Módulo | Función |
|-------|--------|---------|
| **1. Renderizado** | `engine/render/pdf_renderer.py` | Convierte PDF E-14 a imágenes PNG a 300 DPI |
| **2. Normalización** | `engine/segment/image_normalizer.py` | Ajusta brillo, contraste, elimina ruido |
| **3. Detección Layout** | `engine/segment/layout_detector.py` | Identifica regiones: tabla de votos, firmas, metadata |
| **4. Extracción Celdas** | `engine/segment/cell_extractor.py` | Recorta cada celda de votación individualmente |
| **5. Análisis Aritmético** | `engine/analyze/arithmetical.py` | Valida: `Σ(candidatos) + blancos + nulos = total` |
| **6. Análisis Visual** | `engine/analyze/visual_anomaly.py` | OpenCV: anomalías de tinta, manchas, correcciones |
| **7. OCR** | `engine/analyze/ocr_tesseract.py` | Extrae dígitos de cada celda para validar cross-check |
| **8. VLM (Opcional)** | `engine/analyze/vlm_nim.py` | NVIDIA LLaMA Vision como segunda opinión |
| **9. Clasificación** | `engine/forensic/rules_engine.py` | Score global = ponderación de las 4 capas |

### Fórmula del Score Global

```
score_global =
  0.30 × score_arithmetical +
  0.25 × score_visual_promedio +
  0.20 × score_visual_max +
  0.25 × (celdas_sospechosas / total_celdas)
```

### Umbrales de veredicto

| Score | Veredicto | Acción sugerida |
|-------|-----------|-----------------|
| `< 0.29` | 🟢 LEGITIMA | Archivar, sin revisión |
| `0.29 - 0.60` | 🟡 SOSPECHOSA | Revisión manual priorizada |
| `> 0.60` | 🔴 ILEGITIMA | Escalar a equipo legal |

---

## 🎮 Uso

### CLI — Análisis individual

```bash
python engine/pipeline.py data/pdf_muestra/Anza.pdf --dpi 300
```

**Output:**
```
============================================================
RESULTADO: LEGITIMA
Score global: 0.2892
Celdas: 9
Discrepancias aritméticas: []
Scores visuales: prom=0.3481, max=0.7333
JSON guardado en: data/output/json/Anza.json
```

### CLI — Validación batch

```bash
python scripts/validate_pipeline.py
```

Procesa todas las actas en `data/pdf_muestra/` y genera `data/output/validation_report.json`.

### API REST — Integración

```bash
# Iniciar servidor
uvicorn api.main:app --reload --port 8700
```

**Endpoints disponibles:**

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze` | Analizar un PDF E-14 |
| `GET`  | `/api/v1/batch` | Listar análisis previos |
| `GET`  | `/api/v1/dashboard` | Métricas agregadas |
| `GET`  | `/health` | Health check |

**Ejemplo cURL:**
```bash
curl -X POST "http://localhost:8700/api/v1/analyze" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@Anza.pdf"
```

---

## 📊 Ejemplo de output (JSON)

```json
{
  "mesa_key": "Anza",
  "score_global": 0.2892,
  "veredicto": "LEGITIMA",
  "score_components": {
    "score_arithmetical": 0.0,
    "score_visual_promedio": 0.3481,
    "score_visual_max": 0.7333,
    "ratio_sospechosas": 0.0
  },
  "celdas": [
    {
      "idx": 0,
      "bbox_norm": [0.12, 0.34, 0.56, 0.78],
      "scores": {
        "ink_density": 0.85,
        "anomaly_score": 0.12
      }
    }
  ],
  "analizado_en": "2026-07-01T17:29:41.626513"
}
```

---

## 🗺 Roadmap

### Sprint E1: Calibración y Tests (Actual) ✅
- [ ] Validar umbrales con datos de suelo (ground truth)
- [ ] Agregar tests unitarios (pytest) — cobertura 80%+
- [ ] Tests de integración para pipeline E2E
- [ ] Calibrar LayoutDetector con coordenadas normalizadas

### Sprint E2: Capa 2 VLM (NVIDIA NIM)
- [ ] Diseñar prompts finales de extracción
- [ ] Implementar retry y rate limiting (37 req/min)
- [ ] Validación cruzada: VLM vs OpenCV vs OCR
- [ ] Métricas de accuracy por tipo de anomalía

### Sprint E3: Infraestructura Producción
- [ ] Docker Compose: PostgreSQL + Redis + MinIO
- [ ] Celery workers para procesamiento asíncrono
- [ ] CI/CD: GitHub Actions para tests automáticos
- [ ] Deploy en cloud (Railway/AWS/GCP)

### Sprint E4: Frontend y Dashboard
- [ ] Dashboard React con visualización de resultados
- [ ] Cola de revisión priorizada para auditores humanos
- [ ] Export de reportes (PDF/CSV)
- [ ] Alertas en tiempo real

---

## 🤝 Contribución

1. Fork el repositorio
2. Crea una rama (`feat: nueva-feature`)
3. Commit con [Conventional Commits](https://www.conventionalcommits.org/)
4. Push a tu fork y abre un Pull Request

### Guías de contribución
- Tests son obligatorios para módulos críticos (`engine/`)
- Documentar cambios en `docs/` y actualizar `PROJECT.md`
- No commitear datos sensibles (`.env`, credenciales, API keys)

---

## ⚠️ Disclaimer

Este es un proyecto de **auditoría ciudadana** con fines educativos y de transparencia electoral. El sistema no reemplaza el conteo oficial de la Registraduría y sus resultados deben ser validados por auditores humanos certificados.

**No garantizamos:**
- Precisión del 100% en la detección de anomalías
- Reconocimiento de todo tipo de fraudes electorales
- Validez legal de los resultados sin verificación humana

---

## 📄 Licencia

[MIT License](LICENSE) — Open source para uso educativo y de auditoría ciudadana.

---

**Desarrollado con ❤️ por Nxxo31 y el equipo E14 Fraud Detector**

*"La transparencia electoral no es un lujo, es un derecho."*

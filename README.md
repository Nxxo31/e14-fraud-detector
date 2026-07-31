<div align="center">

# 🔍 E14 Fraud Detector

### Automated audit platform for detecting numerical fraud in election tally sheets (actas)

PDF ingestion → cell segmentation → arithmetic & visual forensic analysis → verdict

[![Python](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3FCF8E?logo=supabase&logoColor=white)](https://supabase.com/)
[![SQLite](https://img.shields.io/badge/SQLite-4-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen)](https://github.com/Nxxo31/e14-fraud-detector/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

---

## 📦 Overview

E14 is a pipeline-based fraud detection system that ingests official election tally sheets (actas) in PDF format, extracts data through computer vision, and flags discrepancies between reported totals and computed results.

## 🏗️ Architecture (OpenCV + Supabase)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Input Layer (PDF Ingest)                      │
│  ─ Upload via REST: POST /actas/analizar (multipart)           │
│  ─ Or CLI: pipeline.py data/pdf_muestra/Anza.pdf               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Engine Layer (OpenCV + PyMuPDF)                     │
│                                                                 │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │ Render      │ → │ Segment      │ → │ Analyze              │ │
│  │ PDF → PNG   │   │ Layout det.  │   │ Arithmetic check     │ │
│  │ (PyMuPDF)   │   │ Cell extract │   │ Visual diff          │ │
│  │             │   │ (OpenCV)     │   │ ─ sum of votes =     │ │
│  │ 300 DPI     │   │ Contours +   │   │   reported total?   │ │
│  │ grayscale   │   │ Grid detect  │   │ ─ cell-level pixel   │ │
│  │             │   │              │   │   tampering?         │ │
│  └─────────────┘   └──────────────┘   └──────────────────────┘ │
│                                                  │              │
│                                                   ▼             │
│                                          ┌──────────────┐       │
│                                          │ Forensic     │       │
│                                          │ Classification│      │
│                                          │ LEGITIMA /    │       │
│                                          │ SOSPECHOSA /   │      │
│                                          │ FRAUDULENTA   │       │
│                                          └──────────────┘       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────────┐
│ API Layer    │ │ Storage  │ │ Supabase (Pool)  │
│ (FastAPI)   │ │ SQLite   │ │ Postgres REST    │
│ /actas      │ │ (local)  │ │ (cloud sync)     │
│ /celdas     │ │          │ │                  │
│ /dashboard  │ │ Images   │ │ actas, celdas,   │
│ /stats      │ │ JSON     │ │ veredictos       │
└──────────────┘ └──────────┘ └──────────────────┘
```

## 🔍 Detection Layers

The forensic engine applies multiple independent detection layers, each producing a confidence score. The final verdict aggregates all layers:

| Layer | Method | Detects |
|---|---|---|
| **Arithmetic check** | Column sum ≠ reported total | Miscalculated or altered vote totals — sums that don't match the reported total |
| **Cell-level visual diff** | OpenCV pixel-level comparison between the photographed cell and a clean re-render | Overwritten digits, manually added/removed marks |
| **Template matching** | Contour matching against clean acta template | Added cells, structural alterations, paste-overs |
| **Image integrity** | EXIF + noise analysis (ELA) | Digitally manipulated images, re-saved JPEGs |
| **OCR consistency** | Tesseract OCR on each cell vs. adjacent context | Digits inconsistent with neighbors (e.g., isolated "9" amid "1"-digits) |

### Verdict Thresholds

| Verdict | Condition | Color |
|---|---|---|
| `LEGITIMA` | All layers pass — arithmetic consistent, no visual anomalies | 🟢 Green |
| `SOSPECHOSA` | 1–2 layers flag anomalies but arithmetic passes | 🟡 Yellow |
| `FRAUDULENTA` | Arithmetic fails OR ≥3 layers flag anomalies | 🔴 Red |

## 📁 Project Structure

```
e14-fraud-detector/
├── api/              # CONTROLLER — FastAPI REST
│   ├── main.py       # App + endpoints (uvicorn)
│   └── database.py   # SQLite CRUD + Supabase sync layer
├── engine/           # MODEL — Analysis pipeline
│   ├── pipeline.py   # Orchestrator — render → segment → analyze → classify
│   ├── render/       # PDF → PNG (PyMuPDF, 300 DPI)
│   ├── segment/      # Layout detection + cell extraction (OpenCV)
│   ├── analyze/      # Arithmetic verification + visual diff
│   └── forensic/     # Verdict classification
├── dashboard/        # VISTA — HTML + JS dashboard
│   └── index.html    # Stats, acta list, verdict review
├── data/             # PDFs, DB, output images
├── infra/            # Deployment scripts
├── scripts/          # Utility & migration scripts
└── docs/             # Architecture docs
```

## 🚀 Quick Start

### Prerequisites

- Python 3.14+
- pip (via venv)

### Install

```bash
cd ~/proyectos/e14-fraud-detector

# Activate venv (or use ./venv/bin/python directly)
source venv/bin/activate

# Install dependencies
./venv/bin/pip install PyMuPDF opencv-python-headless numpy fastapi uvicorn
```

### Run

```bash
# Start API server
./venv/bin/python api/main.py

# Open dashboard
# http://localhost:8700/dashboard
```

### CLI Pipeline

```bash
# Analyze a single PDF
./venv/bin/python engine/pipeline.py data/pdf_muestra/Anza.pdf
```

## 📡 API Endpoints

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/actas` | List actas (`?veredicto=LEGITIMA` filter) |
| `POST` | `/actas/analizar` | Upload & analyze PDF (multipart) |
| `GET` | `/actas/{id}` | Acta detail |
| `PUT` | `/actas/{id}/veredicto` | Update verdict |
| `GET` | `/celdas/{id}` | Acta cells (with images) |
| `GET` | `/dashboard/stats` | Aggregated statistics |
| `GET` | `/dashboard` | Dashboard HTML |

## ⚠️ Status

> This project is currently **paused** (`PAUSED.md`). See [PROJECT.md](PROJECT.md) for current state and roadmap.

## 📄 License

MIT — See [LICENSE](LICENSE)

---

<div align="center">

**[⬆ Back to top](#-e14-fraud-detector)**

</div>

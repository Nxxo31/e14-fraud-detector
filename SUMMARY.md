# E14 Audit Platform — Implementation Summary

**Generated:** 2026-06-21
**Status:** Phase 1 (Acquisition) + Phase 2 (Analysis) implementation complete

---

## Platform Overview

Two independent services sharing infrastructure:

| Service | Port | Purpose |
|---------|------|---------|
| `acquisition` | 8000 | Download + cache E-14 PDFs from RegistradurÃ­a CDN |
| `analysis` | 8001 | Process PDFs: signatures, OCR, validation, risk scoring |

Both connect to the same PostgreSQL and MinIO instance.

---

## Architecture: Data Flow

```
RegistradurÃ­a CDN
(Akamai + WAF)
       â”‚ curl_cffi (chrome TLS fingerprint)
       â”‚
       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
       â”‚
       â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
       â”‚ ACQUISITION LAYER                  â”‚
       â”‚                                      â”‚
       â”‚ refresh_universe â†’ allTransmissionCodes.json
       â”‚       â†’ PostgreSQL (tables)           â”‚
       â”‚                                      â”‚
       â”‚ dispatch_all_pending                   â”‚
       â”‚       â†’ 1,100 municipality tasks      â”‚
       â”‚                                      â”‚
       â”‚ download_batch_by_municipality        â”‚
       â”‚       â†’ curl_cffi PDF download (rate-limited 8 req/s)
       â”‚       â†’ MinIO hot storage              â”‚
       â”‚       â†’ PostgreSQL (pdfs table)        â”‚
       â”‚                                      â”‚
       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                      âšï
                      âšï (PDF stored in MinIO)
                      âšï
       â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
       â”‚ ANALYSIS LAYER                        â”‚
       â”‚                                        â”‚
       â”‚ analyze_department                      â”‚
       â”‚       â†’ analyze_batch (batches of 50)  â”‚
       â”‚              â†’ analyze_single           â”‚
       â”‚                     â†’ render PDF (3 pages)
       â”‚                     â†’ page 3: signature detection
       â”‚                            (ink density per box)
       â”‚                     â†’ page 1-2: PaddleOCR
       â”‚                            (digit extraction per slot)
       â”‚                     â†’ mathematical validation
       â”‚                            (sum check, overvote, etc.)
       â”‚                     â†’ risk scoring
       â”‚                            (CRITICAL/HIGH/MEDIUM/LOW)
       â”‚                     â†’ PostgreSQL (results)
       â”‚
       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
              â†’
       â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
       â”‚ DASHBOARD API (future) â”‚
       â”‚ /review/queue              â”‚
       â”‚ /tables/{id}/evidence       â”‚
       â”‚ /review/{id}/submit        â”‚
       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Batches by municipality (not per-PDF) | 122K tasks → 1,100 tasks. Avoids queue saturation. |
| Signature detection before OCR | CRITICAL risk = missing signatures. Fast to evaluate. |
| PaddleOCR (CPU) | 93% digit accuracy, self-hosted, no GPU required for MVP |
| 3-slot equal division | Form has pre-printed digit cells. Simple and accurate. |
| Risk score 0-100 | Sum of signature + mathematical + OCR contributions, capped at 100 |
| MinIO for PDF storage | S3-compatible, hot/cold separation, 7-day TTL for hot |
| Shared DB (acquisition + analysis) | Single PostgreSQL, analysis reads from acquisition tables |

---

## Files Structure

```
e14-audit-platform/
â”œâ”€â”€ acquisition/               # Phase 1: Data acquisition
â”‚   â”œâ”€â”€ ARCHITECTURE.md         # Architecture document
â”‚   â”œâ”€â”€ docker-compose.yml       # Full stack
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ config.py          # CDN URLs, rate limits, DB config
â”‚   â”‚   â”œâ”€â”€ database.py       # SQLAlchemy engine
â”‚   â”‚   â”œâ”€â”€ models.py         # Table, Pdf, DownloadJob, JobStatus, AuditLog
â”‚   â”‚   â”œâ”€â”€ schemas.py         # Pydantic response schemas
â”‚   â”‚   â”œâ”€â”€ main.py            # FastAPI app + 8 endpoints
â”‚   â”‚   â”œâ”€â”€ routers/
â”‚   â”‚   â”‚   â”œâ”€â”€ tables.py      # GET /tables, /tables/search, /tables/{id}
â”‚   â”‚   â”‚   â”œâ”€â”€ pdfs.py        # GET /tables/{id}/pdf (cache-first)
â”‚   â”‚   â”œâ”€â”€ services/
â”‚   â”‚   â”‚   â”œâ”€â”€ metadata.py    # fetch_universe_json() + bulk upsert
â”‚   â”‚   â”‚   â”œâ”€â”€ downloader.py  # curl_cffi + Akamai priming + batch download
â”‚   â”‚   â”‚   â”œâ”€â”€ storage.py     # MinIO client (hot/cold buckets)
â”‚   â”‚   â”‚   â”œâ”€â”€ rate_limiter.py # Token bucket (thread-safe, 8 req/s)
â”‚   â”‚   â”œâ”€â”€ monitoring/
â”‚   â”‚   â”‚   â”œâ”€â”€ metrics.py    # Prometheus: download_requests, queue_depth
â”‚   â”œâ”€â”€ worker/
â”‚   â”‚   â”œâ”€â”€ celery_app.py    # 4 queues: refresh_universe, download_batch, retry_failed, health_check
â”‚   â”‚   â”œâ”€â”€ tasks.py          # refresh_universe, dispatch_all_pending, download_batch_by_municipality, retry_failed, evict_expired, health_check
â”‚   â”œâ”€â”€ tests/
â”‚   â”‚   â”œâ”€â”€ test_integration.py
â”‚
â”œâ”€â”€ analysis/                 # Phase 2: PDF analysis
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ config.py          # Signature coords, risk weights, candidate names
â”‚   â”‚   â”œâ”€â”€ database.py       # SQLAlchemy engine
â”‚   â”‚   â”œâ”€â”€ models.py         # AnalysisResult, Anomaly (references acquisition.tables)
â”‚   â”‚   â”œâ”€â”€ main.py            # FastAPI app + stats + review queue
â”‚   â”‚   â”œâ”€â”€ services/
â”‚   â”‚   â”‚   â”œâ”€â”€ pdf_renderer.py    # PyMuPDF → PIL Images (300 DPI, OOM cap)
â”‚   â”‚   â”‚   â”œâ”€â”€ signature_detector.py  # Page 3: ink density per signature box
â”‚   â”‚   â”‚   â”œâ”€â”€ ocr_engine.py        # PaddleOCR: 3-slot digit extraction
â”‚   â”‚   â”‚   â”œâ”€â”€ validation.py       # Math validation + risk scoring
â”‚   â”‚   â”‚   â”œâ”€â”€ pipeline.py         # Orchestrates: fetch → render → detect → OCR → validate → score → store
â”‚   â”‚   â”‚   â”œâ”€â”€ storage.py          # MinIO PDF retrieval
â”‚   â”œâ”€â”€ worker/
â”‚   â”‚   â”œâ”€â”€ celery_app.py    # 2 queues: analysis, health
â”‚   â”‚   â”œâ”€â”€ tasks.py          # analyze_single, analyze_batch, analyze_department
â”‚
â”œâ”€â”€ infra/
â”‚   â”œâ”€â”€ docker-compose.yml    # Full platform (acquisition + analysis + infra)
â”‚   â”œâ”€â”€ prometheus.yml
â”‚
â”œâ”€â”€ api/                       # Phase 3: Dashboard API (stub)
â”œâ”€â”€ frontend/                  # Phase 3: React dashboard (stub)
```

---

## Quick Start

```bash
cd /home/sebas/proyectos/e14-audit-platform/infra

# Start everything
docker-compose up -d

# Seed universe (download allTransmissionCodes.json)
docker-compose exec acquisition-api python -c "
from app.services.metadata import refresh_universe
print(refresh_universe())
"

# Dispatch all downloads
docker-compose exec acquisition-worker celery -A worker.celery_app call dispatch_all_pending

# Trigger analysis for department 01
docker-compose exec analysis-worker celery -A worker.celery_app call analyze_department --args='["01"]'
```

---

## Next Steps (Phase 3)

1. **Dashboard API** (FastAPI): `/api/v1/tables/{id}/evidence`, `/api/v1/review/{id}/submit`
2. **Frontend** (React): Evidence viewer with page 1/2/3 images, anomaly highlights, reviewer notes
3. **Human review workflow**: State machine: NEW → REVIEWED → ESCALATE_TO_LEGAL
4. **Deployment**: Railway/Render for API services, Kubernetes for workers
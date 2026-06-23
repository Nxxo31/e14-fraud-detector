# E14 Acquisition Layer — Architecture & Design

**Version:** 1.0.0
**Date:** 2026-06-21
**Phase:** Data Infrastructure (Pre-OCR)
**Source of truth:** portal-reverse-engineering-report.md, MVP-IMPLEMENTATION-BLUEPRINT.md

---

## 1. Purpose

This layer is the **data infrastructure foundation** of the E14 Audit Platform. Its sole responsibility is to:

1. Enumerate all 122,000+ E14 records from the Registraduría CDN
2. Store metadata in PostgreSQL
3. Download PDFs on demand with Akamai-safe access patterns
4. Cache PDFs in object storage (MinIO)
5. Expose a REST API for downstream analysis agents

This layer does NOT perform OCR, signature detection, or fraud analysis.

---

## 2. Architecture

```
                          ┌──────────────────────────┐
                          │    Registraduría CDN      │
                          │  (Akamai + WAF)           │
                          │                           │
                          │  allTransmissionCodes.json│
                          │  /assets/temis/pdf/...    │
                          └──────────┬───────────────┘
                                     │
                                     │ curl_cffi (chrome impersonation)
                                     │
┌────────────────────────────────────┼────────────────────────────────────┐
│                            ACQUISITION SERVICE                          │
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    │
│  │  FastAPI REST    │    │  Celery Workers │    │  Scheduler      │    │
│  │  API             │    │                 │    │  (Beat)         │    │
│  │                  │    │  • download_pdf │    │                 │    │
│  │  GET /tables     │    │  • refresh_meta │    │  • every 30min  │    │
│  │  GET /tables/:id │    │  • retry_failed │    │  • retry cron   │    │
│  │  GET /pdf/:id    │    │                 │    │                 │    │
│  │  GET /search     │    └────────┬────────┘    └────────┬────────┘    │
│  │                  │             │                      │              │
│  └────────┬─────────┘             │                      │              │
│           │                       │                      │              │
│           ▼                       ▼                      ▼              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         Redis (Broker + Cache)                   │   │
│  │  • Celery broker (queue:download, queue:refresh)                 │   │
│  │  • Job status cache                                              │   │
│  │  • Rate limiter token bucket                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      PostgreSQL (Metadata)                       │   │
│  │  • tables (122K rows)                                            │   │
│  │  • pdfs (download tracking)                                      │   │
│  │  • jobs (Celery task tracking)                                   │   │
│  │  • audit_logs                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     MinIO (Object Storage)                       │   │
│  │  • /pdfs/{dep}/{muni}/{zona}/{puesto}/{mesa}.pdf                 │   │
│  │  • TTL: 7 days after last access                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Folder Structure

```
acquisition/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Environment configuration
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── tables.py        # /tables endpoints
│   │   ├── pdfs.py          # /pdfs endpoints
│   │   └── jobs.py          # /jobs endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── metadata.py      # Universe JSON parser
│   │   ├── downloader.py    # PDF download with curl_cffi
│   │   ├── storage.py       # MinIO object store client
│   │   └── rate_limiter.py  # Token bucket rate limiter
│   └── monitoring/
│       ├── __init__.py
│       └── metrics.py       # Prometheus metrics
├── worker/
│   ├── __init__.py
│   ├── celery_app.py        # Celery configuration
│   └── tasks.py             # Celery task definitions
├── migrations/              # Alembic migrations
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_downloader.py
│   └── test_metadata.py
├── Dockerfile
├── requirements.txt
├── alembic.ini
└── .env.example
```

---

## 4. Database Schema

### 4.1 Tables

```sql
-- Core: one row per E14 mesa
CREATE TABLE tables (
    id              BIGSERIAL PRIMARY KEY,
    dep_code        VARCHAR(2)   NOT NULL,
    muni_code       VARCHAR(3)   NOT NULL,
    zona_code       VARCHAR(3)   NOT NULL,
    puesto_code     VARCHAR(2)   NOT NULL,
    mesa_code       VARCHAR(3)   NOT NULL,
    corp_code       VARCHAR(3)   NOT NULL DEFAULT '001',
    expected_name   VARCHAR(64)  NOT NULL,
    id_stand        VARCHAR(20),
    id_transmission BIGINT,
    transmission_status INT,  -- 3 or 11
    pdf_url         TEXT,
    
    -- Tracking
    pdf_status      VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending, downloading, cached, missing, error
    pdf_sha256      VARCHAR(64),
    pdf_size_bytes  INTEGER,
    download_count  INTEGER      NOT NULL DEFAULT 0,
    last_error      TEXT,
    
    -- Denormalized names (from departmentsTree.json)
    dep_name        VARCHAR(255),
    muni_name       VARCHAR(255),
    zona_name       VARCHAR(255),
    puesto_name     VARCHAR(255),
    
    -- Timestamps
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ,
    
    -- Constraints
    UNIQUE(dep_code, muni_code, zona_code, puesto_code, mesa_code)
);

CREATE INDEX idx_tables_status ON tables(pdf_status);
CREATE INDEX idx_tables_dep_muni ON tables(dep_code, muni_code);
CREATE INDEX idx_tables_expected_name ON tables(expected_name);
CREATE INDEX idx_tables_status_created ON tables(pdf_status, created_at);
```

### 4.2 PDF Storage Tracking

```sql
CREATE TABLE pdfs (
    id              BIGSERIAL PRIMARY KEY,
    table_id        BIGINT       NOT NULL REFERENCES tables(id),
    sha256          VARCHAR(64)  NOT NULL,
    size_bytes      INTEGER      NOT NULL,
    storage_path    TEXT         NOT NULL,  -- MinIO object key
    storage_backend VARCHAR(20)  NOT NULL DEFAULT 'minio',  -- minio, local
    content_type    VARCHAR(50)  DEFAULT 'application/pdf',
    expires_at      TIMESTAMPTZ,            -- TTL for cache eviction
    
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    
    UNIQUE(table_id, sha256)
);

CREATE INDEX idx_pdfs_expires ON pdfs(expires_at) WHERE expires_at IS NOT NULL;
```

### 4.3 Download Jobs

```sql
CREATE TABLE download_jobs (
    id              BIGSERIAL PRIMARY KEY,
    table_id        BIGINT       NOT NULL REFERENCES tables(id),
    celery_task_id  VARCHAR(64),
    
    status          VARCHAR(20)  NOT NULL DEFAULT 'queued',  -- queued, running, success, failed, retrying
    attempt         INTEGER      NOT NULL DEFAULT 0,
    max_attempts    INTEGER      NOT NULL DEFAULT 5,
    
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER,
    
    error_message   TEXT,
    worker_id       VARCHAR(64),
    
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    
    UNIQUE(table_id, attempt)
);

CREATE INDEX idx_jobs_status ON download_jobs(status);
CREATE INDEX idx_jobs_created ON download_jobs(created_at);
```

### 4.4 Job Status Tracking

```sql
CREATE TABLE job_status (
    id              BIGSERIAL PRIMARY KEY,
    job_type        VARCHAR(50)  NOT NULL,  -- refresh_universe, download_batch, retry_failed
    celery_task_id  VARCHAR(64),
    
    status          VARCHAR(20)  NOT NULL DEFAULT 'queued',
    progress_total  INTEGER,
    progress_done   INTEGER,
    
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    
    metadata        JSONB,
    
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

### 4.5 Audit Logs

```sql
CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(50)  NOT NULL,  -- table_created, pdf_downloaded, pdf_evicted
    table_id        BIGINT       REFERENCES tables(id),
    details         JSONB,
    
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_type ON audit_logs(event_type);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

---

## 5. API Specification

### 5.1 Endpoints

```
GET    /health                         Health check
GET    /api/v1/tables                  List tables (paginated, filterable)
GET    /api/v1/tables/{id}             Get single table with metadata
GET    /api/v1/tables/{id}/pdf         Download PDF (serve from cache or download)
GET    /api/v1/tables/{id}/metadata    Get metadata only (no PDF)
GET    /api/v1/tables/search           Search by location codes
GET    /api/v1/jobs                    List active/recent jobs
GET    /api/v1/jobs/{id}               Get job status
GET    /api/v1/stats                   Download/processing statistics
```

### 5.2 Request/Response Examples

**GET /api/v1/tables**
```json
// Query: ?dep_code=01&muni_code=004&page=1&per_page=50
{
  "total": 1250,
  "page": 1,
  "per_page": 50,
  "tables": [
    {
      "id": 1,
      "dep_code": "01",
      "dep_name": "BOGOTÁ D.C.",
      "muni_code": "004",
      "muni_name": "ENGATIVÁ",
      "zona_code": "098",
      "zona_name": "ZONA 98",
      "puesto_code": "01",
      "puesto_name": "COLEGIO SAN JOSÉ",
      "mesa_code": "001",
      "expected_name": "3a1259d7abc...c087c5.pdf",
      "pdf_status": "cached",
      "pdf_size_bytes": 97234,
      "created_at": "2026-06-21T12:00:00Z"
    }
  ]
}
```

**GET /api/v1/tables/{id}/pdf**
```
Response: application/pdf (binary stream)
Headers:
  Content-Type: application/pdf
  Content-Length: 97234
  X-Cache: HIT
  X-SHA256: abc123...
```

**GET /api/v1/tables/search**
```json
// Query: ?dep_code=01&zona_code=98
{
  "results": [...]
}
```

**GET /api/v1/stats**
```json
{
  "total_tables": 122020,
  "pdfs_downloaded": 45230,
  "pdfs_pending": 76790,
  "pdfs_failed": 1234,
  "total_size_bytes": 4392012340,
  "cache_hit_rate": 0.85,
  "active_jobs": 3,
  "download_rate_per_second": 7.2
}
```

---

## 6. Queue System Design

### 6.1 Celery Configuration

```python
# Queue layout
CELERY_QUEUES = {
    "refresh_universe": {
        "exchange": "e14",
        "routing_key": "refresh_universe",
        "concurrency": 1,  # Only one refresh at a time
    },
    "download_pdf": {
        "exchange": "e14",
        "routing_key": "download_pdf",
        "concurrency": 6,  # 6 parallel downloaders
    },
    "retry_failed": {
        "exchange": "e14",
        "routing_key": "retry_failed",
        "concurrency": 2,
    },
    "health_check": {
        "exchange": "e14",
        "routing_key": "health_check",
        "concurrency": 1,
    },
}

# Retry policy
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_MAX_RETRIES = 5
CELERY_TASK_DEFAULT_RETRY_DELAY = 60  # seconds
CELERY_TASK_RETRY_BACKOFF = True      # exponential backoff
CELERY_TASK_RETRY_BACKOFF_MAX = 600    # max 10 minutes
```

### 6.2 Scheduled Tasks

```
refresh_universe:  every 30 minutes (election night) / every 4 hours (off-peak)
retry_failed:      every 15 minutes
health_check:      every 5 minutes
evict_expired:     every 1 hour
```

---

## 7. Storage Strategy

| Tier | Storage | TTL | Purpose |
|------|---------|-----|---------|
| Metadata | PostgreSQL | Forever | Table metadata, download tracking |
| Hot Cache | MinIO | 7 days after last access | Recently accessed PDFs |
| Cold Storage | MinIO (separate bucket) | Indefinite | SHA256-verified authoritative copies |
| Temp | /tmp (ephemeral) | During single job | Download staging before upload |

**Cache eviction logic:**
- Every hour, delete PDFs from hot cache where `expires_at < NOW()`
- If a cached PDF is requested after eviction, re-download
- SHA256-verified PDFs in cold storage are NEVER evicted

---

## 8. Implementation Plan (Execution Order)

1. Create folder structure
2. Write models.py (SQLAlchemy)
3. Write database.py + config.py
4. Run Alembic migrations (create tables)
5. Write services/metadata.py (universe JSON parser)
6. Write services/downloader.py (curl_cffi + Akamai priming)
7. Write services/storage.py (MinIO client)
8. Write worker/celery_app.py
9. Write worker/tasks.py
10. Write routers (tables.py, pdfs.py, jobs.py)
11. Write main.py (FastAPI app)
12. Write Dockerfile + requirements.txt
13. Write docker-compose.yml override
14. Write tests

---

## 9. Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| API | FastAPI | Async, auto-docs, Pydantic validation |
| Database | PostgreSQL 15 | ACID, JSONB, 122K rows easily |
| Cache | Redis 7 | Celery broker + token bucket |
| Storage | MinIO | S3-compatible, self-hosted |
| Queue | Celery 5.4 | Mature, Redis-backed, retry built-in |
| HTTP | curl_cffi | TLS fingerprint evasion for Akamai |
| Metrics | Prometheus client | Standard, Grafana-ready |
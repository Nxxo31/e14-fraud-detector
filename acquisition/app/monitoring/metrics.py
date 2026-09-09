"""E14 Acquisition — Prometheus metrics."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from fastapi import FastAPI, Response


# ── Download metrics ─────────────────────────────────────────────────────────
download_requests = Counter(
    "e14_download_requests_total",
    "Total download requests",
    ["status"],  # success, failure, skipped
)

download_bytes = Counter(
    "e14_download_bytes_total",
    "Total bytes downloaded",
)

download_duration = Histogram(
    "e14_download_seconds",
    "PDF download latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

download_errors = Counter(
    "e14_download_errors_total",
    "Download errors by reason",
    ["reason"],  # magic_bytes, timeout, http_error, storage_error
)

# ── Queue metrics ──────────────────────────────────────────────────────────
queue_depth = Gauge(
    "e14_queue_depth",
    "Number of pending download jobs",
    ["queue"],  # refresh, download, retry
)

jobs_total = Counter(
    "e14_jobs_total",
    "Total jobs by type and status",
    ["job_type", "status"],  # refresh_universe/running, download_batch/success, etc.
)

# ── Universe metrics ────────────────────────────────────────────────────────
universe_tables = Gauge(
    "e14_universe_tables",
    "Total tables in universe",
)

universe_refresh_duration = Histogram(
    "e14_universe_refresh_seconds",
    "Time to fetch allTransmissionCodes.json",
    buckets=[5, 10, 30, 60, 120, 300],
)

# ── Storage metrics ─────────────────────────────────────────────────────────
storage_bytes = Gauge(
    "e14_storage_bytes",
    "Total bytes in object storage",
)

storage_objects = Gauge(
    "e14_storage_objects",
    "Total PDF objects in storage",
)


def setup_metrics(app: FastAPI):
    """Mount /metrics endpoint."""

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
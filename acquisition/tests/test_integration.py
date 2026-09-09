"""E14 Acquisition — Integration tests.

These tests hit the real Registraduría CDN (mocked in CI).
To run: pytest tests/ -v --integration

Requires environment:
  E14_CDN_BASE_URL=https://divulgacione14presidente.registraduria.gov.co
"""

import hashlib
import os
import pytest
from datetime import datetime, timezone

# Skip integration tests unless explicitly enabled
INTEGRATION = os.getenv("E14_INTEGRATION_TESTS", "0") == "1"


@pytest.mark.skipif(not INTEGRATION, reason="Integration tests disabled")
class TestMetadataCollector:
    """Test the universe JSON collector."""

    def test_fetch_universe(self):
        from app.services.metadata import fetch_universe_json
        nodes = fetch_universe_json()
        assert len(nodes) > 1000, f"Expected >1000 nodes, got {len(nodes)}"

    def test_node_to_row(self):
        from app.services.metadata import node_to_row

        node = {
            "idDepartmentCode": "01",
            "municipalityCode": "004",
            "idZoneCode": "98",
            "standCode": "01",
            "numberStand": "001",
            "idCorporationCode": "001",
            "expectedName": "abc123def456.pdf",
            "idTransmissionCode": 4813912,
            "idTransmissionCodeStatus": 11,
            "idStand": "019800401",
        }
        row = node_to_row(node)
        assert row["dep_code"] == "01"
        assert row["muni_code"] == "004"
        assert row["zona_code"] == "098"
        assert row["mesa_code"] == "001"
        assert row["expected_name"] == "abc123def456.pdf"

    def test_pdf_url_construction(self):
        from app.services.metadata import pdf_url_for, node_to_row

        node = {
            "idDepartmentCode": "01",
            "municipalityCode": "004",
            "idZoneCode": "98",
            "standCode": "01",
            "numberStand": "001",
            "idCorporationCode": "001",
            "expectedName": "abc123.pdf",
            "idTransmissionCode": 1,
            "idTransmissionCodeStatus": 11,
            "idStand": "1",
        }
        row = node_to_row(node)
        url = pdf_url_for(row)
        assert url.startswith("https://")
        assert "/01/004/098/01/001/PRE/abc123.pdf" in url


@pytest.mark.skipif(not INTEGRATION, reason="Integration tests disabled")
class TestPdfDownloader:
    """Test PDF download and validation."""

    def test_validate_pdf_success(self):
        from app.services.downloader import _validate_pdf

        # Create a minimal valid PDF
        valid_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        sha = _validate_pdf(valid_pdf, "abc123.pdf")
        assert len(sha) == 64  # SHA256 hex length

    def test_validate_pdf_invalid_magic(self):
        from app.services.downloader import _validate_pdf, PdfDownloadError

        with pytest.raises(PdfDownloadError, match="Invalid magic bytes"):
            _validate_pdf(b"NOT A PDF", "abc123.pdf")

    def test_validate_pdf_too_small(self):
        from app.services.downloader import _validate_pdf, PdfDownloadError

        with pytest.raises(PdfDownloadError, match="PDF too small"):
            _validate_pdf(b"%PDF-1", "abc123.pdf")


class TestRateLimiter:
    """Test the token bucket rate limiter."""

    def test_bucket_acquire_no_wait(self):
        from app.services.rate_limiter import TokenBucket
        import time

        bucket = TokenBucket(rate=10.0, burst=10)

        # First 10 should acquire immediately
        for _ in range(10):
            wait = bucket.acquire(block=False)
            assert wait == 0.0

    def test_bucket_acquire_with_wait(self):
        from app.services.rate_limiter import TokenBucket
        import time

        bucket = TokenBucket(rate=5.0, burst=5)

        # Drain the bucket
        for _ in range(5):
            bucket.acquire(block=False)

        # Next one should require waiting
        start = time.monotonic()
        bucket.acquire(block=True)
        elapsed = time.monotonic() - start

        # At 5 tokens/s, acquiring 1 token should take ~0.2s
        assert 0.1 < elapsed < 0.5, f"Expected ~0.2s wait, got {elapsed:.3f}s"


class TestApiSchemas:
    """Test API response schemas."""

    def test_table_out_schema(self):
        from app.schemas import TableOut
        from datetime import datetime

        data = {
            "id": 1,
            "dep_code": "01",
            "muni_code": "004",
            "zona_code": "098",
            "puesto_code": "01",
            "mesa_code": "001",
            "expected_name": "abc123.pdf",
            "pdf_status": "cached",
            "dep_name": "BOGOTÁ D.C.",
            "muni_name": "BOGOTÁ",
            "zona_name": "ZONA 98",
            "puesto_name": "COLEGIO SAN JOSÉ",
            "created_at": datetime.now(timezone.utc),
        }
        out = TableOut(**data)
        assert out.dep_code == "01"
        assert out.pdf_status == "cached"

    def test_table_list_schema(self):
        from app.schemas import TableList, TableOut
        from datetime import datetime

        tables = [
            TableOut(
                id=i,
                dep_code="01",
                muni_code="004",
                zona_code="098",
                puesto_code="01",
                mesa_code=f"{i:03d}",
                expected_name=f"abc{i}.pdf",
                pdf_status="cached",
                created_at=datetime.now(timezone.utc),
            )
            for i in range(3)
        ]
        lst = TableList(total=100, page=1, per_page=50, tables=tables)
        assert lst.total == 100
        assert len(lst.tables) == 3

    def test_stats_schema(self):
        from app.schemas import StatsOut

        stats = StatsOut(
            total_tables=122000,
            pdfs_downloaded=45000,
            pdfs_pending=76000,
            pdfs_failed=1000,
            total_size_bytes=4_300_000_000,
            active_jobs=3,
            download_rate_hourly=28800,
        )
        assert stats.total_tables == 122000
        assert stats.pdfs_downloaded == 45000
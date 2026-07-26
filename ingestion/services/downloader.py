"""E14 PDF Downloader — Browser impersonation for Akamai bypass.

Uses curl_cffi with Chrome impersonation to bypass Akamai CDN protections.
Downloads electoral E-14 forms (~97KB, 3 pages each) from Registraduria CDN.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

import curl_cffi
from curl_cffi.requests import Session

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a PDF download operation."""

    status: str  # "success", "failed", "retry"
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    error_message: Optional[str] = None


class E14Downloader:
    """Download E-14 PDFs from Registraduria CDN with Akamai bypass.

    Uses curl_cffi with Chrome 120+ TLS fingerprinting to bypass Akamai.
    Validates PDF magic bytes (%PDF-) before accepting download.
    """

    PDF_MAGIC_BYTES = b"%PDF-"

    def __init__(self, impersonate: str = "chrome"):
        """Initialize downloader with browser impersonation.

        Args:
            impersonate: Browser to impersonate (default: "chrome").
                        Other options: "edge", "safari", "firefox".
        """
        self.impersonate = impersonate
        self._session: Optional[Session] = None
        self._cookie_refresh_time = 0

    def _get_session(self) -> Session:
        """Get or create curl_cffi session with Chrome impersonation."""
        if self._session is None:
            self._session = Session(impersonate=self.impersonate)
        return self._session

    def _refresh_cookies(self) -> None:
        """Refresh Akamai cookies by visiting the base page."""
        session = self._get_session()
        try:
            session.get(settings.CDN_BASE_URL, timeout=10)
            self._cookie_refresh_time = 0
            logger.debug("Cookies refreshed successfully")
        except Exception as e:
            logger.warning(f"Cookie refresh failed: {e}")

    def _build_pdf_url(
        self,
        dep: int,
        muni: int,
        zona: int,
        puesto: int,
        mesa: int,
        expected_name: str,
    ) -> str:
        """Build PDF download URL with zero-padded path components.

        Args:
            dep: Department code (0-padded to 2 digits)
            muni: Municipality code (0-padded to 3 digits)
            zona: Zone code (0-padded to 3 digits)
            puesto: Voting station code (0-padded to 2 digits)
            mesa: Table code (0-padded to 3 digits)
            expected_name: Expected PDF filename from transmission codes

        Returns:
            Full URL to the PDF on CDN
        """
        return (
            f"{settings.CDN_BASE_URL}"
            f"/assets/temis/pdf/"
            f"{dep:02}/{muni:03}/{zona:03}/{puesto:02}/{mesa:03}/PRE/{expected_name}"
        )

    def _validate_pdf(self, content: bytes) -> bool:
        """Validate PDF by checking magic bytes.

        Args:
            content: Raw bytes from download response

        Returns:
            True if valid PDF, False otherwise
        """
        if not settings.PDF_VALIDATION_ENABLED:
            return True
        return content[:5] == self.PDF_MAGIC_BYTES

    def download_pdf(
        self,
        dep: int,
        muni: int,
        zona: int,
        puesto: int,
        mesa: int,
        expected_name: str,
    ) -> DownloadResult:
        """Download a single E-14 PDF from CDN.

        Args:
            dep: Department code (0-99)
            muni: Municipality code (0-999)
            zona: Zone code (0-999)
            puesto: Voting station code (0-99)
            mesa: Table code (0-999)
            expected_name: Expected PDF filename from allTransmissionCodes.json

        Returns:
            DownloadResult with status, sha256, and size if successful

        Raises:
            ValueError: If PDF validation fails
            curl_cffi.CurlError: On network errors
        """
        url = self._build_pdf_url(dep, muni, zona, puesto, mesa, expected_name)
        session = self._get_session()

        try:
            response = session.get(url, timeout=settings.DOWNLOAD_TIMEOUT)

            # Validate magic bytes (not HTTP status)
            if not self._validate_pdf(response.content):
                raise ValueError(
                    f"Invalid PDF magic bytes for {expected_name}. "
                    f"First 5 bytes: {response.content[:5]!r}"
                )

            sha256_hash = hashlib.sha256(response.content).hexdigest()
            size = len(response.content)

            logger.debug(
                f"Downloaded {expected_name}: sha256={sha256_hash[:16]}..., "
                f"size={size} bytes"
            )

            return DownloadResult(
                status="success",
                sha256=sha256_hash,
                size_bytes=size,
            )

        except curl_cffi.CurlError as e:
            logger.error(f"Curl error downloading {expected_name}: {e}")
            return DownloadResult(
                status="failed",
                error_message=str(e),
            )

        except ValueError as e:
            logger.error(f"Validation error for {expected_name}: {e}")
            return DownloadResult(
                status="failed",
                error_message=str(e),
            )

    def download_transmission_codes(self) -> Optional[dict]:
        """Download allTransmissionCodes.json to enumerate universe.

        Returns:
            Parsed JSON with all transmission codes, or None on failure
        """
        session = self._get_session()
        try:
            response = session.get(
                settings.TRANSMISSION_CODES_URL,
                timeout=settings.DOWNLOAD_TIMEOUT,
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to download transmission codes: {e}")
            return None

    def close(self) -> None:
        """Close the curl_cffi session."""
        if self._session:
            self._session.close()
            self._session = None


# Convenience function for quick downloads
def download_single_pdf(
    dep: int,
    muni: int,
    zona: int,
    puesto: int,
    mesa: int,
    expected_name: str,
) -> DownloadResult:
    """Download a single E-14 PDF using default settings.

    This is a convenience function for one-off downloads.
    For batch processing, use E14Downloader class directly.
    """
    downloader = E14Downloader()
    try:
        return downloader.download_pdf(dep, muni, zona, puesto, mesa, expected_name)
    finally:
        downloader.close()
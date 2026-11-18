"""Download source archives with retries, validation and a local cache."""

from __future__ import annotations

import hashlib
import logging
import os
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from claims_ingest.errors import DownloadError
from claims_ingest.retry import retry_call

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
REQUEST_TIMEOUT = (15, 120)
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
HEADERS = {"User-Agent": "claims-analytics-warehouse-ingest/0.1", "Accept-Encoding": "identity"}


class TransientDownloadError(Exception):
    """A failure that is likely to succeed on another attempt."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size_bytes: int
    from_cache: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _is_transient(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            TransientDownloadError,
            requests.ConnectionError,
            requests.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def _fetch(session: requests.Session, url: str, dest: Path) -> None:
    partial = dest.with_name(f"{dest.name}.part")
    try:
        with session.get(url, stream=True, timeout=REQUEST_TIMEOUT, headers=HEADERS) as response:
            if response.status_code in RETRYABLE_STATUS:
                raise TransientDownloadError(f"HTTP {response.status_code}")
            if response.status_code != 200:
                raise DownloadError(
                    f"Download of {url} failed with HTTP {response.status_code}. "
                    "Check that the file still exists on the CMS site."
                )

            expected = response.headers.get("Content-Length")
            written = 0
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    handle.write(chunk)
                    written += len(chunk)

        if expected is not None and written != int(expected):
            raise TransientDownloadError(f"received {written} of {expected} bytes")
        if not zipfile.is_zipfile(partial):
            raise TransientDownloadError("response is not a valid zip archive")
        os.replace(partial, dest)
    finally:
        partial.unlink(missing_ok=True)


def download_file(
    url: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
    attempts: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    """Download `url` to `dest`, reusing a valid archive that is already there."""
    if dest.exists() and zipfile.is_zipfile(dest):
        logger.info("download_cached file=%s", dest.name)
        return DownloadResult(dest, sha256_file(dest), dest.stat().st_size, True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    try:
        retry_call(
            lambda: _fetch(http, url, dest),
            should_retry=_is_transient,
            description=f"download {dest.name}",
            attempts=attempts,
            sleep=sleep,
        )
    except (TransientDownloadError, requests.RequestException) as exc:
        raise DownloadError(f"Could not download {url} after {attempts} attempts: {exc}") from exc

    size = dest.stat().st_size
    logger.info("download_complete file=%s bytes=%d", dest.name, size)
    return DownloadResult(dest, sha256_file(dest), size, False)

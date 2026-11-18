import hashlib

import pytest
import requests
import responses
from conftest import zip_bytes

from claims_ingest.download import download_file
from claims_ingest.errors import DownloadError

URL = "https://example.test/source.zip"


def no_wait(_: float) -> None:
    return None


@responses.activate
def test_download_saves_the_archive_and_its_checksum(tmp_path):
    body = zip_bytes()
    responses.get(URL, body=body)

    result = download_file(URL, tmp_path / "nested" / "source.zip", sleep=no_wait)

    assert result.path.read_bytes() == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.size_bytes == len(body)
    assert result.from_cache is False


@responses.activate
def test_valid_cached_archive_is_not_downloaded_again(tmp_path):
    dest = tmp_path / "source.zip"
    dest.write_bytes(zip_bytes())

    result = download_file(URL, dest, sleep=no_wait)

    assert result.from_cache is True
    assert len(responses.calls) == 0


@responses.activate
def test_corrupt_cached_archive_is_replaced(tmp_path):
    dest = tmp_path / "source.zip"
    dest.write_bytes(b"not a zip")
    body = zip_bytes()
    responses.get(URL, body=body)

    result = download_file(URL, dest, sleep=no_wait)

    assert result.from_cache is False
    assert dest.read_bytes() == body


@responses.activate
def test_server_errors_are_retried(tmp_path):
    responses.get(URL, status=503)
    responses.get(URL, status=429)
    responses.get(URL, body=zip_bytes())

    result = download_file(URL, tmp_path / "source.zip", sleep=no_wait)

    assert result.path.exists()
    assert len(responses.calls) == 3


@responses.activate
def test_connection_errors_are_retried(tmp_path):
    responses.get(URL, body=requests.ConnectionError("connection reset"))
    responses.get(URL, body=zip_bytes())

    result = download_file(URL, tmp_path / "source.zip", sleep=no_wait)

    assert result.path.exists()
    assert len(responses.calls) == 2


@responses.activate
def test_missing_file_fails_immediately_with_the_url(tmp_path):
    responses.get(URL, status=404)

    with pytest.raises(DownloadError, match=r"source\.zip failed with HTTP 404"):
        download_file(URL, tmp_path / "source.zip", sleep=no_wait)

    assert len(responses.calls) == 1


@responses.activate
def test_html_response_fails_after_retries_and_leaves_no_files(tmp_path):
    responses.get(URL, body=b"<html>maintenance page</html>")

    with pytest.raises(DownloadError, match="not a valid zip archive"):
        download_file(URL, tmp_path / "source.zip", attempts=3, sleep=no_wait)

    assert len(responses.calls) == 3
    assert list(tmp_path.iterdir()) == []

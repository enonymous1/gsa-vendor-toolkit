"""Tests for the downloader hardening (staff-review patch 01).

The downloader previously had no direct tests: the e2e test simulates
downloads by placing workbooks by hand. These tests mock ``requests.get``
and cover the behaviors patch 01 changes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from vendors_toolkit.config import DownloadConfig
from vendors_toolkit.pipeline.download import _download_one, download_filename


def _row(vendor="Acme", contact="101", url="http://example.com/list.xlsx"):
    return pd.Series({"Price List": url, "Vendor": vendor, "Contact #": contact})


def _response(status=200, chunks=(b"abc", b"def"), body_error=None):
    resp = MagicMock()
    resp.status_code = status
    if body_error is not None:
        resp.iter_content.side_effect = body_error
    else:
        resp.iter_content.return_value = list(chunks)
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _cfg(**overrides):
    kwargs = {"retry_sleep_seconds": 0}
    kwargs.update(overrides)
    return DownloadConfig(**kwargs)


def test_download_success_writes_file_and_no_part(tmp_path):
    cfg = _cfg()
    with patch(
        "vendors_toolkit.pipeline.download.requests.get",
        return_value=_response(),
    ) as mock_get:
        outcome = _download_one(_row(), tmp_path, cfg)
    assert outcome.status == "Success"
    assert (tmp_path / "Acme_101.xlsx").read_bytes() == b"abcdef"
    assert not list(tmp_path.glob("*.part"))
    assert mock_get.call_count == 1


def test_download_existing_file_skips_network(tmp_path):
    (tmp_path / "Acme_101.xlsx").write_bytes(b"already here")
    cfg = _cfg()
    with patch(
        "vendors_toolkit.pipeline.download.requests.get",
    ) as mock_get:
        outcome = _download_one(_row(), tmp_path, cfg)
    assert outcome.status == "Success"
    assert mock_get.call_count == 0


def test_download_404_fails_fast_without_retry(tmp_path):
    cfg = _cfg()
    with patch(
        "vendors_toolkit.pipeline.download.requests.get",
        return_value=_response(status=404),
    ) as mock_get:
        outcome = _download_one(_row(), tmp_path, cfg)
    assert outcome.status == "Failed"
    assert outcome.error == "HTTP 404"
    assert mock_get.call_count == 1
    assert not (tmp_path / "Acme_101.xlsx").exists()


def test_download_500_retries_then_fails(tmp_path):
    cfg = _cfg(max_retries=3)
    with patch(
        "vendors_toolkit.pipeline.download.requests.get",
        return_value=_response(status=500),
    ) as mock_get:
        outcome = _download_one(_row(), tmp_path, cfg)
    assert outcome.status == "Failed"
    assert outcome.error == "HTTP 500"
    assert mock_get.call_count == 3
    assert not (tmp_path / "Acme_101.xlsx").exists()


def test_download_mid_body_failure_leaves_no_file_or_part(tmp_path):
    cfg = _cfg(max_retries=1)

    def _broken(*args, **kwargs):
        return _response(body_error=RuntimeError("connection dropped"))

    with patch("vendors_toolkit.pipeline.download.requests.get", side_effect=_broken):
        outcome = _download_one(_row(), tmp_path, cfg)
    assert outcome.status == "Failed"
    assert not (tmp_path / "Acme_101.xlsx").exists()
    assert not list(tmp_path.glob("*.part"))


def test_download_filename_sanitizes_contact(tmp_path):
    assert download_filename("Acme", "../../evil", ".xlsx", None) == "Acme_______evil.xlsx"
    cfg = _cfg()
    with patch(
        "vendors_toolkit.pipeline.download.requests.get",
        return_value=_response(),
    ):
        outcome = _download_one(_row(contact="../../evil"), tmp_path, cfg)
    assert outcome.status == "Success"
    assert (tmp_path / "Acme_______evil.xlsx").exists()
    # Nothing escaped the download directory.
    assert not (tmp_path.parent / "evil.xlsx").exists()
    assert not (tmp_path / "evil.xlsx").exists()


def test_download_filename_truncation_unchanged():
    assert download_filename("A" * 60, "101", ".xlsx", 50) == "A" * 50 + "_101.xlsx"

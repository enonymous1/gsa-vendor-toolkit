"""Tests for the SAM.gov retry policy (staff-review patch 03)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from vendors_toolkit.config import SamGovConfig
from vendors_toolkit.integrations.samgov import SamGovClient


def _client():
    return SamGovClient(SamGovConfig(), api_key="KEY-123")


def _error_response(status, retry_after=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}", response=resp)
    return resp


def test_sam_401_fails_immediately_without_retry(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = _client()
    with (
        patch(
            "vendors_toolkit.integrations.samgov.requests.get",
            return_value=_error_response(401),
        ) as mock_get,
        pytest.raises(RuntimeError, match="SAM.gov request failed"),
    ):
        client.get_entity_by_uei("RV56IG5JM6G9")
    assert mock_get.call_count == 1


def test_sam_500_retries_then_fails(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    monkeypatch.setattr("vendors_toolkit.integrations.samgov.time.sleep", lambda seconds: None)
    client = _client()
    with (
        patch(
            "vendors_toolkit.integrations.samgov.requests.get",
            return_value=_error_response(500),
        ) as mock_get,
        pytest.raises(RuntimeError, match="after retries"),
    ):
        client.get_entity_by_uei("RV56IG5JM6G9")
    # max_retries=2 -> 3 attempts.
    assert mock_get.call_count == 3


def test_sam_429_honors_retry_after_and_then_succeeds(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    sleeps = []
    monkeypatch.setattr("vendors_toolkit.integrations.samgov.time.sleep", sleeps.append)
    client = _client()
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    ok.json.return_value = {"totalRecords": 1}
    with patch(
        "vendors_toolkit.integrations.samgov.requests.get",
        side_effect=[_error_response(429, retry_after="7"), ok],
    ) as mock_get:
        result = client.get_entity_by_uei("RV56IG5JM6G9")
    assert result == {"totalRecords": 1}
    assert mock_get.call_count == 2
    assert sleeps == [7]


def test_sam_connection_error_retries_then_fails(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    monkeypatch.setattr("vendors_toolkit.integrations.samgov.time.sleep", lambda seconds: None)
    client = _client()
    with (
        patch(
            "vendors_toolkit.integrations.samgov.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ) as mock_get,
        pytest.raises(RuntimeError, match="after retries"),
    ):
        client.get_entity_by_uei("RV56IG5JM6G9")
    assert mock_get.call_count == 3


def test_sam_invalid_json_is_wrapped_not_retried(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = _client()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")
    with (
        patch("vendors_toolkit.integrations.samgov.requests.get", return_value=resp) as mock_get,
        pytest.raises(RuntimeError, match="invalid JSON"),
    ):
        client.get_entity_by_uei("RV56IG5JM6G9")
    assert mock_get.call_count == 1

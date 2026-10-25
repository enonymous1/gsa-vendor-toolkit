"""Tests for the SAM.gov scaffold: config, client, and CLI surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vendors_toolkit import cli
from vendors_toolkit.config import SamGovConfig
from vendors_toolkit.integrations.samgov import SamGovClient, SamGovNotConfiguredError


def test_sam_config_defaults():
    cfg = SamGovConfig()
    assert cfg.base_url == "https://api.sam.gov"
    assert cfg.api_key_env_var == "SAM_API_KEY"


def test_client_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = SamGovClient(SamGovConfig())
    assert client.is_configured is False
    with pytest.raises(SamGovNotConfiguredError, match="SAM_API_KEY"):
        client.get_entity_by_uei("RV56IG5JM6G9")


def test_client_uses_explicit_key_and_builds_url(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = SamGovClient(SamGovConfig(), api_key="KEY-123")
    assert client.is_configured is True

    fake_response = MagicMock()
    fake_response.json.return_value = {"totalRecords": 1}
    with patch(
        "vendors_toolkit.integrations.samgov.requests.get",
        return_value=fake_response,
    ) as mock_get:
        result = client.get_entity_by_uei("RV56IG5JM6G9")
    assert result == {"totalRecords": 1}
    url, kwargs = mock_get.call_args.args[0], mock_get.call_args.kwargs
    assert url == "https://api.sam.gov/entity-information/v3/entities"
    assert kwargs["params"]["ueiSAM"] == "RV56IG5JM6G9"
    assert kwargs["params"]["api_key"] == "KEY-123"


def test_client_exclusion_check_requires_identifier():
    client = SamGovClient(SamGovConfig(), api_key="KEY-123")
    with pytest.raises(ValueError, match="uei or a cage"):
        client.check_exclusions()


def test_client_exclusion_path(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = SamGovClient(SamGovConfig(), api_key="KEY-123")
    fake_response = MagicMock()
    fake_response.json.return_value = {"totalRecords": 0}
    with patch(
        "vendors_toolkit.integrations.samgov.requests.get",
        return_value=fake_response,
    ) as mock_get:
        client.check_exclusions(cage="12345")
    assert mock_get.call_args.args[0] == "https://api.sam.gov/entity-information/v3/exclusions"


def test_client_opportunity_search_path(monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    client = SamGovClient(SamGovConfig(), api_key="KEY-123")
    fake_response = MagicMock()
    fake_response.json.return_value = {"opportunitiesData": []}
    with patch(
        "vendors_toolkit.integrations.samgov.requests.get",
        return_value=fake_response,
    ) as mock_get:
        client.search_opportunities(keywords="IT services", naics="54151S")
    assert mock_get.call_args.args[0] == "https://api.sam.gov/prod/opportunities/v2/search"
    assert mock_get.call_args.kwargs["params"]["title"] == "IT services"
    assert mock_get.call_args.kwargs["params"]["ncode"] == "54151S"


def test_cli_sam_status_without_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    rc = cli.main(["--root", str(tmp_path), "sam", "--status"])
    assert rc == 0
    assert "NOT configured" in capsys.readouterr().out


def test_cli_sam_lookup_without_key_returns_1(monkeypatch, tmp_path):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    rc = cli.main(["--root", str(tmp_path), "sam", "--uei", "RV56IG5JM6G9"])
    assert rc == 1


def test_cli_sam_runs_once_even_with_all_variants(monkeypatch, tmp_path):
    """The sam stage must not burn the daily budget by running per variant."""
    monkeypatch.setenv("SAM_API_KEY", "KEY-123")
    calls = []

    def fake_get_entity(self, uei):
        calls.append(uei)
        return {"ok": True}

    monkeypatch.setattr(SamGovClient, "get_entity_by_uei", fake_get_entity)
    rc = cli.main(["--root", str(tmp_path), "sam", "--uei", "RV56IG5JM6G9"])
    assert rc == 0
    assert calls == ["RV56IG5JM6G9"]

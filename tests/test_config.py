"""Tests for centralized configuration."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from vendors_toolkit.config import default_config, resolve_project_root


def test_variant_drift_preserved(cfg, it, mgmt):
    """The 54151S-vs-541611 behavioral drift is captured, not lost."""
    assert it.download.max_retries == 3
    assert mgmt.download.max_retries == 2
    assert it.download.timeout_seconds == 20
    assert mgmt.download.timeout_seconds == 15
    assert it.organize_mode == "move"
    assert mgmt.organize_mode == "copy"
    assert it.report_page_length == 50
    assert mgmt.report_page_length == 25
    assert mgmt.default_download_limit == 3000
    assert it.default_download_limit is None
    assert ".doc" not in it.organize_extensions
    assert ".doc" in mgmt.organize_extensions


def test_metrics_templates_differ_per_variant(it, mgmt):
    assert it.metrics_filename_template != mgmt.metrics_filename_template
    assert it.report_html_template != mgmt.report_html_template
    assert "541611" in mgmt.report_html_template
    assert mgmt.metrics_national_from_shards is True
    assert it.metrics_national_from_shards is False


def test_config_is_frozen(cfg):
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.paths.root = Path("/elsewhere")  # type: ignore[misc]


def test_resolve_project_root_explicit(tmp_path):
    assert resolve_project_root(tmp_path) == tmp_path.resolve()


def test_resolve_project_root_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("VENDORS_ROOT", str(tmp_path))
    assert resolve_project_root() == tmp_path.resolve()


def test_resolve_project_root_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("VENDORS_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_project_root() == tmp_path.resolve()


def test_default_config_uses_env_root(tmp_path, monkeypatch):
    monkeypatch.setenv("VENDORS_ROOT", str(tmp_path))
    cfg = default_config()
    assert cfg.paths.root == tmp_path.resolve()
    assert os.environ["VENDORS_ROOT"] == str(tmp_path)

"""Shared pytest fixtures for the vendors_toolkit test suite."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from vendors_toolkit.config import Config, VariantConfig, default_config


@pytest.fixture()
def cfg(tmp_path: Path) -> Config:
    """Default config rooted at an isolated temporary directory."""
    return default_config(root=tmp_path)


@pytest.fixture()
def it(cfg: Config) -> VariantConfig:
    return cfg.variants["54151S"]


@pytest.fixture()
def mgmt(cfg: Config) -> VariantConfig:
    return cfg.variants["541611"]


@pytest.fixture()
def raw_vendor_csv(cfg: Config, it: VariantConfig) -> Path:
    """A minimal raw vendor CSV at the variant's expected raw_csv location."""
    cfg.paths.raw.mkdir(parents=True, exist_ok=True)
    path = cfg.paths.raw / it.raw_csv
    pd.DataFrame(
        [
            {"Vendor": "Acme", "Category": "A", "State": "VA", "City": "Arlington"},
            {"Vendor": "Beta", "Category": "B", "State": "DC", "City": "Washington"},
        ]
    ).to_csv(path, index=False)
    return path

"""Tests for the sanitize / merge / filter / national pipeline stages."""

from __future__ import annotations

import pandas as pd
import pytest

from vendors_toolkit.pipeline.filter import filter_sin
from vendors_toolkit.pipeline.merge import merge_state_price_lists
from vendors_toolkit.pipeline.national import merge_national
from vendors_toolkit.pipeline.sanitize import sanitize_vendors


def test_sanitize_vendors_writes_output(cfg, it, raw_vendor_csv):
    out = sanitize_vendors(cfg, it)
    assert out.exists()
    df = pd.read_csv(out)
    assert len(df) == 2


def test_sanitize_vendors_missing_input_raises(cfg, it):
    with pytest.raises(FileNotFoundError):
        sanitize_vendors(cfg, it)


def _write_price_list(path, rows):
    """Write a minimal vendor workbook with a 'Price List' sheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, sheet_name="Price List", index=False)


def test_merge_state_price_lists(cfg, it):
    by_region = cfg.paths.downloads(it.dirs.by_region)
    _write_price_list(
        by_region / "VA" / "Arlington" / "acme.xlsx",
        [{"Title": "Analyst", "GSA Price": 100.0}],
    )
    _write_price_list(
        by_region / "VA" / "Richmond" / "beta.xls",
        [{"Title": "Manager", "GSA Price": 200.0}],
    )
    paths = merge_state_price_lists(cfg, it, states=["VA"])
    assert len(paths) == 1
    df = pd.read_csv(paths[0])
    assert set(df["Title"]) == {"Analyst", "Manager"}


def test_merge_state_price_lists_skips_missing_sheet(cfg, it):
    by_region = cfg.paths.downloads(it.dirs.by_region)
    bad = by_region / "VA" / "Nowhere" / "bad.xlsx"
    bad.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"A": [1]}]).to_excel(bad, sheet_name="Other", index=False)
    paths = merge_state_price_lists(cfg, it, states=["VA"])
    # a workbook without a price-list sheet contributes nothing: no output written
    assert paths == []


def test_filter_sin(cfg, it):
    analysis = cfg.paths.variant_dir(it.dirs.analysis)
    analysis.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"Title": "A", "SIN": "54151S", "GSA Price": 10.0},
            {"Title": "B", "SIN": "99999", "GSA Price": 20.0},
        ]
    ).to_csv(analysis / it.merged_filename_template.format(state="VA"), index=False)
    paths = filter_sin(cfg, it, states=["VA"])
    assert len(paths) == 1
    df = pd.read_csv(paths[0])
    assert list(df["Title"]) == ["A"]


def test_merge_national_it(cfg, it):
    cfg.paths.summaries.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Vendor": "Acme", "Contact #": "123", "Download_Status": "Success"}]).to_csv(
        cfg.paths.summaries / it.manifest_filename, index=False
    )
    cfg.paths.raw.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "Vendor": "Acme",
                "Contact #": "123",
                "Category": "54151S",
                "State": "VA",
                "City": "Arlington",
            }
        ]
    ).to_csv(cfg.paths.raw / it.sanitized_csv, index=False)
    wb = cfg.paths.downloads(it.dirs.by_region) / "VA" / "Arlington" / "Acme_123.xlsx"
    wb.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Title": "Analyst", "GSA Price": 100.0}]).to_excel(
        wb, sheet_name="Price List", index=False
    )
    path = merge_national(cfg, it)
    assert path is not None and path.exists()
    df = pd.read_csv(path)
    assert df.iloc[0]["Title"] == "Analyst"
    assert df.iloc[0]["Source_Vendor"] == "Acme"


def test_merge_national_unconfigured_variant_raises(cfg, mgmt):
    with pytest.raises(ValueError, match="not configured"):
        merge_national(cfg, mgmt)

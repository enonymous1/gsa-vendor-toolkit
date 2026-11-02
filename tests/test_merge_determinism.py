"""Tests for merge determinism (staff-review patch 02)."""

from __future__ import annotations

import pandas as pd

from vendors_toolkit.pipeline.merge import merge_state_price_lists


def _write_price_list(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, sheet_name="Price List", index=False)


def test_merge_row_order_is_sorted_not_creation_order(cfg, it, caplog):
    """Cities and files are merged in sorted order, regardless of the
    order they were created on disk (creation order is filesystem order
    for os.listdir/glob, which used to leak into the master CSV)."""
    import logging

    by_region = cfg.paths.downloads(it.dirs.by_region)
    # Created in reverse alphabetical order on purpose.
    _write_price_list(
        by_region / "VA" / "Richmond" / "beta.xlsx",
        [{"Title": "RichmondTitle", "GSA Price": 200.0}],
    )
    _write_price_list(
        by_region / "VA" / "Arlington" / "zeta.xlsx",
        [{"Title": "ArlingtonZeta", "GSA Price": 100.0}],
    )
    _write_price_list(
        by_region / "VA" / "Arlington" / "alpha.xlsx",
        [{"Title": "ArlingtonAlpha", "GSA Price": 110.0}],
    )
    with caplog.at_level(logging.WARNING):
        paths = merge_state_price_lists(cfg, it, states=["VA"])
    assert len(paths) == 1
    df = pd.read_csv(paths[0])
    assert list(df["Title"]) == ["ArlingtonAlpha", "ArlingtonZeta", "RichmondTitle"]
    assert list(df["Source_City"]) == ["Arlington", "Arlington", "Richmond"]


def test_merge_skipped_workbook_is_logged_at_warning(cfg, it, caplog):
    """A workbook without a price-list sheet is skipped with a warning,
    not silently at debug level."""
    import logging

    by_region = cfg.paths.downloads(it.dirs.by_region)
    bad = by_region / "VA" / "Nowhere" / "bad.xlsx"
    bad.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"A": [1]}]).to_excel(bad, sheet_name="Other", index=False)
    with caplog.at_level(logging.WARNING):
        paths = merge_state_price_lists(cfg, it, states=["VA"])
    assert paths == []
    assert any("bad.xlsx" in record.message for record in caplog.records)

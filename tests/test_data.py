"""Tests for the shared data helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from vendors_toolkit.data.cleaning import (
    clean_title,
    detect_price_column,
    is_missing,
    normalize_title_key,
    to_price_numeric,
)
from vendors_toolkit.data.mapping import GSA_MAP, sanitize_frame


def test_gsa_map_is_nonempty():
    assert isinstance(GSA_MAP, dict) and len(GSA_MAP) > 0


def test_sanitize_frame_does_not_mutate():
    df = pd.DataFrame({"Category": ["A"], "Vendor": ["Acme"]})
    before = df.copy(deep=True)
    sanitize_frame(df, renamed_columns={}, skip_columns={"Vendor"})
    pd.testing.assert_frame_equal(df, before)


def test_sanitize_frame_maps_coded_values():
    key = next(iter(GSA_MAP))
    df = pd.DataFrame({"Category": [key, "ZZZ-UNKNOWN"]})
    out = sanitize_frame(df, renamed_columns={}, skip_columns=set())
    assert out["Category"].iloc[0] == GSA_MAP[key]
    assert out["Category"].iloc[1] == "ZZZ-UNKNOWN"  # unmapped passes through


def test_sanitize_frame_renames_columns():
    df = pd.DataFrame({"Unnamed: 39": [1]})
    out = sanitize_frame(df, renamed_columns={"Unnamed: 39": "Flag"}, skip_columns=set())
    assert "Flag" in out.columns


def test_clean_title_fills_missing_first():
    s = pd.Series([None, "  Analyst ", np.nan])
    assert list(clean_title(s)) == ["", "Analyst", ""]


def test_normalize_title_key_uppercases():
    assert list(normalize_title_key(pd.Series(["Analyst", None]))) == ["ANALYST", ""]


def test_is_missing():
    # Mirrors pd.notnull semantics: empty strings are NOT missing.
    assert is_missing(None) and is_missing(np.nan)
    assert is_missing(pd.NA) and is_missing(pd.NaT)
    assert not is_missing("") and not is_missing("   ")
    assert not is_missing("Acme") and not is_missing(0)


def test_to_price_numeric_strips_currency():
    s = pd.Series(["$100.00", "$1,000.50", "200", None, "abc"])
    out = to_price_numeric(s)
    assert out.iloc[0] == 100.0
    assert out.iloc[1] == 1000.5
    assert out.iloc[2] == 200.0
    assert np.isnan(out.iloc[3]) and np.isnan(out.iloc[4])


def test_detect_price_column_prefers_exact():
    df = pd.DataFrame({"GSA Price": [1.0], "Price (alt)": [2.0]})
    assert detect_price_column(df.columns, "GSA Price", ("Price", "Alt")) == "GSA Price"


def test_detect_price_column_falls_back_to_markers():
    df = pd.DataFrame({"GSA Price with IFF (alt)": [2.0]})
    assert (
        detect_price_column(df.columns, "GSA Price", ("GSA Price", "with IFF"))
        == "GSA Price with IFF (alt)"
    )


def test_detect_price_column_none_when_absent():
    df = pd.DataFrame({"Title": ["x"]})
    assert detect_price_column(df.columns, "GSA Price", ("GSA", "Price")) is None

"""Tests for metrics, audit, and exports."""

from __future__ import annotations

import json

import pandas as pd

from vendors_toolkit.analysis.audit import analyze_cardinality, run_audit
from vendors_toolkit.analysis.exports import extract_unique_titles, generate_exports
from vendors_toolkit.analysis.metrics import compute_title_metrics

PRICE_COL = "GSA Price with IFF  - as of price list generation date"


def _write_filtered(cfg, it, state, rows):
    d = cfg.paths.variant_dir(it.dirs.filtered)
    d.mkdir(parents=True, exist_ok=True)
    path = d / it.filtered_filename_template.format(state=state, sin=it.sin)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_compute_title_metrics_values(cfg, it):
    _write_filtered(
        cfg,
        it,
        "VA",
        [
            {"Title": "Analyst", "Description": "Does analysis", PRICE_COL: "$100.00"},
            {"Title": "analyst ", "Description": "More analysis", PRICE_COL: "200"},
            {"Title": "Manager", "Description": "Manages", PRICE_COL: "$1,000.50"},
            {"Title": "Manager", "Description": "Manages well", PRICE_COL: None},
            {"Title": "Clerk", "Description": "", PRICE_COL: "75"},
        ],
    )
    paths = compute_title_metrics(cfg, it, states=["VA"])
    df = pd.read_csv(paths[0])
    by_key = {r["Title_Key"]: r for _, r in df.iterrows()}
    assert by_key["ANALYST"]["Count"] == 2
    assert by_key["ANALYST"]["Mean_Price"] == 150.0
    assert by_key["ANALYST"]["Min_Price"] == 100.0
    assert by_key["MANAGER"]["Max_Price"] == 1000.5
    assert by_key["CLERK"]["Mean_Price"] == 75.0
    assert paths[0].with_suffix(".xlsx").exists()


def test_compute_title_metrics_fallback_price_column(cfg, it):
    _write_filtered(
        cfg,
        it,
        "DC",
        [{"Title": "Director", "Description": "D", "GSA Price with IFF (alt)": "$400"}],
    )
    paths = compute_title_metrics(cfg, it, states=["DC"])
    df = pd.read_csv(paths[0])
    assert df.iloc[0]["Mean_Price"] == 400.0


def test_compute_title_metrics_missing_title_normalizes(cfg, it):
    _write_filtered(
        cfg,
        it,
        "VA",
        [
            {"Title": None, "Description": "d", PRICE_COL: "10"},
            {"Title": "X", "Description": "e", PRICE_COL: "20"},
        ],
    )
    paths = compute_title_metrics(cfg, it, states=["VA"])
    keys = set(pd.read_csv(paths[0], keep_default_na=False)["Title_Key"])
    assert "" in keys and "NONE" not in keys


def test_compute_title_metrics_national_from_shards(cfg, mgmt):
    analysis = cfg.paths.variant_dir(mgmt.dirs.analysis)
    analysis.mkdir(parents=True, exist_ok=True)
    for state, price in [("VA", 500.0), ("MD", 300.0)]:
        pd.DataFrame(
            [{"Title": "Consultant", "Description": "Advises", "GSA Price": price}]
        ).to_csv(analysis / mgmt.merged_filename_template.format(state=state), index=False)
    paths = compute_title_metrics(cfg, mgmt, states=["National"])
    df = pd.read_csv(paths[0])
    assert df.iloc[0]["Count"] == 2
    assert df.iloc[0]["Mean_Price"] == 400.0


def test_analyze_cardinality(cfg, it):
    analysis = cfg.paths.variant_dir(it.dirs.analysis)
    analysis.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"Title": "Analyst", "SIN": "54151S"},
            {"Title": "Analyst", "SIN": "54151S"},
            {"Title": "Manager", "SIN": "54151S"},
        ]
    ).to_csv(analysis / it.merged_filename_template.format(state="VA"), index=False)
    (reports,) = analyze_cardinality(cfg, it, states=["VA"])
    assert reports.total_rows == 3
    assert reports.unique_titles == 2
    assert reports.top_titles[0][0] == "ANALYST"  # titles are normalized uppercase


def test_run_audit(cfg, tmp_path):
    src = tmp_path / "in.csv"
    pd.DataFrame(
        [
            {"Vendor": "A", "State": "VA", "City": "X", "Price List": "y"},
            {"Vendor": "B", "State": "DC", "City": "Y", "Price List": None},
        ]
    ).to_csv(src, index=False)
    summary = run_audit(cfg, src)
    text = summary.read_text()
    assert "DATA AUDIT SUMMARY" in text
    assert "**Total Row Count:** 2" in text
    assert list(cfg.paths.column_selections.glob("*.json"))


def test_generate_exports(cfg, it, raw_vendor_csv):
    sanitize_out = cfg.paths.raw / it.sanitized_csv
    df = pd.read_csv(raw_vendor_csv)
    df["Has_Price_List_Flag"] = "Yes"
    df.to_csv(sanitize_out, index=False)
    base = generate_exports(cfg, it)
    assert (base / "price_lists" / "all_vendors_with_price_list.csv").exists()
    assert (base / "regional" / "VA" / "all_vendors_VA.csv").exists()
    assert list((base / "summaries").glob("*.md"))


def test_extract_unique_titles(cfg, it):
    _write_filtered(
        cfg,
        it,
        "VA",
        [
            {"Title": "Analyst", PRICE_COL: 10.0},
            {"Title": "analyst", PRICE_COL: 20.0},
            {"Title": None, PRICE_COL: 30.0},
        ],
    )
    out_dir = extract_unique_titles(cfg, it, states=["VA"])
    titles = json.loads((out_dir / "VA_Unique_IT_Titles.json").read_text())
    assert titles == ["", "Analyst", "analyst"]

"""Tests for reporting: description HTML, table data, and report generation."""

from __future__ import annotations

import json

import pandas as pd

from vendors_toolkit.reporting.dashboard import (
    build_table_data,
    description_html,
    generate_reports,
)


def test_description_html_escapes_markup():
    count, html = description_html('<script>alert("x")</script> & "q" | plain', 5)
    assert count == 2
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_description_html_empty():
    count, html = description_html("", 5)
    assert count == 0
    assert "No description available" in html


def test_description_html_truncates_to_sample_limit():
    count, html = description_html("a | b | c | d | e | f | g", 5)
    assert count == 7
    assert "2 more variations" in html
    assert "<li>f</li>" not in html


def test_build_table_data_row_shape():
    df = pd.DataFrame(
        [
            {
                "Title_Key": "ANALYST",
                "Count": 2,
                "Min_Price": 100.0,
                "Max_Price": 200.0,
                "Mean_Price": 150.0,
                "Median_Price": 150.0,
                "Mode_Price": 100.0,
                "Merged_Descriptions": "Does analysis",
                "Price_Range": 100.0,
            },
            {
                "Title_Key": "CLERK",
                "Count": 1,
                "Min_Price": 75.0,
                "Max_Price": 75.0,
                "Mean_Price": 75.0,
                "Median_Price": 75.0,
                "Mode_Price": 75.0,
                "Merged_Descriptions": "",
                "Price_Range": 0.0,
            },
        ]
    )
    rows = build_table_data(df, 5)
    assert [r["t"] for r in rows] == ["ANALYST", "CLERK"]  # sorted by Title_Key
    analyst, clerk = rows
    assert analyst["m"] == "$150.00"
    assert analyst["r"] == "$100.00" and analyst["r_r"] == 100.0
    assert clerk["r"] == "-" and clerk["r_r"] == -1.0  # single sample: no range
    assert clerk["d_c"] == 0


def _write_metrics(cfg, variant, state):
    d = cfg.paths.variant_dir(variant.dirs.metrics)
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "Title_Key": "ANALYST",
                "Count": 2,
                "Min_Price": 100.0,
                "Max_Price": 200.0,
                "Mean_Price": 150.0,
                "Median_Price": 150.0,
                "Mode_Price": 100.0,
                "Merged_Descriptions": "Does analysis | More analysis",
                "Price_Range": 100.0,
            }
        ]
    ).to_csv(d / variant.metrics_filename_template.format(state=state), index=False)


def test_generate_reports_writes_all_artifacts(cfg, it):
    _write_metrics(cfg, it, "VA")
    paths = generate_reports(cfg, it, states=["VA"])
    report_dir = cfg.paths.variant_dir(it.dirs.reports)
    assert len(paths) == 1
    html_path = paths[0]
    assert html_path.name == "VA_IT_Pricing_Full_Report.html"
    assert (report_dir / "VA_IT_Pricing_Executive_Summary.md").exists()
    assert (report_dir / "VA_data.js").exists()
    assert (report_dir / "VA_IT_Role_Metrics.csv").exists()
    html = html_path.read_text()
    assert "VA IT Pricing Benchmark" in html
    assert "pageLength: 50" in html
    js = json.loads(
        (report_dir / "VA_data.js")
        .read_text()
        .removeprefix("const pricingData = ")
        .removesuffix(";")
    )
    assert js[0]["t"] == "ANALYST"


def test_generate_reports_uses_variant_page_length(cfg, mgmt):
    _write_metrics(cfg, mgmt, "VA")
    (html_path,) = generate_reports(cfg, mgmt, states=["VA"])
    assert "pageLength: 25" in html_path.read_text()
    assert "Management Consulting (541611) Pricing" in html_path.read_text()


def test_generate_reports_skips_missing_metrics(cfg, it, caplog):
    paths = generate_reports(cfg, it, states=["VA"])
    assert paths == []

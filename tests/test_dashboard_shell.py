"""Tests for dashboard shell escaping and the Excel link (patch 04)."""

from __future__ import annotations

import pandas as pd

from vendors_toolkit.reporting.dashboard import _dashboard_html, generate_reports


def _html(**overrides):
    kwargs = {
        "page_title": "Title",
        "heading": "Heading",
        "filter_note": "",
        "csv_name": "VA_IT_Role_Metrics.csv",
        "xlsx_name": "VA_IT_Role_Metrics.xlsx",
        "js_filename": "VA_data.js",
        "page_length": 50,
        "jquery_url": "https://example.com/jquery.js",
        "datatables_css_url": "https://example.com/dt.css",
        "datatables_js_url": "https://example.com/dt.js",
        "font_url": "https://example.com/font.css",
    }
    kwargs.update(overrides)
    return _dashboard_html(**kwargs)


def test_dashboard_shell_escapes_title_heading_and_note():
    html = _html(
        page_title="<b>Title</b>",
        heading="<script>alert(1)</script>",
        filter_note="<i>note</i>",
    )
    # The template legitimately contains <script> tags for its own JS;
    # what must not appear is the injected string, unescaped.
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Title&lt;/b&gt;" in html
    assert "&lt;i&gt;note&lt;/i&gt;" in html


def test_dashboard_omits_excel_link_when_workbook_absent(cfg, it):
    metrics_dir = cfg.paths.variant_dir(it.dirs.metrics)
    metrics_dir.mkdir(parents=True, exist_ok=True)
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
                "Merged_Descriptions": "Does analysis",
                "Price_Range": 100.0,
            }
        ]
    ).to_csv(metrics_dir / it.metrics_filename_template.format(state="VA"), index=False)
    (html_path,) = generate_reports(cfg, it, states=["VA"])
    html = html_path.read_text()
    assert "Download CSV" in html
    assert "Download Excel" not in html


def test_dashboard_keeps_excel_link_when_workbook_present(cfg, it):
    metrics_dir = cfg.paths.variant_dir(it.dirs.metrics)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
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
            }
        ]
    )
    csv_path = metrics_dir / it.metrics_filename_template.format(state="VA")
    frame.to_csv(csv_path, index=False)
    frame.to_excel(csv_path.with_suffix(".xlsx"), index=False)
    (html_path,) = generate_reports(cfg, it, states=["VA"])
    assert "Download Excel" in html_path.read_text()

"""Unified HTML dashboard + executive summary reporting.

Merges ``generate_pricing_reports.py`` and ``generate_541611_reports.py`` onto
the richer IT dashboard: the 541611 variant gets the nicer styling, the Range
column, description-variation counts, and an executive summary it never had.

Security fix vs both originals: vendor description text is HTML-escaped
before being embedded in the dashboard. The originals interpolated it raw, so
a description containing markup would break (or hijack) the rendered page.
For descriptions without special characters the output is unchanged.
"""

from __future__ import annotations

import html
import json
import logging
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import is_missing

logger = logging.getLogger(__name__)


class DashboardRow(TypedDict):
    """One row of the dashboard's ``pricingData`` JS array."""

    t: str
    d_h: str
    d_c: int
    c: int
    m: str
    mi: str
    ma: str
    me: str
    r: str
    m_r: float
    mi_r: float
    ma_r: float
    me_r: float
    r_r: float


def description_html(desc_value: object, sample_limit: int) -> tuple[int, str]:
    """Build the description cell: (variation count, html list).

    Description text is HTML-escaped; the originals interpolated it raw.
    """
    if is_missing(desc_value) or not str(desc_value).strip():
        return 0, "<i>No description available.</i>"
    descs = [d.strip() for d in str(desc_value).split("|") if d.strip()]
    items = "".join(f"<li>{html.escape(d)}</li>" for d in descs[:sample_limit])
    if len(descs) > sample_limit:
        items += f"<li>... and {len(descs) - sample_limit} more variations in the source data.</li>"
    return len(descs), f"<ul>{items}</ul>"


def build_table_data(df_display: pd.DataFrame, sample_limit: int) -> list[DashboardRow]:
    """Build the ``pricingData`` rows from the display frame."""
    table_data: list[DashboardRow] = []
    for _, r in df_display.sort_values("Title_Key").iterrows():
        desc_count, desc_html = description_html(r.get("Merged_Descriptions", ""), sample_limit)
        table_data.append(
            {
                "t": str(r["Title_Key"]),
                "d_h": desc_html,
                "d_c": desc_count,
                "c": int(r["Count"]),
                "m": f"${r['Mean_Price']:,.2f}",
                "mi": f"${r['Min_Price']:,.2f}",
                "ma": f"${r['Max_Price']:,.2f}",
                "me": f"${r['Median_Price']:,.2f}",
                "r": f"${r['Price_Range']:,.2f}" if r["Count"] > 1 else "-",
                "m_r": float(r["Mean_Price"]),
                "mi_r": float(r["Min_Price"]),
                "ma_r": float(r["Max_Price"]),
                "me_r": float(r["Median_Price"]),
                "r_r": float(r["Price_Range"]) if r["Count"] > 1 else -1.0,
            }
        )
    return table_data


def _executive_summary(
    df: pd.DataFrame,
    state: str,
    title: str,
    filter_note: str,
    html_name: str,
) -> str:
    """Build the executive summary Markdown (byte-faithful port)."""
    lines = [
        title.format(state=state),
        "",
        f"- **Total Unique Roles**: {len(df):,}",
        f"- **Dashboard Filter**: {filter_note if filter_note else 'None'}",
        "",
        "## 🏆 Top 10 Roles by Frequency",
        "| Job Title | Count | Mean Price |",
        "| :--- | :---: | :---: |",
    ]
    for _, row in df.head(10).iterrows():
        lines.append(f"| {row['Title_Key']} | {row['Count']} | ${row['Mean_Price']:,.2f} |")
    lines.append("")
    lines.append(f"[View Full Interactive Report](./{html_name})")
    return "\n".join(lines)


def _dashboard_html(
    *,
    page_title: str,
    heading: str,
    filter_note: str,
    csv_name: str,
    xlsx_name: str,
    js_filename: str,
    page_length: int,
    jquery_url: str,
    datatables_css_url: str,
    datatables_js_url: str,
    font_url: str,
) -> str:
    """Render the thin-shell DataTables dashboard HTML."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <link rel="stylesheet" href="{datatables_css_url}">
    <link href="{font_url}" rel="stylesheet">
    <style>
        :root {{ --p: #1e3a8a; --s: #f8fafc; --t: #64748b; }}
        body {{ font-family: 'Inter', sans-serif; background: var(--s); margin: 0; color: #1e293b; }}
        .header {{ background: #1e3a8a; color: white; padding: 2.5rem 1rem; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 2rem; }}
        .header p {{ margin: 0.5rem 0 0; opacity: 0.9; }}
        .container {{ max-width: 1400px; margin: -2rem auto 2rem; padding: 1.5rem; background: white; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }}
        
        .title-txt {{ font-weight: 700; color: var(--p); font-size: 0.95rem; }}
        .badge {{ background: #eff6ff; color: var(--p); padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; border: 1px solid #dbeafe; }}
        .price {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-weight: 600; color: #0f172a; }}
        
        .desc-box {{ border: 1px solid #e2e8f0; border-radius: 8px; margin-top: 8px; background: #fcfcfd; }}
        .desc-box summary {{ padding: 8px 12px; cursor: pointer; font-size: 0.8rem; color: var(--t); font-weight: 500; list-style: none; }}
        .desc-box summary::-webkit-details-marker {{ display: none; }}
        .desc-box summary:hover {{ background: #f1f5f9; }}
        .desc-box[open] summary {{ border-bottom: 1px solid #e2e8f0; }}
        .desc-list {{ padding: 10px 15px; font-size: 0.8rem; line-height: 1.5; color: #475569; }}
        .desc-list ul {{ margin: 0; padding-left: 20px; }}
        
        table.dataTable.compact thead th {{ background: #f1f5f9; padding: 12px 10px; border-bottom: 2px solid #e2e8f0; font-weight: 700; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; color: #475569; }}
        .dt-right {{ text-align: right !important; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{heading}</h1>
        <p>{filter_note}</p>
        <div style="margin-top:1.5rem; display: flex; justify-content: center; gap: 10px;">
            <a href="./{csv_name}" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📊 Download CSV</a>
            <a href="./{xlsx_name}" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📁 Download Excel</a>
        </div>
    </div>
    <div class="container">
        <table id="priceTable" class="display compact hover" style="width:100%">
            <thead>
                <tr>
                    <th>Role & Descriptions</th>
                    <th>Count</th>
                    <th>Mean</th>
                    <th>Min</th>
                    <th>Max</th>
                    <th>Median</th>
                    <th>Range</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>

    <script src="{jquery_url}"></script>
    <script src="{datatables_js_url}"></script>
    <script src="./{js_filename}"></script>
    <script>
        $(document).ready(function() {{
            $('#priceTable').DataTable({{
                data: pricingData,
                deferRender: true,
                pageLength: {page_length},
                order: [[ 0, "asc" ]],
                columns: [
                    {{ 
                        data: "t",
                        width: "40%",
                        render: function(data, type, row) {{
                            if (type === 'display') {{
                                return '<div class="title-txt">' + data + '</div>' +
                                       '<details class="desc-box">' +
                                       '<summary>⊕ ' + row.d_c + ' Job Description Variations</summary>' +
                                       '<div class="desc-list">' + row.d_h + '</div>' +
                                       '</details>';
                            }}
                            return data;
                        }}
                    }},
                    {{ 
                        data: "c", 
                        className: "dt-right",
                        render: d => '<span class="badge">' + d + '</span>'
                    }},
                    {{ data: "m", className: "dt-right price", orderData: [7] }},
                    {{ data: "mi", className: "dt-right price", orderData: [8] }},
                    {{ data: "ma", className: "dt-right price", orderData: [9] }},
                    {{ data: "me", className: "dt-right price", orderData: [10] }},
                    {{ data: "r", className: "dt-right price", orderData: [11] }},
                    {{ data: "m_r", visible: false }},
                    {{ data: "mi_r", visible: false }},
                    {{ data: "ma_r", visible: false }},
                    {{ data: "me_r", visible: false }},
                    {{ data: "r_r", visible: false }}
                ],
                language: {{
                    searchPlaceholder: "Search roles...",
                    search: ""
                }}
            }});
        }});
    </script>
</body>
</html>
"""


def generate_reports(
    cfg: Config,
    variant: VariantConfig,
    *,
    states: Sequence[str] | None = None,
) -> list[Path]:
    """Generate dashboards + executive summaries for one variant.

    Copies the metrics CSV/XLSX into the report dir for portability, then
    writes the Markdown executive summary, the ``pricingData`` JS file, and
    the thin-shell HTML dashboard per state. Returns the HTML paths written.
    """
    states = tuple(states) if states is not None else variant.states
    metrics_dir = cfg.paths.variant_dir(variant.dirs.metrics)
    report_dir = cfg.paths.variant_dir(variant.dirs.reports)
    report_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for state in states:
        metrics_csv = metrics_dir / variant.metrics_filename_template.format(state=state)
        if not metrics_csv.exists():
            logger.warning("Skipping %s: metrics file not found.", state)
            continue

        shutil.copy2(metrics_csv, report_dir / metrics_csv.name)
        metrics_xlsx = metrics_csv.with_suffix(".xlsx")
        if metrics_xlsx.exists():
            shutil.copy2(metrics_xlsx, report_dir / metrics_xlsx.name)

        logger.info("Generating reports for %s...", state)
        df = pd.read_csv(metrics_csv)

        min_count = cfg.metrics.national_display_min_count
        if state == "National":
            df_display = df[df["Count"] >= min_count].copy()
            filter_note = (
                f" (Displaying {len(df_display):,} roles with {min_count}+ entries. "
                "Niche roles available in Excel.)"
            )
        else:
            df_display = df.copy()
            filter_note = ""

        html_name = variant.report_html_template.format(state=state)
        js_name = variant.report_js_template.format(state=state)

        summary_path = report_dir / variant.report_summary_template.format(state=state)
        summary_path.write_text(
            _executive_summary(
                df,
                state,
                variant.report_summary_title_template,
                filter_note,
                html_name,
            ),
            encoding="utf-8",
        )

        table_data = build_table_data(df_display, cfg.report.description_sample_limit)
        (report_dir / js_name).write_text(
            f"const pricingData = {json.dumps(table_data)};", encoding="utf-8"
        )

        html_path = report_dir / html_name
        html_path.write_text(
            _dashboard_html(
                page_title=variant.report_page_title_template.format(state=state),
                heading=variant.report_heading_template.format(state=state),
                filter_note=filter_note,
                csv_name=metrics_csv.name,
                xlsx_name=metrics_xlsx.name,
                js_filename=js_name,
                page_length=variant.report_page_length,
                jquery_url=cfg.report.jquery_url,
                datatables_css_url=cfg.report.datatables_css_url,
                datatables_js_url=cfg.report.datatables_js_url,
                font_url=cfg.report.font_url,
            ),
            encoding="utf-8",
        )
        logger.info("Generated dashboard: %s", html_path)
        written.append(html_path)

    return written

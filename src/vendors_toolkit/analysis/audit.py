"""Dataset diagnostics: the data audit and title/SIN cardinality.

``run_audit`` is a faithful port of ``data_audit.py`` (minus its duplicated
``GSA_MAP`` copy and duplicated ``__main__`` block): it writes
``output/audit_summary.md`` plus per-column JSON selections. ``analyze_cardinality``
is a structured port of ``analyze_master_data.py`` -- the same figures are
logged and returned as :class:`CardinalityReport` instead of only printed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import normalize_title_key
from vendors_toolkit.data.mapping import GSA_MAP

logger = logging.getLogger(__name__)


def run_audit(cfg: Config, input_path: Path | str) -> Path:
    """Audit a vendor CSV: summary Markdown plus per-column JSON selections.

    Returns the summary Markdown path.

    Raises:
        FileNotFoundError: If the input CSV does not exist.
    """
    data_path = Path(input_path)
    if not data_path.exists():
        logger.error("File not found: %s", data_path)
        raise FileNotFoundError(f"File not found: {data_path}")

    output_dir = cfg.paths.output
    selections_dir = cfg.paths.column_selections
    selections_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path)
    df = df.rename(columns=dict(cfg.audit.renamed_columns))

    lines = ["# DATA AUDIT SUMMARY", f"\n**Total Row Count:** {len(df)}"]
    if "Price List" in df.columns:
        lines.append(f"**Vendors with Price List:** {df['Price List'].count()}")

    lines.append("\n## Geographic Focus: VA & DC")
    if "State" in df.columns:
        va_vendors = df[df["State"] == "VA"]
        dc_vendors = df[df["State"] == "DC"]

        lines.append("### Virginia (VA)")
        lines.append(f"- **Total VA Vendors:** {len(va_vendors)}")
        if not va_vendors.empty and "City" in df.columns:
            lines.append("- **Breakdown by City (Top 15):**")
            for city, count in va_vendors["City"].value_counts().head(cfg.audit.top_cities).items():
                lines.append(f"  - {city}: {count}")

        lines.append("\n### Washington DC (DC)")
        lines.append(f"- **Total DC Vendors:** {len(dc_vendors)}")

    lines.append("\n## Column Headers (Non-Null Values)")
    for i, col in enumerate(df.columns, 1):
        lines.append(f"{i}. {col} ({df[col].count()} entries)")

    lines.append("\n## Categorical Values (Exported to /output/column_selections/)")
    for col in df.columns:
        if col in cfg.audit.skip_columns:
            continue
        unique_raw = df[col].dropna().unique()
        if 0 < len(unique_raw) <= cfg.audit.max_unique_values:
            mapped_vals = sorted(GSA_MAP.get(str(v), str(v)) for v in unique_raw)
            lines.append(f"- **{col}**: {len(mapped_vals)} unique values found.")
            safe_name = "".join(c if c.isalnum() else "_" for c in str(col))
            (selections_dir / f"{safe_name}.json").write_text(
                json.dumps(
                    {
                        "column": col,
                        "unique_count": len(mapped_vals),
                        "values": mapped_vals,
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )

    lines.append("\n## First 3 Rows (Sample Data)")
    lines.append("```json")
    lines.append(json.dumps(df.head(3).to_dict(orient="records"), indent=4))
    lines.append("```")

    output_path = output_dir / cfg.audit.summary_filename
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Audit completed. Summary: %s", output_path)
    logger.info("Selection JSONs: %s", selections_dir)
    return output_path


@dataclass(frozen=True)
class CardinalityReport:
    """Title/SIN cardinality diagnostic for one merged master file."""

    region: str
    file: Path
    total_rows: int
    unique_titles: int
    top_titles: list[tuple[str, int, float]]  # (title, count, pct_of_rows)
    top_sins: list[tuple[str, int]]


def analyze_cardinality(
    cfg: Config,
    variant: VariantConfig,
    *,
    states: Sequence[str] | None = None,
) -> list[CardinalityReport]:
    """Report title/SIN cardinality for a variant's merged masters."""
    states = tuple(states) if states is not None else variant.shard_states
    analysis_dir = cfg.paths.variant_dir(variant.dirs.analysis)

    reports: list[CardinalityReport] = []
    for state in states:
        file_path = analysis_dir / variant.merged_filename_template.format(state=state)
        if not file_path.exists():
            logger.warning("File not found: %s", file_path)
            continue
        df = pd.read_csv(file_path, low_memory=cfg.metrics.csv_low_memory)
        if "Title" not in df.columns:
            logger.error("Column 'Title' not found in %s", file_path)
            continue

        title_clean = normalize_title_key(df["Title"])
        total_rows = len(df)
        unique_titles = int(title_clean.nunique())
        logger.info("Analysis for %s master price list:", state)
        logger.info("  Total rows: %d", total_rows)
        logger.info("  Unique titles (case-insensitive): %d", unique_titles)

        top_titles: list[tuple[str, int, float]] = []
        for title, count in title_clean.value_counts().head(cfg.audit.top_titles).items():
            pct = (count / total_rows * 100) if total_rows else 0.0
            top_titles.append((str(title), int(count), pct))
            logger.info("  - %s: %d (%.2f%%)", title, count, pct)

        top_sins: list[tuple[str, int]] = []
        if "SIN" in df.columns:
            sin_counts = df["SIN"].astype(str).str.strip().value_counts().head(cfg.audit.top_sins)
            for sin, count in sin_counts.items():
                top_sins.append((str(sin), int(count)))
                logger.info("  - SIN %s: %d", sin, count)

        reports.append(
            CardinalityReport(
                region=state,
                file=file_path,
                total_rows=total_rows,
                unique_titles=unique_titles,
                top_titles=top_titles,
                top_sins=top_sins,
            )
        )
    return reports

"""SAM.gov Responsibility and Integrity Records analysis (offline export).

Folds in ``mp-sam-data-bank``: that tool read a SAM.gov FPS export of
responsibility/integrity records (an Excel workbook with a two-row preamble,
a header row, then one row per record) and produced descriptive counts plus a
PDF. This module keeps the loader and the counts, fixes what was broken in
the original, and drops the PDF in favour of the toolkit's CSV + Markdown
reporting (no new dependency, and the original's single unpaginated text
block ran off the page on any real export).

Fixes vs. the original, all covered by tests:

- The original imported ``reportlab`` but never declared it, so a fresh
  install failed at import. This module needs only pandas/openpyxl, which
  the toolkit already depends on.
- The original hardcoded ``F:/Code/mp-sam-data-bank/data`` and took the
  first ``.xlsx`` in it. The input is now a CLI argument, defaulting to the
  first ``.xlsx`` under ``<root>/integrity/`` (sorted), and a missing file
  raises ``FileNotFoundError`` instead of printing and exiting silently.
- The original used ``skiprows=2`` blindly and ``row.get(...)`` per row, so
  empty cells leaked into the dataclass as float ``NaN`` (every
  subcontractor field, most NAICS codes) and dates stayed pandas
  Timestamps. The loader now finds the header row by content, validates
  the required columns, normalizes empties to ``NaN``, parses dates to
  midnight, and coerces float-formatted NAICS codes (``315990.0``) back to
  their code string. Note the export stores header cells with a leading
  quote marker (``'CAGE Code'`` when read raw); headers are stripped of it.
- The original counted raw timestamps, so "trend" counts were per
  timestamp, not per period. Monthly counts are bucketed ``YYYY-MM``.
- Eleven of the export's 38 columns are entirely empty in the snapshot the
  original shipped with (all subcontractor fields, Violation Against).
  They are kept in the loaded frame (the schema is the export's), reported
  as empty, and ignored by the counts instead of silently polluting them.

The real export is never shipped: it contains thousands of officials'
contact details. The repo ships a small fictional workbook under
``sample-data/integrity/`` with the same 38-column layout and preamble.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from vendors_toolkit.config import Config
from vendors_toolkit.data.cleaning import is_missing

logger = logging.getLogger(__name__)

# The export's 38 columns, in order. The loader validates the required
# subset and keeps whatever else the workbook carries, in file order.
INTEGRITY_COLUMNS: tuple[str, ...] = (
    "CAGE Code",
    "Unique Entity ID",
    "Awardee Name",
    "Address 1",
    "Address 2",
    "City",
    "State",
    "Zip",
    "Country",
    "Record Type",
    "Record Date",
    "Contract/Grant Number",
    "Referenced Number",
    "Agency",
    "Solicitation/Funding Number",
    "Subcontractor Unique Entity ID",
    "Subcontractor CAGE",
    "Subcontractor Name",
    "Subcontractor DBA",
    "Subcontractor Address1",
    "Subcontractor Address2",
    "Subcontractor City",
    "Subcontractor State",
    "Subcontractor Zip Code",
    "Subcontractor Country",
    "Violation Against",
    "Product/Service Code",
    "Principal NAICS Code",
    "Agency ID",
    "Official Name",
    "Official Phone",
    "Official Email",
    "Termination Type",
    "Termination Date",
    "User",
    "Email",
    "Phone",
    "Comments",
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "Awardee Name",
    "Record Type",
    "Record Date",
    "Agency",
)

DATE_COLUMNS: tuple[str, ...] = ("Record Date", "Termination Date")


@dataclass(frozen=True)
class IntegritySummary:
    """Counts over one integrity-records export. Count dicts are sorted
    by count descending (encounter order breaks ties)."""

    total_records: int
    record_type_counts: dict[str, int]
    agency_counts: dict[str, int]
    state_counts: dict[str, int]
    naics_counts: dict[str, int]
    termination_type_counts: dict[str, int]
    monthly_counts: dict[str, int]
    most_common_agency: tuple[str, int] | None
    most_common_naics: tuple[str, int] | None
    earliest_record_date: date | None
    latest_record_date: date | None
    empty_columns: tuple[str, ...]


def _clean_header_cell(value: object) -> str:
    """Strip whitespace and the export's leading quote marker from a header."""
    return str(value).strip().strip("'").strip()


def _find_header_row(raw: pd.DataFrame, *, search_rows: int) -> int:
    """Locate the header row: the first row naming CAGE Code and Record Type."""
    for idx in range(min(search_rows, len(raw))):
        values = {_clean_header_cell(v) for v in raw.iloc[idx].tolist()}
        if "CAGE Code" in values and "Record Type" in values:
            return idx
    raise ValueError(
        "No SAM.gov integrity-records header row found in the first "
        f"{search_rows} rows (expected 'CAGE Code' and 'Record Type')."
    )


def _normalize_text(value: object) -> str:
    """Strip a cell to its text form; missing values become an empty string."""
    if is_missing(value):
        return ""
    return str(value).strip()


def _normalize_naics(value: object) -> str:
    """Normalize a NAICS code: strip, and drop a float-formatted ``.0``."""
    text = _normalize_text(value)
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize a headered frame: stripped text, parsed dates, NAICS codes.

    Empty text cells become ``pd.NA`` (the original leaked them as float
    ``NaN`` into its dataclass fields).
    """
    columns: dict[str, pd.Series] = {}
    for column in frame.columns:
        if column in DATE_COLUMNS:
            parsed = pd.to_datetime(frame[column], errors="coerce")
            columns[column] = parsed.dt.normalize()
        elif column == "Principal NAICS Code":
            values = frame[column].map(_normalize_naics)
            columns[column] = values.where(values != "", pd.NA)
        else:
            values = frame[column].map(_normalize_text)
            columns[column] = values.where(values != "", pd.NA)
    return cast("pd.DataFrame", pd.DataFrame(columns, index=frame.index))


def load_integrity_records(path: Path | str, *, search_rows: int = 5) -> pd.DataFrame:
    """Load a SAM.gov integrity-records export workbook.

    Reads every cell as text (so ZIP/NAICS codes keep leading zeros and
    never become floats), finds the header row by content, validates the
    required columns, and returns a normalized frame with one row per
    record and the export's columns in file order.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Integrity-records export not found: {path}")
    raw = pd.read_excel(path, header=None, dtype=str, engine="openpyxl")
    header_idx = _find_header_row(raw, search_rows=search_rows)
    columns = [_clean_header_cell(v) for v in raw.iloc[header_idx].tolist()]
    if "" in columns:
        raise ValueError("Integrity-records header row contains an unnamed column.")
    if len(set(columns)) != len(columns):
        raise ValueError("Integrity-records header row contains a duplicate column.")
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise ValueError(
            "Integrity-records export is missing required column(s): " + ", ".join(missing)
        )
    frame = raw.iloc[header_idx + 1 :].copy()
    frame.columns = pd.Index(columns)
    frame = frame.dropna(how="all").reset_index(drop=True)
    return _normalize_frame(frame)


def _value_counts(series: pd.Series) -> dict[str, int]:
    """Counts of non-empty values, most common first."""
    values = [str(v).strip() for v in series.tolist() if not is_missing(v) and str(v).strip()]
    return dict(Counter(values).most_common())


def _most_common(counts: dict[str, int]) -> tuple[str, int] | None:
    if not counts:
        return None
    return next(iter(counts.items()))


def analyze_integrity_records(frame: pd.DataFrame) -> IntegritySummary:
    """Compute descriptive counts over a loaded integrity-records frame."""
    for column in REQUIRED_COLUMNS:
        if column not in frame.columns:
            raise ValueError(f"Integrity-records frame is missing column: {column}")
    record_dates = pd.to_datetime(frame["Record Date"], errors="coerce").dropna()
    monthly = Counter(record_dates.dt.strftime("%Y-%m").tolist())
    dates = [d.date() for d in record_dates.dt.normalize().tolist()]
    empty = tuple(column for column in frame.columns if bool(frame[column].map(is_missing).all()))
    agency_counts = _value_counts(frame["Agency"])
    naics_counts = (
        _value_counts(frame["Principal NAICS Code"])
        if "Principal NAICS Code" in frame.columns
        else {}
    )
    return IntegritySummary(
        total_records=len(frame),
        record_type_counts=_value_counts(frame["Record Type"]),
        agency_counts=agency_counts,
        state_counts=_value_counts(frame["State"]) if "State" in frame.columns else {},
        naics_counts=naics_counts,
        termination_type_counts=_value_counts(frame["Termination Type"])
        if "Termination Type" in frame.columns
        else {},
        monthly_counts=dict(sorted(monthly.items())),
        most_common_agency=_most_common(agency_counts),
        most_common_naics=_most_common(naics_counts),
        earliest_record_date=min(dates) if dates else None,
        latest_record_date=max(dates) if dates else None,
        empty_columns=empty,
    )


def _write_counts(path: Path, counts: dict[str, int], value_header: str) -> Path:
    rows = [{"value": key, "count": value} for key, value in counts.items()]
    frame = pd.DataFrame(rows, columns=["value", "count"])
    frame = frame.rename(columns={"value": value_header})
    frame.to_csv(path, index=False)
    return path


def write_integrity_report(summary: IntegritySummary, output_dir: Path | str) -> list[Path]:
    """Write count CSVs and a Markdown summary for an integrity summary."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = [
        _write_counts(
            output_dir / "integrity_record_type_counts.csv",
            summary.record_type_counts,
            "Record Type",
        ),
        _write_counts(output_dir / "integrity_agency_counts.csv", summary.agency_counts, "Agency"),
        _write_counts(output_dir / "integrity_state_counts.csv", summary.state_counts, "State"),
        _write_counts(
            output_dir / "integrity_naics_counts.csv", summary.naics_counts, "NAICS Code"
        ),
        _write_counts(
            output_dir / "integrity_monthly_counts.csv",
            summary.monthly_counts,
            "Month",
        ),
    ]
    lines = [
        "# SAM.gov Responsibility and Integrity Records Summary",
        "",
        f"- **Total records**: {summary.total_records}",
    ]
    if summary.earliest_record_date is not None and summary.latest_record_date is not None:
        lines.append(
            f"- **Record dates**: {summary.earliest_record_date} to {summary.latest_record_date}"
        )
    if summary.most_common_agency is not None:
        name, count = summary.most_common_agency
        lines.append(f"- **Most common agency**: {name} ({count})")
    if summary.most_common_naics is not None:
        name, count = summary.most_common_naics
        lines.append(f"- **Most common NAICS**: {name} ({count})")
    lines.extend(["", "## Record types", "", "| Record Type | Count |", "| --- | ---: |"])
    for name, count in summary.record_type_counts.items():
        lines.append(f"| {name} | {count} |")
    if summary.empty_columns:
        lines.extend(
            [
                "",
                "## Empty columns",
                "",
                "Entirely empty in this export: " + ", ".join(summary.empty_columns) + ".",
            ]
        )
    md_path = output_dir / "integrity_summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    written.append(md_path)
    return written


def _discover_input(cfg: Config) -> Path | None:
    """First ``.xlsx`` under ``<root>/<integrity input dir>``, sorted, if any."""
    input_dir = cfg.root / cfg.integrity.input_dirname
    if not input_dir.is_dir():
        return None
    files = sorted(input_dir.glob("*.xlsx"))
    return files[0] if files else None


def analyze_integrity_export(
    cfg: Config,
    *,
    input_path: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> list[Path]:
    """Load, analyze, and report one integrity-records export.

    With no ``input_path``, the first ``.xlsx`` under
    ``<root>/integrity/`` is used. Reports land in
    ``<root>/output/integrity/`` unless ``output_dir`` is given.
    """
    resolved = Path(input_path) if input_path is not None else _discover_input(cfg)
    if resolved is None:
        raise FileNotFoundError(
            f"No .xlsx export found under {cfg.root / cfg.integrity.input_dirname}/. "
            "Pass --input, or place the SAM.gov export there."
        )
    frame = load_integrity_records(resolved, search_rows=cfg.integrity.header_search_rows)
    summary = analyze_integrity_records(frame)
    logger.info("Loaded %d integrity records from %s.", summary.total_records, resolved)
    out = (
        Path(output_dir)
        if output_dir is not None
        else cfg.paths.output / cfg.integrity.output_dirname
    )
    return write_integrity_report(summary, out)

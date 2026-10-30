"""SAM.gov contract-opportunity search results (folded in from ``mp-sam``).

``mp-sam`` was a Selenium scraper: it drove the SAM.gov search page in a
headless browser, followed the next-page button with absolute XPaths, and
wrote the notice IDs it saw to CSV. This module keeps the salvageable part
of that tool -- search active opportunities, keep one row per notice ID,
export a clean CSV -- and replaces the scraping with the toolkit's official
SAM.gov API client (:class:`vendors_toolkit.integrations.samgov.SamGovClient`).
SAM.gov's own terms name its APIs and data-services extracts as the
sanctioned ways to get this data; a page scraper breaks on the next markup
change and burns a browser session per run, while one API call returns up
to the requested ``limit`` of records.

Response shape handled here (the shape the existing scaffold already
assumes, and the shape the public API documentation describes): the search
payload is an object with an ``opportunitiesData`` list. Each row carries
``noticeId`` (required), ``title``, ``fullParentPathName`` (agency path),
``type``, ``naicsCode`` (or, on some rows, a ``naicsCodes`` list),
``typeOfSetAside``, ``postedDate``, ``responseDeadLine``, and optionally
``solicitationNumber``. Dates are kept as the strings the API returns;
parsing them into datetimes would invent a format the API does not promise
here.

Live-run status: the parser and CSV writer below are covered by tests
against a fictional fixture in that shape, but no live API call has been
made from this box -- the client is inert without ``SAM_API_KEY``, and no
key is stored here. The first run with a real key is still the gate for
confirming the live field set; if a field arrives under a different key,
fix the mapping in :func:`parse_opportunities` rather than widening it
silently.

Fixes vs. the original, all covered by tests:

- The original's ``ContractOpportunity.from_text`` overwrote ``title`` on
  every line without a ``": "`` separator, so the last free-text line won,
  and it printed a debug dump of every record it parsed. The model here
  is a frozen dataclass with one field per API key; there is no
  free-text parsing at all.
- The original imported its model in the scraper but never used it, and
  the committed text dump and extracted CSV were never written by any
  committed code (the scraper only wrote ``notice_ids.csv``). Here the
  parse -> dedupe -> CSV path is a single tested function chain.
- The original's extracted CSV was a garbled 3-line file mixing several
  opportunities into one row. The writer here emits a fixed header and
  exactly one row per notice.
- The original's notice-ID list had 10,032 rows for 9,416 unique IDs.
  Parsing deduplicates on ``noticeId``, first occurrence wins, and the
  summary reports how many duplicates were dropped.
- The original hardcoded ``/Users/justinlyons/code/mp-sam/exports/csv``
  as its output directory. Output is now a CLI argument, defaulting to
  ``<root>/output/opportunities/``.
- The original had no pagination safety, no resume, and no ``finally``
  around the browser. The API call is a single request per invocation
  (same budget rule as the ``sam`` stage: it runs once, not per variant),
  so there is no browser session to leak and no unbounded page loop.
- The original shipped a March 2025 bulk snapshot of real notices,
  including awardee names and Unique Entity IDs, plus two saved SAM.gov
  HTML pages. None of that ships here: the repo ships a 5-row fictional
  payload under ``sample-data/opportunities/`` and the ``--input`` path
  below lets that payload be exercised with no API key at all.

Rows missing ``noticeId`` are skipped, not coerced: a row with no
identifier cannot be deduplicated or linked back to SAM.gov, so it is
counted in ``skipped_rows`` and dropped. Every other field is optional
and normalizes blank strings to ``None``.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vendors_toolkit.config import Config

logger = logging.getLogger(__name__)

OPPORTUNITY_CSV_COLUMNS: tuple[str, ...] = (
    "notice_id",
    "title",
    "agency",
    "notice_type",
    "naics_code",
    "set_aside",
    "posted_date",
    "response_deadline",
    "solicitation_number",
)


@dataclass(frozen=True)
class ContractOpportunity:
    """One SAM.gov contract opportunity, typed. Replaces mp-sam's model."""

    notice_id: str
    title: str | None = None
    agency: str | None = None
    notice_type: str | None = None
    naics_code: str | None = None
    set_aside: str | None = None
    posted_date: str | None = None
    response_deadline: str | None = None
    solicitation_number: str | None = None

    def to_row(self) -> dict[str, str]:
        """CSV row in :data:`OPPORTUNITY_CSV_COLUMNS` order (None -> "")."""
        values = {
            "notice_id": self.notice_id,
            "title": self.title,
            "agency": self.agency,
            "notice_type": self.notice_type,
            "naics_code": self.naics_code,
            "set_aside": self.set_aside,
            "posted_date": self.posted_date,
            "response_deadline": self.response_deadline,
            "solicitation_number": self.solicitation_number,
        }
        return {column: (values[column] or "") for column in OPPORTUNITY_CSV_COLUMNS}


@dataclass(frozen=True)
class ParsedOpportunities:
    """Result of parsing one search payload."""

    opportunities: tuple[ContractOpportunity, ...]
    raw_rows: int
    skipped_rows: int
    duplicate_rows: int


def _clean(value: Any) -> str | None:
    """Normalize an optional API string: strip, blank -> None, else str."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _naics_code(row: dict[str, Any]) -> str | None:
    """NAICS code from ``naicsCode`` or, failing that, ``naicsCodes[0]``.

    The API returns both forms across rows; preferring the scalar and
    falling back to the first list entry is the documented shape, not a
    guess -- but a list with no usable entry still yields None.
    """
    code = _clean(row.get("naicsCode"))
    if code is not None:
        return code
    codes = row.get("naicsCodes")
    if isinstance(codes, list):
        for entry in codes:
            cleaned = _clean(entry)
            if cleaned is not None:
                return cleaned
    return None


def _parse_row(row: dict[str, Any]) -> ContractOpportunity | None:
    """Parse one ``opportunitiesData`` row; None when it has no notice ID."""
    notice_id = _clean(row.get("noticeId"))
    if notice_id is None:
        return None
    return ContractOpportunity(
        notice_id=notice_id,
        title=_clean(row.get("title")),
        agency=_clean(row.get("fullParentPathName")),
        notice_type=_clean(row.get("type")),
        naics_code=_naics_code(row),
        set_aside=_clean(row.get("typeOfSetAside")),
        posted_date=_clean(row.get("postedDate")),
        response_deadline=_clean(row.get("responseDeadLine")),
        solicitation_number=_clean(row.get("solicitationNumber")),
    )


def parse_opportunities(payload: dict[str, Any]) -> ParsedOpportunities:
    """Parse a SAM.gov opportunity-search payload into typed opportunities.

    Deduplicates on ``notice_id`` (first occurrence wins) and skips rows
    with no notice ID. Raises :class:`ValueError` when the payload is not
    an object with an ``opportunitiesData`` list, rather than returning
    an empty result that would look like "no opportunities matched".
    """
    if not isinstance(payload, dict):
        raise ValueError("SAM.gov opportunity payload must be a JSON object.")
    rows = payload.get("opportunitiesData")
    if not isinstance(rows, list):
        raise ValueError("SAM.gov opportunity payload has no 'opportunitiesData' list.")
    seen: set[str] = set()
    opportunities: list[ContractOpportunity] = []
    skipped = 0
    duplicates = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        opportunity = _parse_row(row)
        if opportunity is None:
            skipped += 1
            continue
        if opportunity.notice_id in seen:
            duplicates += 1
            continue
        seen.add(opportunity.notice_id)
        opportunities.append(opportunity)
    logger.info(
        "Parsed %d opportunities (%d skipped, %d duplicates) from %d rows.",
        len(opportunities),
        skipped,
        duplicates,
        len(rows),
    )
    return ParsedOpportunities(
        opportunities=tuple(opportunities),
        raw_rows=len(rows),
        skipped_rows=skipped,
        duplicate_rows=duplicates,
    )


def load_opportunities_payload(input_path: Path | str) -> dict[str, Any]:
    """Load a saved SAM.gov search payload (JSON object) from disk."""
    path = Path(input_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Opportunity payload in {path} is not a JSON object.")
    return payload


def write_opportunities_report(
    parsed: ParsedOpportunities,
    output_dir: Path | str,
) -> list[Path]:
    """Write ``opportunities.csv`` (one row per notice) + a summary.

    The CSV header is fixed (:data:`OPPORTUNITY_CSV_COLUMNS`); the
    summary reports raw/skipped/duplicate counts and the most common
    agency, notice type, and NAICS code, so a run's yield is visible
    without opening the CSV.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "opportunities.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OPPORTUNITY_CSV_COLUMNS))
        writer.writeheader()
        for opportunity in parsed.opportunities:
            writer.writerow(opportunity.to_row())

    def most_common(values: list[str | None]) -> tuple[str, int] | None:
        counts = Counter(value for value in values if value is not None)
        return counts.most_common(1)[0] if counts else None

    lines = [
        "# SAM.gov Contract Opportunities Summary",
        "",
        f"- **Raw rows**: {parsed.raw_rows}",
        f"- **Unique opportunities**: {len(parsed.opportunities)}",
        f"- **Skipped rows (no notice ID)**: {parsed.skipped_rows}",
        f"- **Duplicate rows dropped**: {parsed.duplicate_rows}",
    ]
    for label, values in (
        ("Most common agency", [o.agency for o in parsed.opportunities]),
        ("Most common notice type", [o.notice_type for o in parsed.opportunities]),
        ("Most common NAICS", [o.naics_code for o in parsed.opportunities]),
    ):
        common = most_common(values)
        if common is not None:
            lines.append(f"- **{label}**: {common[0]} ({common[1]})")
    summary_path = out / "opportunities_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [csv_path, summary_path]


def analyze_opportunities_payload(
    cfg: Config,
    payload: dict[str, Any],
    *,
    output_dir: Path | str | None = None,
) -> list[Path]:
    """Parse one search payload and write its report.

    Reports land in ``<root>/output/opportunities/`` unless
    ``output_dir`` is given.
    """
    parsed = parse_opportunities(payload)
    out = (
        Path(output_dir)
        if output_dir is not None
        else cfg.paths.output / cfg.opportunities.output_dirname
    )
    return write_opportunities_report(parsed, out)

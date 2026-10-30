"""GSA legacy schedule solicitations archive (folded in from ``ss-gsa``).

``ss-gsa`` was a Scrapy project with two spiders. The solicitations spider
crawled GSA's eOffer portal (``eoffer.gsa.gov``) for legacy schedule
solicitations -- reference-only solicitations under which no new offers
are accepted -- and wrote one JSON file per schedule plus a listing index.
The forecast spider was an unfinished experiment against the Acquisition
Gateway forecast page: it guessed at API endpoints, never called its own
script-parsing method, and never yielded its typed item, so nothing from
it is carried over. The forecast idea is already covered better here by
the ``opportunities`` stage, which uses SAM.gov's official API instead of
guessed endpoints.

This module keeps only the salvageable job from ``ss-gsa``: normalize
saved solicitation JSON into a clean archive. It is deliberately *not* a
live scraper -- it adds no Scrapy dependency, makes no HTTP requests, and
contains no crawl settings to get wrong (the original ran with
``ROBOTSTXT_OBEY = False`` and a spoofed Chrome user agent). A live
re-crawl, if ever wanted, would be a separate decision with robots and
rate-limit rules of its own; the saved output is what this stage works
from, and the live eOffer selectors are unverified (the saved pages are
from February 2025).

Input shape handled here (the shape the spider actually wrote): one
solicitation object, or a list of them, per JSON file. Each object carries
``schedule`` (required), ``title``, ``status``, ``posted_date``,
``url``, and ``documents`` -- a list of ``{"name", "url"}`` pairs. The
loader also tolerates the original's two output quirks, because a stage
that cannot read the archive it claims to preserve is useless:

- The listing index is two JSON arrays concatenated in one file (two runs
  appended, never separated), which is invalid as a single JSON document.
  The loader decodes successive JSON values from a file instead of
  requiring exactly one.
- Every index row has ``documents: []``: the spider's feed item was
  emitted before its documents page was parsed, so the document lists
  only exist in the per-schedule files. Loading a directory merges rows
  for the same schedule, so an index row plus its per-schedule file
  combine into one complete record instead of one empty one.

Fixes vs. the original, all covered by tests:

- The original's index was unusable as JSON (concatenated arrays) and
  incomplete (empty ``documents`` on every row). The parser merges
  duplicates by schedule, unioning document lists by URL, and reports
  how many rows were merged.
- The original's ``status`` strings carry non-breaking spaces
  (``"Refresh\\u00a0#\\u00a021"``). Status text is whitespace-normalized
  here, so the CSV holds plain spaces.
- The original wrote files directly from the spider (bypassing its own
  pipeline and feed export), deleted prior outputs from the spider's
  ``__init__`` via a rotation helper that kept 2 backups instead of the
  intended 3, and stamped feed and spider outputs with different
  timestamps. Here parsing and writing are separate, tested functions;
  nothing is deleted, and output goes to the CLI's ``--output``
  directory (default ``<root>/output/solicitations/``).
- The original defined ``ScheduleDocumentItem`` but never used it,
  yielding plain dicts instead. The model here is a frozen dataclass
  with one field per JSON key.
- The original's 12 MB repo was mostly tracked output (9.2 MB of
  duplicated debug dumps alone). None of that ships here: the repo
  ships a 5-row fictional sample under ``sample-data/solicitations/``
  and the ``--input`` path below lets that sample be exercised with no
  crawl at all.

Rows missing ``schedule`` are skipped, not coerced: a solicitation with
no schedule number cannot be keyed or linked back to eOffer, so it is
counted in ``skipped_rows`` and dropped. Documents missing a name or a
URL are dropped and counted in ``dropped_documents``. Every other field
is optional and normalizes blank strings to ``None``. Posted dates are
kept as the strings the spider wrote; only dates that parse as
``YYYY-MM-DD`` feed the summary's date range, so an odd date string can
never silently shift the range.
"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from json import JSONDecoder
from pathlib import Path
from typing import Any

from vendors_toolkit.config import Config

logger = logging.getLogger(__name__)

SOLICITATION_CSV_COLUMNS: tuple[str, ...] = (
    "schedule",
    "title",
    "status",
    "posted_date",
    "url",
    "document_count",
)

DOCUMENT_CSV_COLUMNS: tuple[str, ...] = (
    "schedule",
    "document_name",
    "document_url",
)

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ScheduleDocument:
    """One document linked from a schedule solicitation."""

    name: str
    url: str

    def to_row(self, schedule: str) -> dict[str, str]:
        """CSV row in :data:`DOCUMENT_CSV_COLUMNS` order."""
        return {
            "schedule": schedule,
            "document_name": self.name,
            "document_url": self.url,
        }


@dataclass(frozen=True)
class Solicitation:
    """One legacy schedule solicitation, typed. Replaces ss-gsa's dicts."""

    schedule: str
    title: str | None = None
    status: str | None = None
    posted_date: str | None = None
    url: str | None = None
    documents: tuple[ScheduleDocument, ...] = ()

    def to_row(self) -> dict[str, str]:
        """CSV row in :data:`SOLICITATION_CSV_COLUMNS` order (None -> "")."""
        values = {
            "schedule": self.schedule,
            "title": self.title,
            "status": self.status,
            "posted_date": self.posted_date,
            "url": self.url,
            "document_count": str(len(self.documents)),
        }
        return {column: (values[column] or "") for column in SOLICITATION_CSV_COLUMNS}


@dataclass(frozen=True)
class ParsedSolicitations:
    """Result of parsing saved solicitation JSON."""

    solicitations: tuple[Solicitation, ...]
    raw_rows: int
    skipped_rows: int
    merged_rows: int
    dropped_documents: int

    @property
    def total_documents(self) -> int:
        """Total document links across all solicitations."""
        return sum(len(item.documents) for item in self.solicitations)


def _clean(value: Any) -> str | None:
    """Normalize an optional string: strip, blank -> None, else str."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_status(value: Any) -> str | None:
    """Normalize status text, collapsing non-breaking spaces to spaces.

    The spider's status strings join the solicitation number, "Refresh",
    and the refresh number with U+00A0 separators; collapsing all
    whitespace runs makes the CSV searchable and diffable.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return _WHITESPACE.sub(" ", cleaned)


def _parse_iso_date(value: str | None) -> date | None:
    """Parse a ``YYYY-MM-DD`` date, or None when the string is not one."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_document(row: Any) -> ScheduleDocument | None:
    """Parse one ``documents`` entry; None when name or URL is missing."""
    if not isinstance(row, dict):
        return None
    name = _clean(row.get("name"))
    url = _clean(row.get("url"))
    if name is None or url is None:
        return None
    return ScheduleDocument(name=name, url=url)


def _parse_row(row: dict[str, Any]) -> tuple[Solicitation, int] | None:
    """Parse one solicitation object; None when it has no schedule.

    Returns the solicitation plus how many of its documents were dropped
    for missing a name or URL.
    """
    schedule = _clean(row.get("schedule"))
    if schedule is None:
        return None
    documents: list[ScheduleDocument] = []
    dropped = 0
    raw_documents = row.get("documents")
    if isinstance(raw_documents, list):
        for entry in raw_documents:
            document = _parse_document(entry)
            if document is None:
                dropped += 1
            else:
                documents.append(document)
    return (
        Solicitation(
            schedule=schedule,
            title=_clean(row.get("title")),
            status=_clean_status(row.get("status")),
            posted_date=_clean(row.get("posted_date")),
            url=_clean(row.get("url")),
            documents=tuple(documents),
        ),
        dropped,
    )


def _merge_into(existing: Solicitation, incoming: Solicitation) -> Solicitation:
    """Merge a duplicate schedule row into the record already kept.

    First non-blank value wins for the scalar fields (so an index row
    with empty documents cannot clobber a per-schedule file's title),
    and document lists union by URL, first name wins, order preserved.
    """
    seen_urls = {document.url for document in existing.documents}
    documents = list(existing.documents)
    for document in incoming.documents:
        if document.url not in seen_urls:
            seen_urls.add(document.url)
            documents.append(document)
    return Solicitation(
        schedule=existing.schedule,
        title=existing.title or incoming.title,
        status=existing.status or incoming.status,
        posted_date=existing.posted_date or incoming.posted_date,
        url=existing.url or incoming.url,
        documents=tuple(documents),
    )


def parse_solicitations(rows: Iterable[Any]) -> ParsedSolicitations:
    """Parse solicitation objects into merged, deduplicated records.

    Rows are grouped by ``schedule`` (first occurrence order kept);
    extra rows for a schedule already seen merge into it and count in
    ``merged_rows``. Raises nothing for malformed rows: non-dict rows
    and rows without a schedule count as skipped.
    """
    by_schedule: dict[str, Solicitation] = {}
    order: list[str] = []
    raw = 0
    skipped = 0
    merged = 0
    dropped_documents = 0
    for row in rows:
        raw += 1
        if not isinstance(row, dict):
            skipped += 1
            continue
        parsed = _parse_row(row)
        if parsed is None:
            skipped += 1
            continue
        solicitation, dropped = parsed
        dropped_documents += dropped
        if solicitation.schedule in by_schedule:
            by_schedule[solicitation.schedule] = _merge_into(
                by_schedule[solicitation.schedule], solicitation
            )
            merged += 1
        else:
            by_schedule[solicitation.schedule] = solicitation
            order.append(solicitation.schedule)
    logger.info(
        "Parsed %d solicitations (%d skipped, %d merged) from %d rows.",
        len(order),
        skipped,
        merged,
        raw,
    )
    return ParsedSolicitations(
        solicitations=tuple(by_schedule[schedule] for schedule in order),
        raw_rows=raw,
        skipped_rows=skipped,
        merged_rows=merged,
        dropped_documents=dropped_documents,
    )


def _values_from_text(text: str, path: Path) -> list[Any]:
    """Decode every JSON value in a file's text, in order.

    A well-formed file holds one value (an object or a list); the
    original's index holds two lists back to back. Decoding successive
    values handles both, and trailing whitespace is fine. Anything else
    raises ValueError rather than returning a partial archive.
    """
    decoder = JSONDecoder()
    values: list[Any] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        value, end = decoder.raw_decode(text, index)
        values.append(value)
        index = end
    if not values:
        raise ValueError(f"Solicitation JSON in {path} holds no JSON value.")
    return values


def _rows_from_value(value: Any, path: Path) -> list[Any]:
    """Expand one decoded JSON value into solicitation rows."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    raise ValueError(
        f"Solicitation JSON in {path} must hold an object or a list, not {type(value).__name__}."
    )


def load_solicitations_file(input_path: Path | str) -> list[Any]:
    """Load solicitation rows from one JSON file (object, list, or both)."""
    path = Path(input_path)
    text = path.read_text(encoding="utf-8")
    rows: list[Any] = []
    for value in _values_from_text(text, path):
        rows.extend(_rows_from_value(value, path))
    return rows


def load_solicitations(input_path: Path | str) -> list[Any]:
    """Load solicitation rows from a JSON file or a directory of them.

    A directory is read in sorted filename order, recursively, so an
    index file plus per-schedule files merge deterministically. A file
    that fails to decode raises ValueError with its path in the message.
    """
    path = Path(input_path)
    if path.is_dir():
        rows: list[Any] = []
        for json_file in sorted(path.rglob("*.json")):
            rows.extend(load_solicitations_file(json_file))
        return rows
    if not path.is_file():
        raise FileNotFoundError(f"Solicitation input not found: {path}")
    return load_solicitations_file(path)


def write_solicitations_report(
    parsed: ParsedSolicitations,
    output_dir: Path | str,
) -> list[Path]:
    """Write ``solicitations.csv`` + ``solicitation_documents.csv`` + summary.

    The solicitations CSV holds one row per schedule (with a document
    count); the documents CSV holds one row per document link, so the
    archive is queryable without re-parsing nested JSON. The summary
    reports raw/skipped/merged counts, total documents, schedules with
    no documents, and the posted-date range over parseable ISO dates.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "solicitations.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SOLICITATION_CSV_COLUMNS))
        writer.writeheader()
        for solicitation in parsed.solicitations:
            writer.writerow(solicitation.to_row())

    documents_path = out / "solicitation_documents.csv"
    with documents_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DOCUMENT_CSV_COLUMNS))
        writer.writeheader()
        for solicitation in parsed.solicitations:
            for document in solicitation.documents:
                writer.writerow(document.to_row(solicitation.schedule))

    dates = [
        parsed_date
        for item in parsed.solicitations
        if (parsed_date := _parse_iso_date(item.posted_date)) is not None
    ]
    without_documents = sum(1 for item in parsed.solicitations if not item.documents)
    lines = [
        "# GSA Legacy Schedule Solicitations Summary",
        "",
        f"- **Raw rows**: {parsed.raw_rows}",
        f"- **Unique schedules**: {len(parsed.solicitations)}",
        f"- **Skipped rows (no schedule)**: {parsed.skipped_rows}",
        f"- **Merged rows (duplicate schedule)**: {parsed.merged_rows}",
        f"- **Dropped documents (missing name or URL)**: {parsed.dropped_documents}",
        f"- **Total documents**: {parsed.total_documents}",
        f"- **Schedules with no documents**: {without_documents}",
    ]
    if dates:
        lines.append(
            f"- **Posted-date range**: {min(dates).isoformat()} to {max(dates).isoformat()}"
        )
    summary_path = out / "solicitations_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [csv_path, documents_path, summary_path]


def analyze_solicitations(
    cfg: Config,
    *,
    input_path: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> list[Path]:
    """Load, parse, and report saved solicitation JSON.

    With no ``input_path``, the ``<root>/solicitations/`` directory is
    used (index plus per-schedule files, if present). Reports land in
    ``<root>/output/solicitations/`` unless ``output_dir`` is given.
    """
    if input_path is not None:
        resolved = Path(input_path)
        if not resolved.exists():
            raise FileNotFoundError(f"Solicitation input not found: {resolved}")
    else:
        resolved = cfg.root / cfg.solicitations.input_dirname
        if not resolved.exists():
            raise FileNotFoundError(
                f"No solicitation JSON found under {resolved}. "
                "Pass --input, or place the saved spider output there."
            )
    parsed = parse_solicitations(load_solicitations(resolved))
    out = (
        Path(output_dir)
        if output_dir is not None
        else cfg.paths.output / cfg.solicitations.output_dirname
    )
    return write_solicitations_report(parsed, out)

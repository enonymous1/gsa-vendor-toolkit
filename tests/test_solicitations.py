"""Tests for the ss-gsa fold-in: solicitation parsing, merging, and CLI."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from vendors_toolkit import cli
from vendors_toolkit.analysis.solicitations import (
    DOCUMENT_CSV_COLUMNS,
    SOLICITATION_CSV_COLUMNS,
    load_solicitations,
    parse_solicitations,
    write_solicitations_report,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample-data" / "solicitations" / "solicitations_sample.json"


def _rows() -> list:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_parses_to_three_schedules_with_merged_documents():
    parsed = parse_solicitations(_rows())
    assert parsed.raw_rows == 5
    assert parsed.skipped_rows == 1
    assert parsed.merged_rows == 1
    assert parsed.dropped_documents == 2
    assert [item.schedule for item in parsed.solicitations] == ["900", "901", "902"]
    # Duplicate row merged: doc 02 deduplicated, doc 03 added, first title kept.
    first = parsed.solicitations[0]
    assert first.title == "Fictional Professional Services"
    assert [doc.name for doc in first.documents] == [
        "01 - Solicitation",
        "02 - Price Proposal Template",
        "03 - Past Performance Evaluation",
    ]
    # Non-breaking spaces in the original status become plain spaces.
    assert first.status == "EXAMPLE-1-000001-A Refresh # 1"
    assert parsed.total_documents == 3


def test_parse_skips_non_dict_rows_and_blank_schedules():
    parsed = parse_solicitations(
        [
            "not a row",
            {"schedule": "   ", "title": "Blank schedule"},
            {"schedule": "KEEP-1", "title": "  Spaced title  "},
        ]
    )
    assert parsed.skipped_rows == 2
    assert [item.schedule for item in parsed.solicitations] == ["KEEP-1"]
    assert parsed.solicitations[0].title == "Spaced title"


def test_csv_writer_fixed_headers_one_row_per_schedule_and_document(tmp_path):
    parsed = parse_solicitations(_rows())
    paths = write_solicitations_report(parsed, tmp_path)
    csv_path = tmp_path / "solicitations.csv"
    assert paths[0] == csv_path
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(SOLICITATION_CSV_COLUMNS)
    assert [row["schedule"] for row in rows] == ["900", "901", "902"]
    assert [row["document_count"] for row in rows] == ["3", "0", "0"]
    with (tmp_path / "solicitation_documents.csv").open(newline="", encoding="utf-8") as handle:
        doc_rows = list(csv.DictReader(handle))
    assert list(doc_rows[0].keys()) == list(DOCUMENT_CSV_COLUMNS)
    assert len(doc_rows) == 3
    assert all(row["schedule"] == "900" for row in doc_rows)
    summary = (tmp_path / "solicitations_summary.md").read_text(encoding="utf-8")
    assert "Unique schedules**: 3" in summary
    assert "Merged rows (duplicate schedule)**: 1" in summary
    assert "Posted-date range**: 2024-01-15 to 2024-03-01" in summary


def test_loader_handles_concatenated_arrays_like_real_index(tmp_path):
    # The real ss-gsa index.json is two JSON arrays back to back.
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps([{"schedule": "A", "documents": []}])
        + json.dumps([{"schedule": "B", "documents": []}]),
        encoding="utf-8",
    )
    rows = load_solicitations(path)
    parsed = parse_solicitations(rows)
    assert [item.schedule for item in parsed.solicitations] == ["A", "B"]


def test_loader_directory_merges_index_row_with_per_schedule_file(tmp_path):
    (tmp_path / "index.json").write_text(
        json.dumps([{"schedule": "700", "title": "Index title", "documents": []}]),
        encoding="utf-8",
    )
    (tmp_path / "700.json").write_text(
        json.dumps(
            {
                "schedule": "700",
                "title": "Index title",
                "documents": [{"name": "Doc", "url": "https://example.com/doc"}],
            }
        ),
        encoding="utf-8",
    )
    parsed = parse_solicitations(load_solicitations(tmp_path))
    assert len(parsed.solicitations) == 1
    assert parsed.merged_rows == 1
    assert len(parsed.solicitations[0].documents) == 1


def test_cli_solicitations_offline_input(tmp_path):
    out = tmp_path / "sol"
    rc = cli.main(
        ["--root", str(tmp_path), "solicitations", "--input", str(SAMPLE), "--output", str(out)]
    )
    assert rc == 0
    assert (out / "solicitations.csv").is_file()
    assert (out / "solicitation_documents.csv").is_file()
    assert (out / "solicitations_summary.md").is_file()
    with (out / "solicitations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3


def test_cli_solicitations_runs_once_with_all_variants(tmp_path):
    out = tmp_path / "sol"
    rc = cli.main(
        [
            "--root",
            str(tmp_path),
            "--variant",
            "all",
            "solicitations",
            "--input",
            str(SAMPLE),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    with (out / "solicitations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3  # not doubled by the two variants


def test_cli_solicitations_needs_input(tmp_path):
    rc = cli.main(["--root", str(tmp_path), "solicitations"])
    assert rc == 1

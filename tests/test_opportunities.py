"""Tests for the mp-sam fold-in: opportunity parsing, CSV, and CLI."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from vendors_toolkit import cli
from vendors_toolkit.analysis.opportunities import (
    OPPORTUNITY_CSV_COLUMNS,
    parse_opportunities,
    write_opportunities_report,
)
from vendors_toolkit.integrations.samgov import SamGovClient

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample-data" / "opportunities" / "sam_opportunities_sample.json"


def _payload() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_sample_payload_parses_to_three_unique_opportunities():
    parsed = parse_opportunities(_payload())
    assert parsed.raw_rows == 5
    assert parsed.skipped_rows == 1
    assert parsed.duplicate_rows == 1
    assert [o.notice_id for o in parsed.opportunities] == [
        "SAMPLE-0001",
        "SAMPLE-0002",
        "SAMPLE-0003",
    ]
    # First occurrence wins on the duplicate, not the duplicate's title.
    assert parsed.opportunities[0].title == "Fictional IT support services"
    # naicsCodes list fallback, and nulls normalize to None.
    assert parsed.opportunities[1].naics_code == "541512"
    assert parsed.opportunities[2].title is None
    assert parsed.opportunities[2].agency is None


def test_parse_rejects_missing_or_non_list_container():
    with pytest.raises(ValueError, match="opportunitiesData"):
        parse_opportunities({"totalRecords": 0})
    with pytest.raises(ValueError, match="opportunitiesData"):
        parse_opportunities({"opportunitiesData": {"noticeId": "X"}})
    with pytest.raises(ValueError, match="JSON object"):
        parse_opportunities(["not", "an", "object"])  # type: ignore[arg-type]


def test_parse_skips_non_dict_rows_and_blank_notice_ids():
    parsed = parse_opportunities(
        {
            "opportunitiesData": [
                "not a row",
                {"noticeId": "   "},
                {"noticeId": "KEEP-1", "title": "  Spaced title  "},
            ]
        }
    )
    assert parsed.skipped_rows == 2
    assert [o.notice_id for o in parsed.opportunities] == ["KEEP-1"]
    assert parsed.opportunities[0].title == "Spaced title"


def test_csv_writer_fixed_header_one_row_per_notice(tmp_path):
    parsed = parse_opportunities(_payload())
    paths = write_opportunities_report(parsed, tmp_path)
    csv_path = tmp_path / "opportunities.csv"
    assert paths[0] == csv_path
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(OPPORTUNITY_CSV_COLUMNS)
    assert [row["notice_id"] for row in rows] == [
        "SAMPLE-0001",
        "SAMPLE-0002",
        "SAMPLE-0003",
    ]
    summary = (tmp_path / "opportunities_summary.md").read_text(encoding="utf-8")
    assert "Unique opportunities**: 3" in summary
    assert "Duplicate rows dropped**: 1" in summary


def test_cli_opportunities_offline_input(tmp_path):
    out = tmp_path / "opp"
    rc = cli.main(
        ["--root", str(tmp_path), "opportunities", "--input", str(SAMPLE), "--output", str(out)]
    )
    assert rc == 0
    assert (out / "opportunities.csv").is_file()
    assert (out / "opportunities_summary.md").is_file()
    with (out / "opportunities.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3


def test_cli_opportunities_needs_filter_or_input(tmp_path):
    rc = cli.main(["--root", str(tmp_path), "opportunities"])
    assert rc == 1


def test_cli_opportunities_api_without_key_returns_1(monkeypatch, tmp_path):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    rc = cli.main(["--root", str(tmp_path), "opportunities", "--keywords", "IT services"])
    assert rc == 1


def test_cli_opportunities_api_runs_once_with_all_variants(monkeypatch, tmp_path):
    """One API call per invocation, like the sam stage (daily budget)."""
    monkeypatch.setenv("SAM_API_KEY", "KEY-123")
    calls = []

    def fake_search(self, *, keywords=None, naics=None, state=None, limit=10):
        calls.append((keywords, naics, state, limit))
        return _payload()

    monkeypatch.setattr(SamGovClient, "search_opportunities", fake_search)
    out = tmp_path / "opp"
    rc = cli.main(
        [
            "--root",
            str(tmp_path),
            "--variant",
            "all",
            "opportunities",
            "--keywords",
            "IT services",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert calls == [("IT services", None, None, 10)]
    assert (out / "opportunities.csv").is_file()

"""Tests for the vendors-toolkit CLI surface."""

from __future__ import annotations

import pytest

from vendors_toolkit import cli


def test_parser_has_all_stages():
    parser = cli.build_parser()
    args = parser.parse_args(["--root", "/tmp/x", "--variant", "54151S", "metrics"])
    assert args.stage == "metrics"
    assert args.root == "/tmp/x"
    assert args.variant == "54151S"


def test_parser_stage_specific_args():
    parser = cli.build_parser()
    args = parser.parse_args(["filter", "--states", "VA", "DC", "--sin", "54151S"])
    assert args.states == ["VA", "DC"]
    assert args.sin == "54151S"
    args = parser.parse_args(["download", "--limit", "10", "--workers", "4"])
    assert args.limit == 10 and args.workers == 4


def test_parser_rejects_bad_variant():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--variant", "nope", "metrics"])


def test_main_dispatches_to_stage(monkeypatch, tmp_path):
    called = {}

    def fake_stage(cfg, variant, args):
        called["stage"] = (variant.sin, args.stage)

    monkeypatch.setitem(cli.STAGE_FUNCS, "metrics", fake_stage)
    rc = cli.main(["--root", str(tmp_path), "--variant", "541611", "metrics"])
    assert rc == 0
    assert called["stage"] == ("541611", "metrics")


def test_main_runs_all_variants_by_default(monkeypatch, tmp_path):
    seen = []

    def fake_stage(cfg, variant, args):
        seen.append(variant.sin)

    monkeypatch.setitem(cli.STAGE_FUNCS, "audit", fake_stage)
    rc = cli.main(["--root", str(tmp_path), "audit", "--states", "VA"])
    assert rc == 0
    assert seen == ["54151S", "541611"]


def test_main_returns_1_on_missing_input(monkeypatch, tmp_path):
    def boom(cfg, variant, args):
        raise FileNotFoundError("nope")

    monkeypatch.setitem(cli.STAGE_FUNCS, "sanitize", boom)
    rc = cli.main(["--root", str(tmp_path), "--variant", "54151S", "sanitize"])
    assert rc == 1


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])
    assert exc.value.code == 0

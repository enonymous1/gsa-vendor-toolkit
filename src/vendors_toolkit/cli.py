"""Command-line interface for the vendors_toolkit pipeline.

One subcommand per pipeline stage; each stage runs the unified engine for the
selected variant(s). Global options select the project root
(``--root``, else the ``VENDORS_ROOT`` env var, else the working directory),
the variant (``--variant 54151S`` / ``541611`` / ``all``), and logging.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from vendors_toolkit import __version__
from vendors_toolkit.analysis.audit import analyze_cardinality, run_audit
from vendors_toolkit.analysis.exports import extract_unique_titles, generate_exports
from vendors_toolkit.analysis.metrics import compute_title_metrics
from vendors_toolkit.config import Config, VariantConfig, default_config
from vendors_toolkit.logging_config import configure_logging
from vendors_toolkit.pipeline.download import download_price_lists
from vendors_toolkit.pipeline.filter import filter_sin
from vendors_toolkit.pipeline.merge import merge_state_price_lists
from vendors_toolkit.pipeline.national import merge_national
from vendors_toolkit.pipeline.organize import organize_price_lists
from vendors_toolkit.pipeline.sanitize import sanitize_vendors
from vendors_toolkit.reporting.dashboard import generate_reports

VARIANTS: tuple[str, str] = ("54151S", "541611")

# (subcommand, help text) -- kept in pipeline order.
STAGES: list[tuple[str, str]] = [
    ("sanitize", "Clean the raw vendor CSV (data_sanitizer + sanitize_541611)."),
    ("download", "Download vendor price lists (download_price_lists + download_541611)."),
    ("organize", "File price lists by State/City (organize_price_lists + organize_541611)."),
    (
        "merge",
        "Merge Excel 'Price List' sheets into master CSVs (merge_price_lists + merge_541611_data).",
    ),
    ("filter", "Filter merged data by SIN (filter_sin_54151s)."),
    ("metrics", "Per-title pricing metrics (analyze_it_pricing + analyze_541611_pricing)."),
    (
        "audit",
        "Audit the vendor dataset + title/SIN cardinality (data_audit + analyze_master_data).",
    ),
    (
        "export",
        "Vendor exports, regional summaries, unique titles "
        "(export_vendors + extract_unique_titles).",
    ),
    ("national", "Build the national master price list (merge_national_it)."),
    (
        "report",
        "HTML dashboards + Markdown executive summaries "
        "(generate_pricing_reports + generate_541611_reports).",
    ),
]


def _stage_sanitize(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    out = sanitize_vendors(cfg, variant, input_path=args.input, output_path=args.output)
    print(f"[{variant.sin}] sanitized vendor CSV -> {out}")


def _stage_download(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    manifest = download_price_lists(cfg, variant, limit=args.limit, max_workers=args.workers)
    print(f"[{variant.sin}] downloads complete; manifest -> {manifest}")


def _stage_organize(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    summary = organize_price_lists(cfg, variant)
    print(
        f"[{variant.sin}] organized {summary.moved} files "
        f"({summary.errors} errors) -> {summary.target_root}"
    )


def _stage_merge(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    paths = merge_state_price_lists(cfg, variant, states=args.states)
    print(f"[{variant.sin}] merged {len(paths)} state master file(s)")


def _stage_filter(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    paths = filter_sin(cfg, variant, states=args.states, target_sin=args.sin)
    print(f"[{variant.sin}] filtered {len(paths)} state file(s)")


def _stage_metrics(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    paths = compute_title_metrics(cfg, variant, states=args.states)
    print(f"[{variant.sin}] wrote {len(paths)} metrics file(s)")


def _stage_audit(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    summary = run_audit(cfg, cfg.paths.raw / variant.sanitized_csv)
    reports = analyze_cardinality(cfg, variant, states=args.states)
    print(f"[{variant.sin}] audit summary -> {summary}")
    for report in reports:
        print(
            f"[{variant.sin}] {report.region}: {report.unique_titles} titles "
            f"({report.total_rows} rows)"
        )


def _stage_export(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    base = generate_exports(cfg, variant)
    titles_dir = extract_unique_titles(cfg, variant, states=args.states)
    print(f"[{variant.sin}] exports -> {base}; unique titles -> {titles_dir}")


def _stage_national(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    try:
        path = merge_national(cfg, variant)
    except ValueError:
        print(f"[{variant.sin}] national merge not configured for this variant; skipped")
        return
    if path is None:
        print(f"[{variant.sin}] national merge: no data merged")
    else:
        print(f"[{variant.sin}] national master -> {path}")


def _stage_report(cfg: Config, variant: VariantConfig, args: argparse.Namespace) -> None:
    paths = generate_reports(cfg, variant, states=args.states)
    print(f"[{variant.sin}] wrote {len(paths)} dashboard(s)")


STAGE_FUNCS: dict[str, Callable[[Config, VariantConfig, argparse.Namespace], None]] = {
    "sanitize": _stage_sanitize,
    "download": _stage_download,
    "organize": _stage_organize,
    "merge": _stage_merge,
    "filter": _stage_filter,
    "metrics": _stage_metrics,
    "audit": _stage_audit,
    "export": _stage_export,
    "national": _stage_national,
    "report": _stage_report,
}


def _add_states_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--states",
        nargs="+",
        default=None,
        help="States to process (default: the variant's configured state list).",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with one subcommand per pipeline stage."""
    parser = argparse.ArgumentParser(
        prog="vendors-toolkit",
        description="GSA vendor price-list pipeline: download, organize, merge, "
        "filter, analyze, and report.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--root",
        default=None,
        help="Project root (data directory). Defaults to $VENDORS_ROOT, "
        "else the current working directory.",
    )
    parser.add_argument(
        "--variant",
        choices=[*VARIANTS, "all"],
        default="all",
        help="Which pipeline variant to run (default: all).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Console log level (default: $VENDORS_LOG_LEVEL, else INFO).",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Write a rotating DEBUG log file into this directory.",
    )
    subparsers = parser.add_subparsers(dest="stage", required=True, metavar="stage")

    stage_parsers: dict[str, argparse.ArgumentParser] = {}
    for name, help_text in STAGES:
        stage_parser = subparsers.add_parser(name, help=help_text, description=help_text)
        stage_parser.set_defaults(stage=name)
        stage_parsers[name] = stage_parser

    sanitize_p = stage_parsers["sanitize"]
    sanitize_p.add_argument("--input", default=None, help="Raw vendor CSV (default: per-variant).")
    sanitize_p.add_argument("--output", default=None, help="Sanitized CSV destination.")

    download_p = stage_parsers["download"]
    download_p.add_argument(
        "--limit", type=int, default=None, help="Max downloads (default: none)."
    )
    download_p.add_argument("--workers", type=int, default=None, help="Thread pool size.")

    for stage in ("merge", "filter", "metrics", "audit", "export", "report"):
        _add_states_argument(stage_parsers[stage])

    filter_p = stage_parsers["filter"]
    filter_p.add_argument("--sin", default=None, help="SIN to keep (default: the variant's SIN).")

    return parser


def _selected_variants(cfg: Config, name: str) -> list[VariantConfig]:
    if name == "all":
        return [cfg.variants[v] for v in VARIANTS]
    return [cfg.variants[name]]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``vendors-toolkit`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(level=args.log_level, log_dir=args.log_dir)

    cfg = default_config(root=args.root)
    run_stage = STAGE_FUNCS[args.stage]
    try:
        for variant in _selected_variants(cfg, args.variant):
            run_stage(cfg, variant, args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error in stage '{args.stage}': {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

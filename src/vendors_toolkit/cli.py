"""Command-line interface for the vendors_toolkit pipeline.

Phase 1: skeleton only. Each subcommand parses its arguments and reports that the
stage is not yet implemented; the real engines land in later phases. This keeps
the CLI surface stable while the package is built out one module at a time.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from vendors_toolkit import __version__

# (subcommand, help text, originating script(s)) -- kept in pipeline order.
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
    ("audit", "Audit the vendor dataset (data_audit)."),
    (
        "export",
        "Vendor exports, regional summaries, unique titles "
        "(export_vendors + extract_unique_titles + analyze_master_data).",
    ),
    ("national", "Build the national IT master price list (merge_national_it)."),
    (
        "report",
        "HTML dashboards + Markdown executive summaries "
        "(generate_pricing_reports + generate_541611_reports).",
    ),
]


def _not_implemented(stage: str) -> int:
    """Report that a pipeline stage is a Phase 1 stub and exit non-zero."""
    print(
        f"Stage '{stage}' is not implemented yet (Phase 1 CLI skeleton).",
        file=sys.stderr,
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with one subcommand per pipeline stage."""
    parser = argparse.ArgumentParser(
        prog="vendors-toolkit",
        description="GSA vendor price-list pipeline: download, organize, merge, "
        "filter, analyze, and report.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="stage", required=True, metavar="stage")

    for name, help_text in STAGES:
        stage_parser = subparsers.add_parser(name, help=help_text, description=help_text)
        stage_parser.set_defaults(stage=name)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``vendors-toolkit`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return _not_implemented(args.stage)


if __name__ == "__main__":
    raise SystemExit(main())

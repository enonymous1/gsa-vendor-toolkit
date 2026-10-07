"""Centralized configuration for vendors_toolkit.

Every hardcoded value harvested from the original scripts lives here: the
filesystem layout, the two per-SIN pipeline variants (54151S IT vs 541611
management consulting), and the downloader / organizer / merger / metrics /
audit / report / export knobs. Engines take a :class:`Config` instead of
reaching for module-level constants, so behavior can be overridden per run and
tested without touching the real data layout.

Where the original script twins disagreed (retries, timeouts, copy-vs-move,
sheet matching, ...), the variant that behavior came from is noted and the
original behavior is preserved per variant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

PROJECT_ROOT_ENV_VAR = "VENDORS_ROOT"
LOG_LEVEL_ENV_VAR = "VENDORS_LOG_LEVEL"

OrganizeMode = Literal["move", "copy"]
SheetMatch = Literal["exact", "contains"]


def resolve_project_root(explicit: Path | str | None = None) -> Path:
    """Resolve the data root the pipeline reads from and writes to.

    The originals assumed the repo checkout *was* the data root (``src/`` lived
    one level below it). The installed package no longer knows where the data
    lives, so the root is now explicit: a caller-provided path, else the
    ``VENDORS_ROOT`` environment variable, else the current working directory.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get(PROJECT_ROOT_ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


@dataclass(frozen=True)
class Paths:
    """Filesystem layout, rooted at the configured project root."""

    root: Path

    @property
    def raw(self) -> Path:
        """Raw vendor CSV snapshots (``ext_res/``)."""
        return self.root / "ext_res"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def summaries(self) -> Path:
        return self.output / "summaries"

    @property
    def logs(self) -> Path:
        return self.output / "logs"

    @property
    def column_selections(self) -> Path:
        return self.output / "column_selections"

    @property
    def merged_national(self) -> Path:
        return self.output / "merged_national"

    def downloads(self, dirname: str) -> Path:
        """A named directory under ``output/downloads/``."""
        return self.output / "downloads" / dirname

    def variant_dir(self, dirname: str) -> Path:
        """A named directory directly under ``output/``."""
        return self.output / dirname


@dataclass(frozen=True)
class DownloadConfig:
    """Threaded price-list downloader knobs."""

    max_retries: int = 3
    timeout_seconds: int = 20
    retry_sleep_seconds: float = 1.0
    max_workers: int = 10
    chunk_size: int = 8192
    default_extension: str = ".xlsx"
    # (marker, excluded_marker, extension): first match wins, checked in order.
    # Mirrors the originals' "default .xlsx, sniff the URL" logic.
    extension_rules: tuple[tuple[str, str | None, str], ...] = (
        (".pdf", None, ".pdf"),
        (".xls", ".xlsx", ".xls"),
        (".doc", None, ".doc"),
    )
    manifest_save_every: int | None = 10  # None: write the manifest once at the end
    safe_vendor_max_length: int | None = None  # None: no truncation


@dataclass(frozen=True)
class OrganizeConfig:
    """State/City file organizer knobs shared by both variants."""

    unknown_state: str = "UNKNOWN_STATE"
    unknown_city: str = "UNKNOWN_CITY"


@dataclass(frozen=True)
class MergeConfig:
    """Excel 'Price List' sheet merger knobs."""

    sheet_name: str = "price list"  # matched case-insensitively after stripping
    sheet_match: SheetMatch = "exact"
    excel_row_limit: int = 1_000_000


@dataclass(frozen=True)
class MetricsConfig:
    """Per-title pricing-metrics knobs."""

    price_column: str = "GSA Price with IFF  - as of price list generation date"
    description_join_limit: int = 5000
    excel_cell_limit: int = 32000
    national_display_min_count: int = 2  # originals filtered ``Count > 1``
    csv_low_memory: bool = False


@dataclass(frozen=True)
class AuditConfig:
    """Data-audit knobs."""

    renamed_columns: dict[str, str] = field(
        default_factory=lambda: {
            "Unnamed: 39": "Has_T_and_C_Flag",
            "Unnamed: 40": "Has_Price_List_Flag",
        }
    )
    skip_columns: tuple[str, ...] = (
        "Vendor",
        "Address 1",
        "Address 2",
        "Phone",
        "Email",
        "URL",
        "SAM UEI",
        "Contact #",
        "T&Cs",
        "Price List",
        "View Catalog",
        "Zip",
    )
    max_unique_values: int = 150
    top_cities: int = 15
    top_titles: int = 20
    top_sins: int = 5
    summary_filename: str = "audit_summary.md"


@dataclass(frozen=True)
class ReportConfig:
    """HTML dashboard knobs (CDN assets, description sampling)."""

    jquery_url: str = "https://code.jquery.com/jquery-3.7.1.min.js"
    datatables_css_url: str = "https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css"
    datatables_js_url: str = "https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"
    font_url: str = "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
    description_sample_limit: int = 5


@dataclass(frozen=True)
class ExportConfig:
    """Vendor-export / regional-summary knobs."""

    socioeconomic_markers: tuple[str, ...] = (
        "Small Business",
        "Owned",
        "8(a)",
        "Hub Zone",
        "HUBZone",
    )
    top_cities: int = 10


@dataclass(frozen=True)
class VariantDirs:
    """Per-variant output directory names (all relative to ``output/``)."""

    downloads: str = "price_lists"
    by_region: str = "price_lists_by_region"
    analysis: str = "merged"
    filtered: str = "merged_filtered"
    metrics: str = "it_title_analysis"
    reports: str = "reports"
    titles: str = "unique_titles"


@dataclass(frozen=True)
class VariantConfig:
    """Everything that differs between the 54151S and 541611 pipelines."""

    sin: str
    display_name: str
    states: tuple[str, ...]
    shard_states: tuple[str, ...]  # states with on-disk shards ("National" is derived)
    raw_csv: str  # dated snapshot name under ext_res/
    sanitized_csv: str  # sanitized output name under ext_res/
    manifest_filename: str  # download manifest name under output/summaries/
    manifest_resume: bool = True  # merge with an existing manifest, skipping successes
    manifest_columns: tuple[str, ...] | None = (
        "Vendor",
        "Contact #",
        "Price List",
        "Download_Status",
        "Last_Error",
    )  # None: write every column
    sanitize_category_filter: str | None = None  # e.g. "541611": pre-filter Category
    price_column_markers: tuple[str, str] = ("GSA Price", "with IFF")
    dirs: VariantDirs = field(default_factory=VariantDirs)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    organize_mode: OrganizeMode = "move"
    organize_extensions: tuple[str, ...] = (".pdf", ".xlsx", ".xls", ".doc")
    organize_progress_every: int = 100
    merge_drop_empty: bool = True
    default_download_limit: int | None = None
    report_page_length: int = 50


@dataclass(frozen=True)
class Config:
    """Top-level configuration: paths, shared knobs, and per-SIN variants."""

    root: Path
    paths: Paths
    download: DownloadConfig = field(default_factory=DownloadConfig)
    organize: OrganizeConfig = field(default_factory=OrganizeConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    variants: dict[str, VariantConfig] = field(default_factory=dict)


def default_config(root: Path | str | None = None) -> Config:
    """Build the default configuration, preserving each original's behavior.

    Variant notes (behavioral drift between the original script twins):
    - 54151S downloader: 3 retries, 20s timeout, 1s sleep, 10 workers, no .doc
      sniffing; 541611 downloader: 2 retries, 15s timeout, 0.5s sleep, 15 workers.
    - 54151S organizer *moves* files and checks (.pdf, .xlsx, .xls); the 541611
      organizer *copies* and also checks .doc, truncating vendor names at 50 chars.
    - 54151S merger drops fully-empty rows/columns; the 541611 merger does not.
    - 54151S dashboards page at 50 rows, 541611 at 25.
    - The 541611 ``__main__`` capped downloads at 3000; 54151S had no cap.
    - 54151S downloads resume from the manifest (5-column subset, saved every 10
      completions); the 541611 downloader never resumed and wrote the full frame
      once at the end.
    - Sheet matching is unified to exact ``"price list"`` (the 54151S behavior);
      the 541611 substring match could merge the wrong sheet.
    """
    resolved = resolve_project_root(root)
    return Config(
        root=resolved,
        paths=Paths(root=resolved),
        variants={
            "54151S": VariantConfig(
                sin="54151S",
                display_name="IT (SIN 54151S)",
                states=("VA", "DC", "National"),
                shard_states=("VA", "DC"),
                raw_csv="2026_02_12_04_10_24.csv",
                sanitized_csv="vendors_sanitized.csv",
                manifest_filename="download_manifest.csv",
                price_column_markers=("GSA Price", "with IFF"),
                download=DownloadConfig(
                    extension_rules=(
                        (".pdf", None, ".pdf"),
                        (".xls", ".xlsx", ".xls"),
                    )
                ),
                organize_mode="move",
                organize_extensions=(".pdf", ".xlsx", ".xls"),
                organize_progress_every=100,
                merge_drop_empty=True,
                default_download_limit=None,
                report_page_length=50,
            ),
            "541611": VariantConfig(
                sin="541611",
                display_name="Management Consulting (NAICS 541611)",
                states=("VA", "DC", "MD", "National"),
                shard_states=("VA", "DC", "MD"),
                raw_csv="2026_03_02_08_18_31.csv",
                sanitized_csv="vendors_541611_sanitized.csv",
                manifest_filename="download_541611_manifest.csv",
                manifest_resume=False,
                manifest_columns=None,
                sanitize_category_filter="541611",
                price_column_markers=("GSA", "Price"),
                dirs=VariantDirs(
                    downloads="541611_price_lists",
                    by_region="541611_by_region",
                    analysis="541611_analysis",
                    metrics="541611_metrics",
                    reports="541611_reports",
                ),
                download=DownloadConfig(
                    max_retries=2,
                    timeout_seconds=15,
                    retry_sleep_seconds=0.5,
                    max_workers=15,
                    manifest_save_every=None,
                    safe_vendor_max_length=50,
                ),
                organize_mode="copy",
                organize_extensions=(".pdf", ".xlsx", ".xls", ".doc"),
                organize_progress_every=200,
                merge_drop_empty=False,
                default_download_limit=3000,
                report_page_length=25,
            ),
        },
    )

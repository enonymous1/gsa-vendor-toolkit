"""Unified State/City price-list organizer.

Merges ``organize_price_lists.py`` and ``organize_541611.py``. The behavioral
drift between the originals -- ``shutil.move`` vs ``shutil.copy2``, the probed
extension lists, vendor-name truncation, and progress cadence -- is captured in
:class:`~vendors_toolkit.config.VariantConfig`.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import is_missing
from vendors_toolkit.pipeline.download import download_filename

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrganizeSummary:
    """Outcome of organizing one variant's downloaded price lists."""

    moved: int
    errors: int
    target_root: Path


def _normalize_state(value: object, unknown: str) -> str:
    return str(value).strip().upper() if not is_missing(value) else unknown


def _normalize_city(value: object, unknown: str) -> str:
    if is_missing(value):
        return unknown
    return "".join(c if c.isalnum() or c == " " else "_" for c in str(value).strip())


def organize_price_lists(
    cfg: Config,
    variant: VariantConfig,
    *,
    sanitized_path: Path | str | None = None,
) -> OrganizeSummary:
    """File downloaded price lists into ``<state>/<city>/`` directories.

    Returns an :class:`OrganizeSummary` with the moved/copied count, error
    count, and target root.

    Raises:
        FileNotFoundError: If the sanitized vendor CSV or the download
            directory does not exist.
    """
    data_path = (
        Path(sanitized_path)
        if sanitized_path is not None
        else cfg.paths.raw / variant.sanitized_csv
    )
    if not data_path.exists():
        logger.error("Sanitized file not found: %s", data_path)
        raise FileNotFoundError(f"Sanitized file not found: {data_path}")

    source_dir = cfg.paths.downloads(variant.dirs.downloads)
    if not source_dir.exists():
        logger.error("Source directory does not exist: %s", source_dir)
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    target_root = cfg.paths.downloads(variant.dirs.by_region)

    df = pd.read_csv(data_path, dtype={"Contact #": str})
    df = df[df["Price List"].notna()].copy()
    logger.info("Found %d vendors with price lists to organize...", len(df))

    verb = "moved" if variant.organize_mode == "move" else "copied"
    moved = 0
    errors = 0
    for _, row in df.iterrows():
        vendor = str(row["Vendor"]).strip()
        contact = str(row["Contact #"]).strip()
        state = _normalize_state(row["State"], cfg.organize.unknown_state)
        city = _normalize_city(row["City"], cfg.organize.unknown_city)

        found: str | None = None
        for ext in variant.organize_extensions:
            filename = download_filename(
                vendor, contact, ext, variant.download.safe_vendor_max_length
            )
            if (source_dir / filename).exists():
                found = filename
                break
        if found is None:
            continue

        target_dir = target_root / state / city
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if variant.organize_mode == "move":
                shutil.move(source_dir / found, target_dir / found)
            else:
                shutil.copy2(source_dir / found, target_dir / found)
            moved += 1
            if moved % variant.organize_progress_every == 0:
                logger.info("Progress: organized %d files...", moved)
        except Exception as exc:
            logger.warning(
                "Error %s %s: %s", "moving" if verb == "moved" else "copying", found, exc
            )
            errors += 1

    logger.info(
        "Organization complete: %d %s, %d errors. Target: %s",
        moved,
        verb,
        errors,
        target_root,
    )
    return OrganizeSummary(moved=moved, errors=errors, target_root=target_root)

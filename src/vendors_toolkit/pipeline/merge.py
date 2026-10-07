"""Unified Excel price-list merger.

Merges ``merge_price_lists.py`` and ``merge_541611_data.py``. The drift between
the originals is captured in config:

- sheet matching unified to exact ``"price list"`` (the 54151S behavior; the
  541611 substring match could grab the wrong sheet),
- empty row/column dropping: ``VariantConfig.merge_drop_empty``,
- filename metadata columns: ``VariantConfig.merge_filename_metadata``,
- output naming / Excel output: ``merged_filename_template`` / ``merge_write_excel``.
"""

from __future__ import annotations

import glob
import logging
import os
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, SheetMatch, VariantConfig

logger = logging.getLogger(__name__)


def find_price_list_sheet(
    sheet_names: Sequence[str | int], sheet_name: str, match: SheetMatch
) -> str | None:
    """Return the first sheet matching the configured price-list sheet name.

    Non-string sheet names are skipped (the originals assumed strings).
    """
    target = sheet_name.strip().lower()
    for name in sheet_names:
        if not isinstance(name, str):
            continue
        normalized = name.strip().lower()
        if (match == "exact" and normalized == target) or (
            match == "contains" and target in normalized
        ):
            return name
    return None


def _add_metadata(
    df: pd.DataFrame,
    *,
    state: str,
    city: str,
    filename: str,
    filename_metadata: bool,
) -> pd.DataFrame:
    """Tag a workbook's rows with source metadata (541611 also parses the filename)."""
    df["Source_State"] = state
    df["Source_City"] = city
    df["Source_File"] = filename
    if filename_metadata:
        name_part = os.path.splitext(filename)[0]
        if "_" in name_part:
            vendor_part, contract_part = name_part.rsplit("_", 1)
            df["Metadata_Vendor"] = vendor_part
            df["Metadata_Contract"] = contract_part
    return df


def merge_state_price_lists(
    cfg: Config,
    variant: VariantConfig,
    *,
    states: Sequence[str] | None = None,
) -> list[Path]:
    """Merge per-vendor Excel price lists into per-state master CSVs.

    Walks ``output/downloads/<by_region>/<STATE>/<city>/*.xls*``, reads the
    price-list sheet from each workbook, tags source metadata, and concatenates
    into ``output/<analysis>/<merged_filename_template>``.

    Returns the master CSV paths written.
    """
    states = tuple(states) if states is not None else variant.shard_states
    base_dir = cfg.paths.downloads(variant.dirs.by_region)
    output_dir = cfg.paths.variant_dir(variant.dirs.analysis)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for state in states:
        state_dir = base_dir / state.upper()
        if not state_dir.exists():
            logger.warning("Skipping %s: directory not found.", state)
            continue

        logger.info("Processing state: %s...", state)
        all_data: list[pd.DataFrame] = []
        files_processed = 0
        files_skipped = 0

        for city in os.listdir(state_dir):
            city_path = state_dir / city
            if not city_path.is_dir():
                continue
            for file_path in glob.glob(str(city_path / "*.xls*")):
                filename = os.path.basename(file_path)
                try:
                    xl = pd.ExcelFile(file_path)
                    target = find_price_list_sheet(
                        xl.sheet_names, cfg.merge.sheet_name, cfg.merge.sheet_match
                    )
                    if target is None:
                        files_skipped += 1
                        continue
                    df = pd.read_excel(xl, sheet_name=target)
                    df = _add_metadata(
                        df,
                        state=state,
                        city=city,
                        filename=filename,
                        filename_metadata=variant.merge_filename_metadata,
                    )
                    if variant.merge_drop_empty:
                        df = df.dropna(how="all").dropna(axis=1, how="all")
                    all_data.append(df)
                    files_processed += 1
                    logger.debug("  [%d] Added: %s", files_processed, filename)
                except Exception as exc:
                    logger.debug("  Skipping %s: %s", filename, exc)
                    files_skipped += 1

        logger.info(
            "Finished %s: %d files merged, %d skipped.",
            state,
            files_processed,
            files_skipped,
        )
        if not all_data:
            logger.warning("No data found to merge for %s.", state)
            continue

        logger.info("Combining data for %s...", state)
        master_df = pd.concat(all_data, ignore_index=True, sort=False)
        csv_out = output_dir / variant.merged_filename_template.format(state=state)
        master_df.to_csv(csv_out, index=False)

        if variant.merge_write_excel:
            xlsx_out = csv_out.with_suffix(".xlsx")
            if len(master_df) < cfg.merge.excel_row_limit:
                try:
                    master_df.to_excel(xlsx_out, index=False)
                    logger.info("Saved: %s", xlsx_out)
                except Exception as exc:
                    logger.warning("Could not save Excel for %s: %s", state, exc)
            else:
                logger.warning(
                    "%s data too large for Excel (%d rows). Saved CSV only.",
                    state,
                    len(master_df),
                )
        logger.info("Saved: %s (%d rows)", csv_out, len(master_df))
        written.append(csv_out)

    return written

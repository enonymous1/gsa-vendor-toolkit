"""National master merge.

Generalizes ``merge_national_it.py``: the original was IT-specific (hardcoded
54151S category filter, manifest/vendor filenames, and the
``National_IT_Master_Price_List.csv`` output name). The SIN filter and file
locations now come from the variant; only variants with
``national_output_filename`` set support this stage.

Known original quirk, preserved: the State/City lookup here does *not* apply
the organizer's city-name sanitization (and uses ``"UNKNOWN"`` fallbacks
instead of ``"UNKNOWN_STATE"``/``"UNKNOWN_CITY"``), so files filed under
sanitized city names are not found by this stage -- exactly as before.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import is_missing
from vendors_toolkit.pipeline.merge import find_price_list_sheet

logger = logging.getLogger(__name__)


def merge_national(cfg: Config, variant: VariantConfig) -> Path | None:
    """Build the national master price list from successful downloads.

    Joins the download manifest with the vendor catalog, reads the price-list
    sheet from every successfully downloaded workbook, and concatenates into
    ``output/merged_national/<national_output_filename>``.

    Returns the output CSV path, or None when no data was merged.

    Raises:
        ValueError: If the variant has no ``national_output_filename``.
        FileNotFoundError: If the manifest or vendor CSV is missing.
    """
    output_filename = variant.national_output_filename
    if output_filename is None:
        raise ValueError(f"National merge is not configured for variant {variant.sin!r}.")

    manifest_path = cfg.paths.summaries / variant.manifest_filename
    vendors_path = cfg.paths.raw / variant.sanitized_csv
    base_dir = cfg.paths.downloads(variant.dirs.by_region)
    output_dir = cfg.paths.merged_national
    output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_path.exists() or not vendors_path.exists():
        logger.error("Required files not found: %s, %s", manifest_path, vendors_path)
        raise FileNotFoundError(f"Required files not found: {manifest_path}, {vendors_path}")

    logger.info("Loading data catalogs...")
    manifest = pd.read_csv(manifest_path)
    vendors = pd.read_csv(vendors_path)
    manifest["Contact #"] = manifest["Contact #"].astype(str)
    vendors["Contact #"] = vendors["Contact #"].astype(str)

    df_merged = manifest.merge(
        vendors[["Vendor", "Contact #", "Category", "State", "City"]],
        on=["Vendor", "Contact #"],
        how="left",
    )
    it_df = df_merged[
        (df_merged["Download_Status"] == "Success")
        & (df_merged["Category"].str.contains(variant.sin, na=False))
    ].copy()
    logger.info("Found %d successful %s downloads to merge.", len(it_df), variant.sin)

    all_data: list[pd.DataFrame] = []
    files_processed = 0
    files_skipped = 0
    for _, row in it_df.iterrows():
        vendor_safe = "".join(c if c.isalnum() else "_" for c in str(row["Vendor"]))
        contact = str(row["Contact #"])
        state = str(row["State"]).strip().upper() if not is_missing(row["State"]) else "UNKNOWN"
        city = str(row["City"]).strip() if not is_missing(row["City"]) else "UNKNOWN"

        candidate = base_dir / state / city / f"{vendor_safe}_{contact}.xlsx"
        if not candidate.exists():
            # Faithful to the original's str.replace on the full path.
            candidate = Path(str(candidate).replace(".xlsx", ".xls"))
        if not candidate.exists():
            files_skipped += 1
            continue

        try:
            xl = pd.ExcelFile(candidate)
            target = find_price_list_sheet(
                xl.sheet_names, cfg.merge.sheet_name, cfg.merge.sheet_match
            )
            if target is None:
                files_skipped += 1
                continue
            df = pd.read_excel(xl, sheet_name=target)
            df["Source_Vendor"] = row["Vendor"]
            df["Source_Contact_Num"] = row["Contact #"]
            df["Source_State"] = state
            df["Source_City"] = city
            df = df.dropna(how="all").dropna(axis=1, how="all")
            all_data.append(df)
            files_processed += 1
            if files_processed % cfg.merge.national_progress_every == 0:
                logger.info("Processed %d files...", files_processed)
        except Exception as exc:
            logger.debug("Skipping %s: %s", candidate.name, exc)
            files_skipped += 1

    logger.info(
        "Finished merging: %d files processed, %d skipped/missing.",
        files_processed,
        files_skipped,
    )
    if not all_data:
        logger.warning("No data found to merge.")
        return None

    logger.info("Combining all data (this may take a moment)...")
    master_df = pd.concat(all_data, ignore_index=True, sort=False)
    csv_out = output_dir / output_filename
    master_df.to_csv(csv_out, index=False)
    logger.info("Saved national master: %s (%d rows)", csv_out, len(master_df))
    return csv_out

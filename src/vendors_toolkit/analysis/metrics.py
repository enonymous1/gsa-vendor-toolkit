"""Unified per-title pricing metrics.

Merges ``analyze_it_pricing.py`` and ``analyze_541611_pricing.py`` into one
engine. Two deliberate unifications (both documented, both verified):

- Output schema is the richer IT shape for both variants: the 541611 metrics
  gain ``Mode_Price``/``Price_Range`` and the ``*_Price``/``Merged_Descriptions``
  column names. The phase-7 dashboard is built against this single schema.
- Title cleaning is fillna-first for both variants: the IT original turned a
  missing title into the key ``"NONE"`` (``astype(str)`` on NaN); it now
  normalizes to ``""`` like the 541611 original did.

National input handling stays per-variant: IT reads the prebuilt national
master (``metrics_national_from_shards=False``); 541611 concatenates the state
shards on the fly (``metrics_national_from_shards=True``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import (
    clean_title,
    detect_price_column,
    is_missing,
    normalize_title_key,
    to_price_numeric,
)

logger = logging.getLogger(__name__)

METRICS_COLUMNS = [
    "Count",
    "Min_Price",
    "Max_Price",
    "Mean_Price",
    "Median_Price",
    "Mode_Price",
    "Merged_Descriptions",
]


def _series_mode(values: pd.Series) -> float | int:
    """Mode of a price series, NaN when empty (the originals' ``get_mode``).

    Preserves int scalars as ints: the originals returned the raw mode value,
    so an all-integer price column yields ``120`` rather than ``120.0``.
    """
    if values.empty:
        return float("nan")
    modes = values.mode()
    if modes.empty:
        return float("nan")
    mode_value = modes.iloc[0]
    if isinstance(mode_value, (int, np.integer)):
        return int(mode_value)
    return float(mode_value)


def _description_merger(limit: int) -> Callable[[pd.Series], str]:
    """Build the description-merge aggregation: sorted unique values, capped."""

    def merge(values: pd.Series) -> str:
        parts = {str(v).strip() for v in values if not is_missing(v) and str(v).strip()}
        return " | ".join(sorted(parts))[:limit]

    return merge


def _resolve_metrics_input(
    cfg: Config, variant: VariantConfig, analysis_dir: Path, state: str
) -> Path | None:
    """Locate (or build, for 541611 National) the metrics input CSV."""
    if state == "National":
        if variant.metrics_national_from_shards:
            national_csv = analysis_dir / variant.merged_filename_template.format(state="National")
            if not national_csv.exists():
                logger.info("Creating national master list...")
                shards = []
                for shard_state in variant.shard_states:
                    shard_path = analysis_dir / variant.merged_filename_template.format(
                        state=shard_state
                    )
                    if shard_path.exists():
                        shards.append(
                            pd.read_csv(shard_path, low_memory=cfg.metrics.csv_low_memory)
                        )
                if not shards:
                    logger.warning("Skipping National: no state shards found.")
                    return None
                pd.concat(shards, ignore_index=True).to_csv(national_csv, index=False)
            return national_csv
        if variant.national_output_filename is None:
            logger.warning("Skipping National: no national input configured for %s.", variant.sin)
            return None
        national_csv = cfg.paths.merged_national / variant.national_output_filename
        if not national_csv.exists():
            logger.warning("Skipping %s: input file not found.", state)
            return None
        return national_csv

    if variant.metrics_use_filtered_input:
        input_csv = cfg.paths.variant_dir(
            variant.dirs.filtered
        ) / variant.filtered_filename_template.format(state=state, sin=variant.sin)
    else:
        input_csv = analysis_dir / variant.merged_filename_template.format(state=state)
    if not input_csv.exists():
        logger.warning("Skipping %s: input file not found.", state)
        return None
    return input_csv


def compute_title_metrics(
    cfg: Config,
    variant: VariantConfig,
    *,
    states: Sequence[str] | None = None,
) -> list[Path]:
    """Compute per-title pricing metrics for one variant.

    Writes ``output/<metrics>/<metrics_filename_template>`` (CSV plus Excel with
    descriptions capped for cell limits). Returns the CSV paths written.
    """
    states = tuple(states) if states is not None else variant.states
    output_dir = cfg.paths.variant_dir(variant.dirs.metrics)
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir = cfg.paths.variant_dir(variant.dirs.analysis)

    written: list[Path] = []
    for state in states:
        input_csv = _resolve_metrics_input(cfg, variant, analysis_dir, state)
        if input_csv is None:
            continue

        logger.info("Analyzing job title metrics for %s (%s)...", state, variant.sin)
        df = pd.read_csv(input_csv, low_memory=cfg.metrics.csv_low_memory)

        price_col = detect_price_column(
            df.columns, cfg.metrics.price_column, variant.price_column_markers
        )
        if price_col is None:
            logger.warning("No price column found for %s.", state)
            continue
        if "Title" not in df.columns or "Description" not in df.columns:
            logger.error("Required Title/Description columns missing for %s.", state)
            continue

        df["Title_Key"] = normalize_title_key(df["Title"])
        df["Description"] = clean_title(df["Description"])
        df["Price_Numeric"] = to_price_numeric(df[price_col])
        numeric_df = df.dropna(subset=["Price_Numeric"]).copy()

        metrics_df = numeric_df.groupby("Title_Key").agg(
            {
                "Price_Numeric": [
                    "count",
                    "min",
                    "max",
                    "mean",
                    "median",
                    _series_mode,
                ],
                "Description": _description_merger(cfg.metrics.description_join_limit),
            }
        )
        metrics_df.columns = pd.Index(METRICS_COLUMNS)
        metrics_df["Price_Range"] = metrics_df["Max_Price"] - metrics_df["Min_Price"]
        metrics_df = metrics_df.reset_index().sort_values(by="Count", ascending=False)

        csv_out = output_dir / variant.metrics_filename_template.format(state=state)
        metrics_df.to_csv(csv_out, index=False)

        xlsx_out = csv_out.with_suffix(".xlsx")
        try:
            excel_df = metrics_df.copy()
            excel_df["Merged_Descriptions"] = excel_df["Merged_Descriptions"].str.slice(
                0, cfg.metrics.excel_cell_limit
            )
            excel_df.to_excel(xlsx_out, index=False)
            logger.info("Saved metrics to: %s", xlsx_out)
        except Exception as exc:
            logger.warning("Excel save failed for %s: %s", state, exc)

        logger.info("Processed %d unique titles for %s.", len(metrics_df), state)
        written.append(csv_out)

    return written

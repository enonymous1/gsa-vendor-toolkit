"""Generalized SIN filter.

Generalizes ``filter_sin_54151s.py``: the SIN under test defaults to the
variant's SIN and the input/output naming comes from the variant config, so the
same engine serves the 541611 pipeline too.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig

logger = logging.getLogger(__name__)


def filter_sin(
    cfg: Config,
    variant: VariantConfig,
    *,
    states: Sequence[str] | None = None,
    target_sin: str | None = None,
) -> list[Path]:
    """Filter merged master price lists down to one SIN.

    Writes ``output/<filtered>/<filtered_filename_template>`` (CSV, plus Excel
    when under the row limit). Returns the CSV paths written.
    """
    sin = target_sin if target_sin is not None else variant.sin
    states = tuple(states) if states is not None else variant.shard_states
    input_dir = cfg.paths.variant_dir(variant.dirs.analysis)
    output_dir = cfg.paths.variant_dir(variant.dirs.filtered)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for state in states:
        input_csv = input_dir / variant.merged_filename_template.format(state=state)
        if not input_csv.exists():
            logger.warning("Skipping %s: merged file not found.", state)
            continue

        logger.info("Filtering %s for SIN %s...", state, sin)
        df = pd.read_csv(input_csv, low_memory=cfg.metrics.csv_low_memory)
        if "SIN" not in df.columns:
            logger.error("'SIN' column not found in %s file.", state)
            continue

        filtered = df[df["SIN"].astype(str).str.contains(sin, na=False)].copy()
        count, total = len(filtered), len(df)
        logger.info("Found %d rows matching %s (out of %d total).", count, sin, total)

        if count == 0:
            logger.info("No rows found for SIN %s in %s.", sin, state)
            continue

        csv_out = output_dir / variant.filtered_filename_template.format(state=state, sin=sin)
        filtered.to_csv(csv_out, index=False)

        if count < cfg.merge.excel_row_limit:
            xlsx_out = csv_out.with_suffix(".xlsx")
            try:
                filtered.to_excel(xlsx_out, index=False)
                logger.info("Saved: %s", xlsx_out)
            except Exception as exc:
                logger.warning("Excel save failed for %s: %s", state, exc)
        else:
            logger.warning("%s data too large for Excel (%d rows). Saved CSV only.", state, count)

        logger.info("Saved: %s", csv_out)
        written.append(csv_out)

    return written

"""Unified vendor CSV sanitizer.

Merges ``data_sanitizer.py`` and ``sanitize_541611.py``: the only behavioral
difference between the originals was the 541611 pre-filter on the ``Category``
column, which is now ``VariantConfig.sanitize_category_filter``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.mapping import sanitize_frame

logger = logging.getLogger(__name__)


def sanitize_vendors(
    cfg: Config,
    variant: VariantConfig,
    *,
    input_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> Path:
    """Sanitize the raw vendor CSV for one pipeline variant.

    Reads the raw CSV, optionally pre-filters on ``Category``, maps coded
    values through :data:`~vendors_toolkit.data.mapping.GSA_MAP`, and writes
    the sanitized CSV. Returns the output path.

    Raises:
        FileNotFoundError: If the raw input CSV does not exist.
    """
    src = Path(input_path) if input_path is not None else cfg.paths.raw / variant.raw_csv
    dst = Path(output_path) if output_path is not None else cfg.paths.raw / variant.sanitized_csv

    if not src.exists():
        logger.error("Raw file not found at %s", src)
        raise FileNotFoundError(f"Raw file not found: {src}")

    logger.info("Sanitizing %s ...", src)
    df = pd.read_csv(src, low_memory=cfg.metrics.csv_low_memory)

    category_filter = variant.sanitize_category_filter
    if category_filter and "Category" in df.columns:
        logger.info("Filtering for category '%s' ...", category_filter)
        df = df[df["Category"].astype(str).str.contains(category_filter, na=False)].copy()
        logger.info("Found %d vendors after category filter.", len(df))

    sanitized = sanitize_frame(
        df,
        renamed_columns=cfg.audit.renamed_columns,
        skip_columns=cfg.audit.skip_columns,
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    sanitized.to_csv(dst, index=False)
    logger.info("Sanitized source created at: %s", dst)
    return dst

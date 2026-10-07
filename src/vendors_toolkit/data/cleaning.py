"""Title and price cleaning helpers shared by the analysis stages.

These are exact ports of the inline cleaning expressions repeated across
``analyze_it_pricing.py`` and ``analyze_541611_pricing.py``. The pandas call
chains are kept identical to the originals (including ``str.replace`` semantics)
so refactored output stays byte-comparable with the originals.
"""

from __future__ import annotations

import math

import pandas as pd


def is_missing(value: object) -> bool:
    """Scalar missing-value check mirroring ``pd.notnull`` for CSV-loaded cells.

    Written explicitly (instead of ``pd.isna``) so the ``object`` parameter
    type-checks under ``mypy --strict``.
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return value is pd.NA or value is pd.NaT


def clean_title(values: pd.Series) -> pd.Series:
    """Strip whitespace from titles, treating missing values as empty strings."""
    return values.fillna("").astype(str).str.strip()


def normalize_title_key(values: pd.Series) -> pd.Series:
    """Upper-cased, stripped title used as the group-by key (``Title_Key``)."""
    return clean_title(values).str.upper()


def detect_price_column(columns: pd.Index, primary: str, markers: tuple[str, str]) -> str | None:
    """Find the GSA price column: the primary name, else the first column whose
    name contains both fallback markers (the originals' re-detection logic)."""
    if primary in columns:
        return primary
    matches = [col for col in columns if all(m in str(col) for m in markers)]
    return str(matches[0]) if matches else None


def to_price_numeric(values: pd.Series) -> pd.Series:
    """Convert a price column to numeric, coercing ``$``/``,``-formatted strings.

    Mirrors the originals: cast to string, strip ``$`` and commas, then
    ``pd.to_numeric(..., errors="coerce")``. Non-string (already numeric) input
    round-trips through the same chain with an identical result.
    """
    cleaned = values.astype(str).str.replace("$", "").str.replace(",", "").str.strip()
    return pd.to_numeric(cleaned, errors="coerce")

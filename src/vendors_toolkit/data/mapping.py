"""GSA code mapping and DataFrame sanitization.

This module is the single source of truth for ``GSA_MAP`` -- the originals
duplicated it verbatim in ``utils.py`` and ``data_audit.py``. :func:`sanitize_frame`
is a pure, non-mutating port of the original ``sanitize_df``.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping

import pandas as pd

GSA_MAP: dict[str, str] = {
    "s": "Small Business",
    "o": "Other Than Small Business",
    "w": "Women Owned",
    "wo": "Women Owned (WOSB)",
    "ed": "Women Owned (EDWOSB)",
    "v": "Veteran Owned",
    "dv": "Service Disabled Veteran Owned",
    "d": "Small Disadv",
    "8a": "8(a)",
    "8aS": "8(a) Sole Source Pool",
    "h": "HUBZone",
    "to": "Tribally Owned",
    "ai": "American Indian Owned",
    "anc": "Alaskan Native Corporation Owned",
    "nho": "Native Hawaiian Organization Owned",
    "8ajv": "8(a) Joint Venture Eligible",
    "wojv": "Women Owned Joint Venture Eligible",
    "dvjv": "Service Disabled Veteran Owned Joint Venture Eligible",
    "hjv": "HUBZone Joint Venture Eligible",
    "Y": "Yes",
    "N": "No",
}


def _is_missing(value: object) -> bool:
    """Scalar missing-value check mirroring ``pd.notnull`` for CSV-loaded cells.

    Written explicitly (instead of ``pd.isna``) so the ``object`` parameter
    type-checks under ``mypy --strict``.
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return value is pd.NA or value is pd.NaT


def _map_gsa_value(value: object) -> object:
    """Map one raw cell through ``GSA_MAP``; nulls and unmapped values pass through."""
    if _is_missing(value):
        return value
    return GSA_MAP.get(str(value), value)


def sanitize_frame(
    df: pd.DataFrame,
    *,
    renamed_columns: Mapping[str, str],
    skip_columns: Collection[str],
) -> pd.DataFrame:
    """Return a sanitized copy of ``df`` without mutating the input.

    - Renames ambiguous columns (e.g. ``Unnamed: 39`` -> ``Has_T_and_C_Flag``).
    - Maps coded categorical values through :data:`GSA_MAP` for every column
      except the identity/contact columns in ``skip_columns``.
    """
    result: pd.DataFrame = df.rename(columns=dict(renamed_columns))
    result = result.copy()
    for col in result.columns:
        if col in skip_columns:
            continue
        # Elementwise mapping via comprehension (Series.apply's stub overloads
        # reject an (object -> object) callable under --strict).
        mapped = [_map_gsa_value(value) for value in result[col]]
        result[col] = pd.Series(mapped, index=result.index)
    return result

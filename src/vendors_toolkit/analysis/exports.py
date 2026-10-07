"""Vendor exports and unique-title extraction.

``generate_exports`` ports ``export_vendors.py`` (regional CSV exports plus
per-state Markdown summaries); ``extract_unique_titles`` ports
``extract_unique_titles.py`` (per-state JSON title lists plus a summary).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from vendors_toolkit.config import Config, VariantConfig
from vendors_toolkit.data.cleaning import clean_title

logger = logging.getLogger(__name__)


def _default_variant(cfg: Config) -> VariantConfig:
    """The IT variant -- the original export scripts defaulted to its files."""
    return cfg.variants["54151S"]


def _write_regional_summary(
    df: pd.DataFrame, state_code: str, output_dir: Path, se_cols: list[str], top_cities: int
) -> None:
    """Write the per-state Markdown summary (byte-faithful port)."""
    total = len(df)
    pl_count = len(df[df["Has_Price_List_Flag"] == "Yes"])
    pct = (pl_count / total * 100) if total > 0 else 0.0

    lines = [
        f"# Regional Summary: {state_code}",
        f"- **Total Vendors:** {total}",
        f"- **Vendors with Price List:** {pl_count} ({pct:.1f}%)",
        "",
    ]
    if "City" in df.columns:
        lines.append("## Top Cities")
        for city, count in df["City"].value_counts().head(top_cities).items():
            lines.append(f"- {city}: {count}")
    lines.append("")
    lines.append("## Socio-Economic Breakdown (Price List Preferred)")

    pl_df = df[df["Has_Price_List_Flag"] == "Yes"]
    for col in se_cols:
        total_se = int(df[col].count())
        pl_se = int(pl_df[col].count())
        if total_se > 0:
            lines.append(f"- **{col}**: {total_se} total ({pl_se} with Price List)")

    (output_dir / f"summary_{state_code}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_exports(
    cfg: Config,
    variant: VariantConfig | None = None,
    *,
    sanitized_path: Path | str | None = None,
) -> Path:
    """Export vendor CSVs (all/regional/socio-economic) and per-state summaries.

    Returns the output base directory.

    Raises:
        FileNotFoundError: If the sanitized vendor CSV does not exist.
    """
    variant = variant or _default_variant(cfg)
    data_path = (
        Path(sanitized_path)
        if sanitized_path is not None
        else cfg.paths.raw / variant.sanitized_csv
    )
    if not data_path.exists():
        logger.error("Sanitized file not found: %s", data_path)
        raise FileNotFoundError(f"Sanitized file not found: {data_path}")

    df = pd.read_csv(data_path)

    output_base = cfg.paths.output
    dirs = {
        "price_lists": output_base / "price_lists",
        "regional": output_base / "regional",
        "summaries": output_base / "summaries",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    se_cols = [c for c in df.columns if any(m in c for m in cfg.export.socioeconomic_markers)]

    price_list_df = df[df["Has_Price_List_Flag"] == "Yes"]
    price_list_df.to_csv(dirs["price_lists"] / "all_vendors_with_price_list.csv", index=False)
    logger.info("Exported all price list vendors.")

    for state_code in df["State"].dropna().unique():
        state_dir = dirs["regional"] / str(state_code)
        state_dir.mkdir(parents=True, exist_ok=True)

        state_df = df[df["State"] == state_code]
        state_df.to_csv(state_dir / f"all_vendors_{state_code}.csv", index=False)

        state_pl_df = state_df[state_df["Has_Price_List_Flag"] == "Yes"]
        if not state_pl_df.empty:
            state_pl_df.to_csv(state_dir / f"vendors_{state_code}_with_price_list.csv", index=False)

        if state_code in ("VA", "DC") and not state_pl_df.empty:
            se_dir = state_dir / "socio_economic_with_price_list"
            se_dir.mkdir(parents=True, exist_ok=True)
            for col in se_cols:
                subset = state_pl_df[state_pl_df[col].notna()]
                if not subset.empty:
                    safe_col_name = "".join(c if c.isalnum() else "_" for c in col)
                    subset.to_csv(se_dir / f"{state_code}_PL_{safe_col_name}.csv", index=False)

        _write_regional_summary(
            state_df, str(state_code), dirs["summaries"], se_cols, cfg.export.top_cities
        )

    logger.info("Exports and summaries completed in %s.", output_base)
    return output_base


def extract_unique_titles(
    cfg: Config,
    variant: VariantConfig | None = None,
    *,
    states: Sequence[str] | None = None,
) -> Path:
    """Extract per-state unique title JSON lists from the filtered files.

    Returns the output directory. The JSON lists are the contract; the Markdown
    summary header is generalized to the variant's SIN.
    """
    variant = variant or _default_variant(cfg)
    states = tuple(states) if states is not None else variant.shard_states
    input_dir = cfg.paths.variant_dir(variant.dirs.filtered)
    output_dir = cfg.paths.variant_dir(variant.dirs.titles)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = [f"# Unique Titles ({variant.sin})", ""]
    for state in states:
        input_csv = input_dir / variant.filtered_filename_template.format(
            state=state, sin=variant.sin
        )
        if not input_csv.exists():
            logger.warning("Skipping %s: filtered file not found.", state)
            continue

        logger.info("Extracting unique titles for %s...", state)
        df = pd.read_csv(input_csv, low_memory=cfg.metrics.csv_low_memory)
        if "Title" not in df.columns:
            logger.error("'Title' column not found in %s file.", state)
            continue

        unique_titles = clean_title(df["Title"]).unique().tolist()
        unique_titles.sort()

        json_name = variant.unique_titles_template.format(state=state)
        (output_dir / json_name).write_text(json.dumps(unique_titles, indent=4), encoding="utf-8")
        summary.extend(
            [
                f"## {state}",
                f"- **Total Rows**: {len(df)}",
                f"- **Unique Titles**: {len(unique_titles)}",
                f"- **JSON List**: [{json_name}]({json_name})",
                "",
            ]
        )
        logger.info("Found %d unique titles for %s.", len(unique_titles), state)

    (output_dir / "unique_titles_summary.md").write_text("\n".join(summary), encoding="utf-8")
    return output_dir

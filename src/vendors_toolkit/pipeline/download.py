"""Unified threaded price-list downloader.

Merges ``download_price_lists.py`` and ``download_541611.py``. The behavioral
drift between the originals (retries, timeouts, workers, ``.doc`` sniffing,
vendor-name truncation, manifest resume/columns/cadence) is captured in
:class:`~vendors_toolkit.config.VariantConfig` / :class:`~vendors_toolkit.config.DownloadConfig`.

Also fixes a crash in the 54151S original: it built ``{future: row}`` with a
pandas ``Series`` as the dict key, which raises ``TypeError`` (Series is
unhashable) before any download runs. Futures are keyed by the DataFrame index
here, as the working 541611 twin did.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import requests

from vendors_toolkit.config import Config, DownloadConfig, VariantConfig

logger = logging.getLogger(__name__)

DownloadStatus = Literal["Success", "Failed"]


@dataclass(frozen=True)
class DownloadOutcome:
    """Result of a single price-list download attempt."""

    contact: str
    status: DownloadStatus
    error: str


def detect_extension(url: str, cfg: DownloadConfig) -> str:
    """Sniff the file extension from a price-list URL (first rule wins).

    Mirrors the originals' "default ``.xlsx``, sniff the URL" logic, driven by
    ``DownloadConfig.extension_rules``.
    """
    lowered = url.lower()
    for marker, excluded, ext in cfg.extension_rules:
        if marker in lowered and (excluded is None or excluded not in lowered):
            return ext
    return cfg.default_extension


def download_filename(vendor: str, contact: str, ext: str, max_length: int | None) -> str:
    """Build the ``<SafeVendor>_<Contact#><ext>`` filename (shared with organize)."""
    safe = "".join(c if c.isalnum() else "_" for c in vendor.strip())
    if max_length is not None:
        safe = safe[:max_length]
    return f"{safe}_{contact}{ext}"


def _download_one(row: pd.Series, download_dir: Path, cfg: DownloadConfig) -> DownloadOutcome:
    """Download one price list with retries; skips files already on disk."""
    url = str(row["Price List"])
    vendor = str(row["Vendor"]).strip()
    contact = str(row["Contact #"]).strip()

    filename = download_filename(
        vendor, contact, detect_extension(url, cfg), cfg.safe_vendor_max_length
    )
    filepath = download_dir / filename

    if filepath.exists():
        return DownloadOutcome(contact, "Success", "")

    error_msg = ""
    for _ in range(cfg.max_retries):
        try:
            response = requests.get(url, timeout=cfg.timeout_seconds, stream=True)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=cfg.chunk_size):
                        f.write(chunk)
                return DownloadOutcome(contact, "Success", "")
            error_msg = f"HTTP {response.status_code}"
        except Exception as exc:
            error_msg = str(exc)
        time.sleep(cfg.retry_sleep_seconds)

    return DownloadOutcome(contact, "Failed", error_msg)


def _write_manifest(df: pd.DataFrame, path: Path, columns: tuple[str, ...] | None) -> None:
    view = df if columns is None else df[list(columns)]
    view.to_csv(path, index=False)


def download_price_lists(
    cfg: Config,
    variant: VariantConfig,
    *,
    sanitized_path: Path | str | None = None,
    limit: int | None = None,
    max_workers: int | None = None,
) -> Path:
    """Download price lists for one pipeline variant; returns the manifest path.

    Builds (or resumes, per ``variant.manifest_resume``) a manifest tracking
    ``Download_Status``/``Last_Error`` per vendor, then downloads every pending
    entry with a thread pool.

    Raises:
        FileNotFoundError: If the sanitized vendor CSV does not exist.
    """
    data_path = (
        Path(sanitized_path)
        if sanitized_path is not None
        else cfg.paths.raw / variant.sanitized_csv
    )
    if not data_path.exists():
        logger.error("Sanitized file not found: %s", data_path)
        raise FileNotFoundError(f"Sanitized file not found: {data_path}")

    dl = variant.download
    workers = max_workers if max_workers is not None else dl.max_workers
    effective_limit = variant.default_download_limit if limit is None else limit

    download_dir = cfg.paths.downloads(variant.dirs.downloads)
    download_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cfg.paths.summaries / variant.manifest_filename
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path, dtype={"Contact #": str})
    to_download = df[df["Price List"].notna()].copy()

    if variant.manifest_resume and manifest_path.exists():
        manifest_df = pd.read_csv(manifest_path, dtype={"Contact #": str})
        to_download = to_download.merge(
            manifest_df[["Contact #", "Download_Status", "Last_Error"]],
            on="Contact #",
            how="left",
        )
        to_download["Download_Status"] = (
            to_download["Download_Status"].fillna("Pending").astype(str)
        )
        to_download["Last_Error"] = to_download["Last_Error"].fillna("").astype(str)
        stats = to_download["Download_Status"].value_counts()
        logger.info(
            "Current progress: %d successes, %d failures, %d pending.",
            stats.get("Success", 0),
            stats.get("Failed", 0),
            stats.get("Pending", 0),
        )
    else:
        to_download["Download_Status"] = "Pending"
        to_download["Last_Error"] = ""

    if effective_limit:
        pending = to_download[to_download["Download_Status"] != "Success"].head(effective_limit)
        logger.info("Limiting download to first %d pending entries.", effective_limit)
    else:
        pending = to_download[to_download["Download_Status"] != "Success"]

    total = len(pending)
    if total == 0:
        logger.info("All files already downloaded according to manifest.")
        return manifest_path

    logger.info(
        "Starting/resuming concurrent download of %d price lists (workers: %d)...",
        total,
        workers,
    )
    completed = 0
    # Keyed by DataFrame index (ints) -- keying by the row Series itself crashes,
    # as the 54151S original demonstrated.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_download_one, row, download_dir, dl): idx
            for idx, row in pending.iterrows()
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            outcome = future.result()
            to_download.loc[idx, "Download_Status"] = outcome.status
            to_download.loc[idx, "Last_Error"] = outcome.error
            completed += 1
            if outcome.status == "Success":
                logger.debug("[%d/%d] Downloaded: %s", completed, total, outcome.contact)
            else:
                logger.warning(
                    "[%d/%d] Failed %s: %s", completed, total, outcome.contact, outcome.error
                )
            if dl.manifest_save_every and (
                completed % dl.manifest_save_every == 0 or completed == total
            ):
                _write_manifest(to_download, manifest_path, variant.manifest_columns)

    if not dl.manifest_save_every:
        _write_manifest(to_download, manifest_path, variant.manifest_columns)

    successes = int((to_download["Download_Status"] == "Success").sum())
    logger.info(
        "Download complete: %d/%d succeeded. Manifest: %s",
        successes,
        len(to_download),
        manifest_path,
    )
    return manifest_path

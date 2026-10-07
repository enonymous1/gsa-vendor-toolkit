"""Standardized logging configuration for vendors_toolkit.

Replaces the ~60 ``print()`` calls scattered across the original scripts with
standard-library logging:

- console handler at the configured level (default ``INFO``),
- optional rotating file handler capturing ``DEBUG`` and above,
- idempotent: calling :func:`configure_logging` twice never adds duplicate
  handlers, it only refreshes the console level.

Modules should log via ``logging.getLogger(__name__)``; loggers under the
``vendors_toolkit`` namespace propagate to the handlers installed here.
The log level can also be set with the ``VENDORS_LOG_LEVEL`` environment
variable (e.g. ``VENDORS_LOG_LEVEL=DEBUG``).
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from vendors_toolkit.config import LOG_LEVEL_ENV_VAR

LOGGER_NAME = "vendors_toolkit"
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _coerce_level(level: str | int) -> int:
    """Accept a logging level name (case-insensitive) or a numeric level."""
    if isinstance(level, int):
        return level
    numeric = logging.getLevelName(level.upper())
    if not isinstance(numeric, int):
        raise ValueError(f"Unknown log level: {level!r}")
    return numeric


def resolve_log_level(default: str | int = "INFO") -> int:
    """Resolve the console log level, honoring the ``VENDORS_LOG_LEVEL`` env var."""
    env = os.environ.get(LOG_LEVEL_ENV_VAR)
    return _coerce_level(env) if env else _coerce_level(default)


def _formatter() -> logging.Formatter:
    return logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT)


def configure_logging(
    level: str | int | None = None,
    log_dir: Path | str | None = None,
    log_filename: str = "vendors_toolkit.log",
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
) -> logging.Logger:
    """Configure the ``vendors_toolkit`` logger and return it.

    Args:
        level: Console level (name or number). Defaults to ``VENDORS_LOG_LEVEL``
            env var, else ``INFO``.
        log_dir: If given, a rotating file handler capturing ``DEBUG`` and above
            is installed there (created if missing).
        log_filename: Name of the rotating log file inside ``log_dir``.
        max_bytes: Rotate the log file after this many bytes.
        backup_count: How many rotated files to keep.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)  # capture everything; handlers filter
    logger.propagate = False

    console_level = resolve_log_level() if level is None else _coerce_level(level)

    if logger.handlers:
        # Idempotent: refresh the console level instead of adding handlers.
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                continue
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(console_level)
        return logger

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(_formatter())
    logger.addHandler(console)

    if log_dir is not None:
        resolved = Path(log_dir).expanduser()
        resolved.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            resolved / log_filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_formatter())
        logger.addHandler(file_handler)

    return logger

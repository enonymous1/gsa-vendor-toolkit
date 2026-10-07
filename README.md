# ss-gsaVendors refactor

Refactoring of the `ss-gsaVendors` GSA vendor price-list pipeline into an installable,
maintainable package: **`vendors_toolkit`**.

Pipeline: download vendor price lists → organize by State/City → merge Excel
"Price List" sheets into master CSVs → filter by SIN (54151S IT / 541611 consulting)
→ compute per-title pricing metrics → generate HTML dashboards and Markdown summaries.

## Layout

```text
ss-gsaVendors-refactor/
├── pyproject.toml                 # packaging, ruff + mypy-strict config, `vendors-toolkit` entry point
├── src/vendors_toolkit/
│   ├── __init__.py
│   ├── config.py                  # (Phase 2) centralized configuration
│   ├── logging_config.py          # (Phase 2) standardized logging
│   ├── data/                      # (Phase 3) mapping, sanitization helpers
│   ├── pipeline/                  # (Phases 3-4) sanitize, download, organize, merge, filter
│   ├── analysis/                  # (Phase 5) metrics, audit, exports, national merge
│   ├── reporting/                 # (Phase 6) dashboards, executive summaries
│   └── cli.py                     # CLI skeleton (Phase 1) → full subcommands (later)
├── tools/export_to_md.py          # (Phase 7) relocated from project root, unchanged
├── original/                      # pristine copies of the 20 original scripts (reference only)
└── tests/                         # (Phase 9) pytest suite + differential checks
```

## Install

```bash
pip install -e .        # runtime
pip install -e ".[dev]" # + pytest, ruff, mypy
```

## Usage

```bash
vendors-toolkit --help
vendors-toolkit sanitize --help   # per-stage help
```

> Phase 1 status: the CLI parses every stage but each one reports "not implemented
> yet" until its engine is built in a later phase. Stages are being implemented
> strictly one module at a time so behavior stays verifiable against `original/`.

## Quality gates

- `ruff check .` and `ruff format --check .`
- `mypy` (strict)
- `pytest` — unit tests plus differential tests proving refactored outputs match
  the originals on sample data

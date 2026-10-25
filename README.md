# gsa-vendor-toolkit

GSA vendor price-list pipeline, refactored from the original `ss-gsaVendors`
scripts into an installable, maintainable Python package (`vendors_toolkit`).

**Pipeline:** download vendor price lists → organize by State/City → merge Excel
"Price List" sheets into per-state master CSVs → filter by SIN → compute per-title
pricing metrics → audit / export → build the national master → generate HTML
dashboards and Markdown executive summaries.

Two pipeline variants share the engines: **54151S** (IT services) and **541611**
(management consulting). Where the original script twins disagreed (retries,
copy-vs-move, dashboard page length, …), the drift is captured explicitly in
`config.py` rather than hidden in duplicated code.

## Layout

```text
gsa-vendor-toolkit/
├── pyproject.toml                 # packaging, ruff + mypy-strict, `vendors-toolkit` entry point
├── src/vendors_toolkit/
│   ├── __init__.py
│   ├── cli.py                     # `vendors-toolkit` subcommands (one per stage)
│   ├── config.py                  # centralized frozen-dataclass configuration
│   ├── logging_config.py          # idempotent stdlib logging
│   ├── data/                      # GSA_MAP, sanitize_frame, title/price cleaning helpers
│   ├── pipeline/                  # sanitize, download, organize, merge, filter, national
│   ├── analysis/                  # metrics, audit + cardinality, exports, unique titles
│   └── reporting/                 # HTML dashboards + executive summaries
├── tools/export_to_md.py          # standalone .py → Markdown exporter (unchanged)
├── original/                      # pristine copies of the 20 original scripts (reference only)
└── tests/                         # pytest suite (47 tests)
```

## Install

```bash
pip install -e .          # runtime (+ `vendors-toolkit` on PATH)
pip install -e ".[dev]"   # + pytest, ruff, mypy, pandas-stubs
```

## Usage

```bash
# project root: --root, else $VENDORS_ROOT, else the working directory
vendors-toolkit --root /data/vendors --variant 54151S sanitize
vendors-toolkit --root /data/vendors --variant 541611 download --limit 100
vendors-toolkit --root /data/vendors merge --states VA DC
vendors-toolkit --root /data/vendors filter --variant 54151S --states VA
vendors-toolkit --root /data/vendors metrics --states VA DC National
vendors-toolkit --root /data/vendors national --variant 54151S
vendors-toolkit --root /data/vendors report --states VA National
vendors-toolkit --help            # global options
vendors-toolkit download --help   # per-stage options
```

Stages run in pipeline order: `sanitize → download → organize → merge → filter →
metrics → audit → export → national → report`. `--variant` accepts `54151S`,
`541611`, or `all` (default). Logging: `--log-level`, `--log-dir` (rotating DEBUG
file), or the `VENDORS_LOG_LEVEL` env var.

## Configuration

`config.py` holds every knob the originals hardcoded: paths, download
retries/timeouts/workers, merge sheet matching, metrics filenames, dashboard CDN
URLs, and the per-variant drift (`VariantConfig`). All dataclasses are frozen.

## Behavioral notes (deliberate fixes vs the originals)

- Missing input files raise `FileNotFoundError` instead of printing and continuing.
- Missing titles normalize to `""` (the IT analyzer emitted `"NONE"`/`"None"`).
- Price cleaning strips `$`/commas on every pandas version — the IT analyzer's
  `dtype == object` check silently dropped `$`-prices on pandas 3.
- Dashboard descriptions are HTML-escaped (the originals injected raw markup).
- The 54151S downloader no longer crashes keying futures on an unhashable Series.
- Both mergers match the `"price list"` sheet exactly (case-insensitive).

## Quality gates

```bash
ruff check src/ tests/ && ruff format --check src/ tests/
mypy src/          # strict
pytest             # 47 tests
```

Differential tests proving byte-level behavioral parity with `original/` were run
per phase during the refactor (see the git history: phases 3–7).

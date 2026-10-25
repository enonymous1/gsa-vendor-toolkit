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
│   ├── reporting/                 # HTML dashboards + executive summaries
│   └── integrations/              # SAM.gov API client (scaffold; needs SAM_API_KEY)
├── tools/export_to_md.py          # standalone .py → Markdown exporter (unchanged)
├── original/                      # pristine copies of the 20 original scripts (reference only)
└── tests/                         # pytest suite (57 tests)
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

## Pipeline / workflow

```text
vendor snapshot CSV (you supply)
  └─► sanitize ─► download ─► organize ─► merge ─► filter ─► metrics
                                                          ├─► audit / export
                                                          ├─► national (54151S)
                                                          └─► report (dashboards)
```

### Step 0 — Get the input file (the pipeline does not fetch this itself)

The pipeline starts from a **vendor snapshot CSV**: one row per vendor, with at
least these columns: `Vendor`, `Contact #`, `Price List` (the URL of the
vendor's published price list), `Category`, `State`, `City`,
`Has_Price_List_Flag`.

Where it comes from: **GSA eLibrary** (gsaelibrary.gsa.gov) — search by SIN
(54151S = IT Professional Services; 541611 = management consulting) or by
contractor name, and export/save the vendor listing as a CSV. eLibrary has no
public API, so this step is a manual export, not a download stage.

Where it goes: `ext_res/` under the configured name — `2026_02_12_04_10_24.csv`
for 54151S, `2026_03_02_08_18_31.csv` for 541611 (those dated names are just
the snapshots the config was built with; rename your export to match, or pass
`--input` to `sanitize` to use another file).

### Stages and their outputs (under `output/`)

| Stage | Reads | Writes |
| --- | --- | --- |
| `sanitize` | `ext_res/<raw CSV>` | `ext_res/<sanitized CSV>` |
| `download` | sanitized CSV's `Price List` URLs | `downloads/<price lists>`, `summaries/<manifest>` |
| `organize` | downloads dir | `downloads/<by_region>/<STATE>/<City>/` |
| `merge` | organized workbooks' `"Price List"` sheets | `<analysis>/<STATE>_Master_Price_List.csv` |
| `filter` | merged masters | `merged_filtered/<STATE>_SIN_<SIN>_Only.csv` |
| `metrics` | filtered files (54151S) / merged files (541611) | `<metrics>/<STATE>_<..._Metrics.csv` (+ xlsx) |
| `audit` | sanitized CSV, merged masters | `output/audit_summary.md`, `column_selections/*.json` |
| `export` | sanitized CSV | `price_lists/`, `regional/<STATE>/`, `summaries/*.md` |
| `national` | manifest + sanitized CSV + organized workbooks (54151S) | `merged_national/National_IT_Master_Price_List.csv` |
| `report` | metrics CSVs | `<reports>/<STATE>_*_Full_Report.html`, `*_Executive_Summary.md` |

The `download` stage is plain HTTP file fetching (`requests.get` per `Price
List` URL, with retries) — there is no API behind the price lists. The
`national` stage re-reads the organized workbooks through the download
manifest; it does not concatenate the merged state files.

### SAM.gov enrichment (scaffold, optional)

`integrations/samgov.py` wires the free SAM.gov APIs for future vendor
enrichment (entity lookup by UEI/CAGE, exclusion screening, opportunity
search). It is inert until a key exists:

```bash
# free key: SAM.gov account → Account Details → "Public API Key"
export SAM_API_KEY="SAM-..."
vendors-toolkit sam --status          # check configuration, no API call
vendors-toolkit sam --uei <UEI>       # entity lookup
vendors-toolkit sam --uei <UEI> --excluded   # exclusion check
vendors-toolkit sam --keywords "IT services" --naics 54151S
```

Free tiers: 10 requests/day with a basic account, 1,000/day with a SAM entity
role. Keys expire every 90 days. The `sam` command runs once per invocation
(not per variant) so it never double-spends the daily budget.

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
pytest             # 57 tests
```

Differential tests proving byte-level behavioral parity with `original/` were run
per phase during the refactor (see the git history: phases 3–7).

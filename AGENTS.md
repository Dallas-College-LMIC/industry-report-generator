# AGENTS.md — Industry Report Generator

## Project Overview

A config-driven CLI tool that produces formatted Excel data tables for Dallas College LMIC industry reports. Given a TOML config with NAICS/SOC codes, it queries the Lightcast API (Core LMI + JPA) and outputs a multi-sheet workbook matching the structure of published reports (e.g., Healthcare, Construction, Aerospace).

- **Language**: Python 3.13+
- **Package manager**: `uv`
- **Dev environment**: Nix flake (`nix develop`)
- **Entrypoint**: `python -m industry_report --config <path>.toml`
- **CLI alias**: `industry-report --config <path>.toml`

---

## Architecture

```
config.toml
    │
    ├──→ fetch_corelmi.py ──→ industry data (MSA / state / national)
    │                     ──→ occupation data (MSA)
    │                     ──→ demographic data (MSA) [future]
    │
    ├──→ fetch_postings.py ──→ skills, employers, salary, postings (MSA)
    │         │
    │         └──→ (on failure) read_manual.py ──→ same data from Excel files
    │
    ├──→ fetch_zip.py ──→ ZIP-level industry, occupation, census data (batch job)
    │         │
    │         └──→ build_zip.py ──→ ZIP-level analysis sheets (reads CSVs)
    │
    ├──→ fetch_pulse.py ──→ FRED (UI claims, Dallas Fed, BFS, BLS mirror)
    │                   ──→ Socrata (WARN notices, TX sales tax)
    │                   ──→ BLS API (DFW employment)
    │                   ──→ Census BFS API (business formation)
    │         │
    │         └──→ build_pulse.py ──→ pulse DataFrames for dashboard
    │
    └──→ build.py ──→ OrderedDict of sheet_name → DataFrame
              │
              └──→ export.py ──→ formatted .xlsx workbook
```

### Data directory convention

Each config `configs/<stem>.toml` has a companion data directory `configs/<stem>/` that holds pre-fetched ZIP-level CSVs:

```
configs/
  healthcare_dfw.toml
  healthcare_dfw/              ← committed to git
    industry.csv               (~52 KB, 308 rows)
    occupation.csv             (~96 KB, 401 rows)
    census.csv                 (~116 KB, 281 rows)
    geography_manifest.json    ← ZIP code list for fetchers
    .cache/                    ← gitignored pickle cache
```

The directory path is derived from the config file stem via `ReportConfig.zip_data`.

### Source modules (`src/industry_report/`)

| File | Responsibility |
|------|----------------|
| `cli.py` | Argument parsing, env loading (`.env`), orchestration (incl. `--fetch-zip`) |
| `config.py` | TOML loader → `ReportConfig` dataclass (incl. `zip_data` property) |
| `fetch_corelmi.py` | Lightcast Core LMI queries via `pyghtcast` |
| `fetch_postings.py` | Lightcast JPA queries via `pyghtcast` (often unavailable) |
| `fetch_zip.py` | ZIP-level batch fetchers (Lightcast per-ZIP + Census ACS) |
| `fetch_pulse.py` | **Pulse data fetchers** — FRED, Socrata, BLS, Census BFS APIs |
| `read_manual.py` | Fallback readers for `.xls`, `.xlsx`, `.csv` exports from Lightcast web UI |
| `build.py` | Assemble API + fallback data into MSA-level report DataFrames |
| `build_zip.py` | Assemble pre-fetched CSVs into ZIP-level analysis DataFrames |
| `build_pulse.py` | **Pulse data assembler** — orchestrates pulse fetchers, computes key metrics |
| `export.py` | Write formatted workbook via `dclmic_export` |
| `dashboard.py` | Streamlit dashboard with MSA-Level, ZIP-Level Spatial, and **Pulse** tabs |

---

## Key Conventions

### API-first with silent fallback

Fetchers **must not crash** the pipeline. Every API call is wrapped in `try/except` and returns `None` on failure. `build.py` then tries the next data source (API → manual Excel → skip sheet).

```python
# Correct
try:
    df = fetch_occupation_data(...)
except Exception:
    df = None

# build.py later checks
if df is not None and not df.empty:
    sheets["..."] = df
```

### Column rename maps

Use explicit rename dictionaries (`OCCUPATION_COLUMN_MAP`, `INDUSTRY_COLUMN_MAP`) to transform raw API column names into report-friendly names. Drop unwanted columns by mapping them to `None`.

### Title maps populated at build time

`SOC_TITLE_MAP` and `NAICS_TITLE_MAP` are module-level globals set by `build_all_sheets()` from the config. They are used to insert human-readable titles next to codes.

### Ordered output

Sheets are stored in `collections.OrderedDict` so the workbook tab order is deterministic and matches the logical report flow.

### Living wage flagging

Any wage at or below `$23.36/hr` (Dallas County living wage for 1 adult) gets a `Below Living Wage` boolean column. Update `living_wage` in config if this threshold changes.

---

## Data Sources

| Dataset | API module | Fallback file | Used for |
|---------|-----------|---------------|----------|
| Core LMI `EMSI.us.Industry` | `fetch_corelmi.py` | `overview.xls` | Industry jobs, earnings, growth |
| Core LMI `EMSI.us.Occupation` | `fetch_corelmi.py` | `occ.csv` | Occupation jobs, wages, openings |
| Core LMI `emsi.us.occupation.demographics` | `fetch_corelmi.py` | `overview.xls` | Age, race, gender breakdowns |
| JPA `post_totals` | `fetch_postings.py` | `jpa.xls` | Total postings, unique companies |
| JPA `post_rankings` | `fetch_postings.py` | `jpa.xls` | Top skills, top employers |
| JPA `post_timeseries` | `fetch_postings.py` | `jpa.xls` | Advertised salary trend |

**Auth**: Core LMI uses `LCAPI_USER` / `LCAPI_PASS` env vars. JPA requires `postings:us` scope (currently unavailable for our credentials; all JPA sheets fall back to manual Excel).

### Pulse Data Sources (frequently-updated economic indicators)

| Dataset | API module | Cadence | API Key |
|---------|-----------|---------|--------|
| Texas UI Claims (FRED) | `fetch_pulse.py` | Weekly | `FRED_API_KEY` (required) |
| Dallas Fed TMOS/TSSOS (FRED) | `fetch_pulse.py` | Monthly | `FRED_API_KEY` |
| Census Business Formation Stats | `fetch_pulse.py` | Monthly | None (FRED fallback) |
| BLS Metro CES Employment | `fetch_pulse.py` | Monthly | `BLS_API_KEY` (optional, FRED fallback) |
| Texas WARN Act Notices (Socrata) | `fetch_pulse.py` | Daily | `SOCRATA_APP_TOKEN` (optional) |
| TX Sales Tax Allocations (Socrata) | `fetch_pulse.py` | Monthly | `SOCRATA_APP_TOKEN` (optional) |

**Auth**: FRED requires a free API key from `fredaccount.stlouisfed.org`. Socrata works without a token (lower rate limits). BLS has a free key but FRED mirrors most series.

---

## Configuration

One TOML file per industry/region. Example: `configs/healthcare_dfw.toml`

```toml
[report]
name = "Healthcare"
output_dir = "./output"

[industry]
naics_codes = ["6211", "6212", ...]
naics_titles = ["Offices of Physicians", ...]   # optional, for readable rows
label = "Healthcare Industries"

[occupation]
soc_codes = ["29-1141", "29-1171", ...]
soc_titles = ["Registered Nurses", ...]         # optional, for readable rows
label = "Healthcare Occupations"

[geography]
msa_code = "19100"
msa_name = "Dallas-Fort Worth-Arlington, TX"
state_code = "48"
living_wage = 23.36

[manual_inputs]   # all optional — enable fallback when JPA is down
overview_xls = "path/to/overview.xls"
jpa_xls = "path/to/jpa.xls"
occ_csv = "path/to/occ.csv"
```

**To add a new industry**: copy a config, change `naics_codes`, `soc_codes`, and `name`. Everything else stays the same for DFW reports.

---

## Running / Developing

```bash
# Enter dev shell (Nix)
nix develop

# Run with a config
python -m industry_report --config configs/healthcare_dfw.toml

# Or via installed script
industry-report --config configs/healthcare_dfw.toml

# Pre-fetch ZIP-level data (batch job, 30-60 min)
industry-report --config configs/healthcare_dfw.toml --fetch-zip

# Sync dependencies
uv sync

# Install with ZIP extras (for censusdis)
uv sync --extra zip

# Lint / format
ruff check src/
ruff format src/

# Run tests
python -m pytest tests/ -v
```

**Env vars** (can also live in `.env` at repo root):
- `LCAPI_USER` — Lightcast API username
- `LCAPI_PASS` — Lightcast API password
- `FRED_API_KEY` — FRED API key (required for Pulse tab)
- `BLS_API_KEY` — BLS API key (optional, FRED mirrors most series)
- `SOCRATA_APP_TOKEN` — Socrata app token (optional, works without)

---

## Dashboard (Streamlit)

A lightweight Streamlit dashboard is included for interactive exploration and public sharing.

### Run locally

```bash
# Install with dashboard extras
uv sync --extra dashboard

# Launch
streamlit run src/industry_report/dashboard.py

# Or via the installed launcher
industry-report-dashboard
```

### What it does

1. Pick a TOML config from the sidebar (populated from `configs/*.toml`).
2. **MSA-Level Report** tab: Click **"Generate Report from Lightcast"** to fetch fresh data via the existing `build.py` pipeline.
3. **ZIP-Level Spatial** tab: View pre-fetched ZIP-level analysis from cached CSVs.
4. **Pulse** tab: View frequently-updated economic indicators (UI claims, WARN notices, Dallas Fed surveys, BLS employment, business formation, sales tax). Data is cached for 1 day.
5. Download the generated Excel workbook.

### Deploy to Streamlit Community Cloud

1. Push this repo to a public GitHub repository.
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) → **New app**.
3. Point the app entrypoint to `src/industry_report/dashboard.py`.
4. Add `LCAPI_USER`, `LCAPI_PASS`, and `FRED_API_KEY` as app **Secrets** in the Streamlit Cloud UI.
5. Deploy. You get a public URL like `https://your-app.streamlit.app`.

**Why this works:** Both `pyghtcast` and `dclmic-export` are public repos, and Streamlit Cloud reads `pyproject.toml` directly. No custom build steps needed.

---

## Output Sheets

The tool generates whatever it can from available data. Expected sheets (when fully supplied):

1. **Industry Overview** — per-NAICS jobs, earnings, share of sector
2. **Did you know** — summary stats (total jobs, postings, growth, employers competing)
3. **Notable Occupations** — SOC-level employment, growth, openings, wages
4. **Wage Analysis** — P10/P50/P90 wages sorted by median
5. **Notable Employers in DFW** — top companies by unique postings
6. **In-Demand Skills** — top specialized skills from postings
7. **Top Common Skills** — soft skills from manual JPA
8. **Top Software Skills** — technical skills from manual JPA
9. **Regional Comparison** — DFW vs Texas vs US (jobs, earnings, growth, postings)
10. **Age / Race / Gender Breakdown** — workforce demographics
11. **Advertised Wage Trend** — monthly posting salary trend
12. **Work where you live** — employers competing count

### ZIP-Level Sheets (when CSVs are available in `config.zip_data/`)

13. **ZIP Industry Detail** — industry jobs/earnings/growth per ZIP
14. **ZIP Occupation Detail** — occupation jobs/wages/openings per ZIP
15. **Census Context** — demographics, education, income per ZIP
16. **Top ZIPs by Jobs** — employment concentration analysis (top 25 industry + top 25 occupation)
17. **Wage Analysis** — wage distribution (P10/P50/P90) per ZIP sorted by median

---

## Common Agent Tasks

### Adding a new output sheet

1. Add fetcher logic to `fetch_corelmi.py` or `fetch_postings.py` (or `read_manual.py` fallback).
2. Add `_build_<sheet>_sheet()` in `build.py`. Follow the pattern: accept API result, fallback to manual, return `DataFrame | None`.
3. Call it in `build_all_sheets()` and insert into the `OrderedDict`.
4. Add column formatting rules to `export.py` `COL_FORMAT` if needed.
5. Update this AGENTS.md.

### Adding a new data source/fetcher

1. Create a new `fetch_*.py` module or extend an existing one.
2. Return `pd.DataFrame | dict | None`. Never raise on expected failures (bad auth, no scope, network issues).
3. Add corresponding `read_manual.py` fallback if the data can come from Lightcast Excel exports.
4. Wire into `build.py`.

### Updating report frame / columns

1. Modify the relevant `_build_*_sheet()` in `build.py`.
2. Update `OCCUPATION_COLUMN_MAP` or `INDUSTRY_COLUMN_MAP` if API column names changed.
3. Update `COL_FORMAT` in `export.py` so numbers format correctly in Excel.

### Handling a new geography

The tool is currently hardcoded for DFW (`msa_code = "19100"`, `state_code = "48"`). To support a new MSA:

1. Add the new MSA code and state code to the config.
2. Update `fetch_corelmi.py` `fetch_regional_comparison()` to accept the new codes (it already parameterizes them).
3. Verify JPA filter payloads in `fetch_postings.py` use the correct MSA code.

### Adding a new Pulse data source

1. Add a fetcher function in `fetch_pulse.py`. Follow the pattern: return `pd.DataFrame | None`, wrap in `try/except`.
2. Wire the fetcher into `build_pulse_data()` in `build_pulse.py`.
3. If the source provides a key metric, add extraction logic to `compute_key_metrics()`.
4. Add a panel or metric card in the Pulse tab of `dashboard.py`.
5. Add mocked tests in `tests/test_pulse.py`.
6. Update this AGENTS.md.

---

## Dependencies & Internal Libraries

| Package | Purpose |
|---------|---------|
| `pandas` | Data manipulation |
| `openpyxl` | Excel writing |
| `xlrd` | Legacy `.xls` reading (manual fallback) |
| `pyghtcast` | Lightcast API wrapper (git dep) |
| `dclmic-export` | Formatted Excel export with auto-styling (git dep) |
| `fredapi` | FRED API wrapper (UI claims, Dallas Fed, BFS/BLS mirrors) |
| `sodapy` | Socrata API client (WARN notices, TX sales tax) |

Both git deps are Dallas College LMIC internal packages. If API behavior changes, you may need to patch `pyghtcast` (e.g., the `JobPostingsConnection` class needed `base_url` + `scope` initialization).

---

## Testing

Tests live in `tests/` and use `pytest`. Key test modules:

- `tests/test_zip_module.py` — ZIP-level module tests (config property, build_zip with fixtures, missing data, CLI flag)
- `tests/test_pulse.py` — Pulse data fetcher tests (FRED, Socrata, BLS, BFS mocks; build_pulse orchestration; key metrics extraction)

Fixtures are in `tests/fixtures/`:

- `tests/fixtures/test_config.toml` — minimal TOML config for tests
- `tests/fixtures/zip_data/` — 10-row CSV samples for industry, occupation, census

When adding tests:

- Use `pytest`.
- Mock `pyghtcast.lightcast.Lightcast` and `JobPostings` to avoid network calls.
- Provide minimal fixture files in `tests/fixtures/` for manual fallback readers.
- Test the fallback chain: API fail → manual success → sheet built correctly.
- For ZIP-level: test with fixture CSVs and test graceful handling of missing data.

---

## Known Limitations

- JPA API scope (`postings:us`) is not available with current credentials. All JPA-dependent sheets rely on manual Excel fallbacks.
- Typical Entry Level Education is not available from Lightcast API; reports currently source this from BLS SOC definitions (not yet automated).
- Demographics API (`emsi.us.occupation.demographics`) exists in spec but is not yet wired in `fetch_corelmi.py`; demographic sheets come exclusively from manual `overview.xls`.
- ZIP-level spatial analysis is now implemented. Use `--fetch-zip` to pre-fetch data, and the Streamlit dashboard shows a **ZIP-Level Spatial** tab. Data lives in `configs/<stem>/` as committed CSVs (~260 KB total per industry).

---

## File Checklist for New Reports

When onboarding a new industry:

- [ ] Create `configs/<industry>_dfw.toml` with correct NAICS and SOC codes
- [ ] Add `naics_titles` and `soc_titles` for readable output rows
- [ ] Verify `msa_code`, `state_code`, and `living_wage` in `[geography]`
- [ ] (Optional) Download Lightcast exports and set `[manual_inputs]` paths if JPA is unavailable
- [ ] (Optional) Run `industry-report --config configs/<industry>_dfw.toml --fetch-zip` to generate ZIP-level CSVs
- [ ] Run `python -m industry_report --config configs/<industry>_dfw.toml`
- [ ] Inspect output in `configs/output/<Name>_Report_Data.xlsx`

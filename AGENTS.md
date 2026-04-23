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
    └──→ build.py ──→ OrderedDict of sheet_name → DataFrame
              │
              └──→ export.py ──→ formatted .xlsx workbook
```

### Source modules (`src/industry_report/`)

| File | Responsibility |
|------|----------------|
| `cli.py` | Argument parsing, env loading (`.env`), orchestration |
| `config.py` | TOML loader → `ReportConfig` dataclass |
| `fetch_corelmi.py` | Lightcast Core LMI queries via `pyghtcast` |
| `fetch_postings.py` | Lightcast JPA queries via `pyghtcast` (often unavailable) |
| `read_manual.py` | Fallback readers for `.xls`, `.xlsx`, `.csv` exports from Lightcast web UI |
| `build.py` | Assemble API + fallback data into report DataFrames |
| `export.py` | Write formatted workbook via `dclmic_export` |

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

# Sync dependencies
uv sync

# Lint / format
ruff check src/
ruff format src/
```

**Env vars** (can also live in `.env` at repo root):
- `LCAPI_USER` — Lightcast API username
- `LCAPI_PASS` — Lightcast API password

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
2. Click **"Generate Report from Lightcast"** to fetch fresh data via the existing `build.py` pipeline.
3. View key metrics, a Plotly wage chart, and every report sheet in expandable tables.
4. Download the generated Excel workbook.

### Deploy to Streamlit Community Cloud

1. Push this repo to a public GitHub repository.
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) → **New app**.
3. Point the app entrypoint to `src/industry_report/dashboard.py`.
4. Add `LCAPI_USER` and `LCAPI_PASS` as app **Secrets** in the Streamlit Cloud UI.
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

---

## Dependencies & Internal Libraries

| Package | Purpose |
|---------|---------|
| `pandas` | Data manipulation |
| `openpyxl` | Excel writing |
| `xlrd` | Legacy `.xls` reading (manual fallback) |
| `pyghtcast` | Lightcast API wrapper (git dep) |
| `dclmic-export` | Formatted Excel export with auto-styling (git dep) |

Both git deps are Dallas College LMIC internal packages. If API behavior changes, you may need to patch `pyghtcast` (e.g., the `JobPostingsConnection` class needed `base_url` + `scope` initialization).

---

## Testing

There is no test suite yet (`tests/` exists but is empty). When adding tests:

- Use `pytest`.
- Mock `pyghtcast.lightcast.Lightcast` and `JobPostings` to avoid network calls.
- Provide minimal fixture files in `tests/fixtures/` for manual fallback readers.
- Test the fallback chain: API fail → manual success → sheet built correctly.

---

## Known Limitations

- JPA API scope (`postings:us`) is not available with current credentials. All JPA-dependent sheets rely on manual Excel fallbacks.
- Typical Entry Level Education is not available from Lightcast API; reports currently source this from BLS SOC definitions (not yet automated).
- Demographics API (`emsi.us.occupation.demographics`) exists in spec but is not yet wired in `fetch_corelmi.py`; demographic sheets come exclusively from manual `overview.xls`.
- ZIP-level spatial analysis is explicitly out of scope for this module (separate future module).

---

## File Checklist for New Reports

When onboarding a new industry:

- [ ] Create `configs/<industry>_dfw.toml` with correct NAICS and SOC codes
- [ ] Add `naics_titles` and `soc_titles` for readable output rows
- [ ] Verify `msa_code`, `state_code`, and `living_wage` in `[geography]`
- [ ] (Optional) Download Lightcast exports and set `[manual_inputs]` paths if JPA is unavailable
- [ ] Run `python -m industry_report --config configs/<industry>_dfw.toml`
- [ ] Inspect output in `configs/output/<Name>_Report_Data.xlsx`

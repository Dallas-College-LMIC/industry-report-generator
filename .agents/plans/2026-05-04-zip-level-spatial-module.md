# ZIP-Level Spatial Module

**Date**: 2026-05-04
**Status**: Planning

## Context

The industry-report-generator currently produces MSA-level Excel data tables (~5-10 API calls, returns in seconds). The `report-framework` repo has a working ZIP-level pipeline that fetches per-ZIP data from Lightcast and Census (~1000+ API calls, 30-60 min). We need to port that capability into this project and surface it in the Streamlit dashboard, which is deployed publicly on Streamlit Community Cloud.

### Key decisions

- **Data is static** — Lightcast updates quarterly/annually. ZIP-level data is a snapshot, not live.
- **Option C approach** — Pre-fetch ZIP data offline via CLI, commit the resulting CSVs (small, ~260 KB per industry) to git. Dashboard reads them instantly. No live fetching from the dashboard.
- **Data lives alongside configs** — `configs/healthcare_dfw.toml` → `configs/healthcare_dfw/industry.csv`, `occupation.csv`, `census.csv`. Derived from config stem, like `output_dir`.
- **Intermediate pickle caches are gitignored** — Only the 3 final aggregated CSVs are committed.
- **Reference implementation**: `report-framework/reports/2026-03-26-dr-j-industry-report-healthcare/` and `report-framework/reports/2026-2-27-dr-j-industry-report-aero/`.

## Steps

- [x] **Add `zip_data` property to `ReportConfig`** (`config.py`)
  - Computed property that returns `configs/<stem>/` (e.g. `configs/healthcare_dfw/`)
  - Derived from config file stem — no TOML changes needed
  - Create directory if it doesn't exist

- [x] **Create `fetch_zip.py`** — Port the three fetcher scripts from `report-framework` into a single module
  - `fetch_zip_industry(config, cache_dir)` — iterates ZIPs from geography manifest, queries Lightcast `EMSI.us.Industry` per ZIP with all NAICS aggregated, per-ZIP pickle caching, saves final CSV to `config.zip_data / "industry.csv"`
  - `fetch_zip_occupation(config, cache_dir)` — same pattern for `EMSI.us.Occupation` with all SOC codes, saves to `config.zip_data / "occupation.csv"`
  - `fetch_zip_census(config, cache_dir)` — uses `censusdis` to pull ACS 5-year at ZCTA level, saves to `config.zip_data / "census.csv"`
  - Port geography manifest system — ZIP list defined in config or a `geography_manifest.json` companion file in `config.zip_data/`
  - Add `censusdis` as optional dependency group: `[project.optional-dependencies] zip = ["censusdis"]`

- [x] **Create `build_zip.py`** — Port `build_datasets.py` logic from `report-framework`
  - `build_zip_sheets(config)` function that reads the 3 CSVs from `config.zip_data/`
  - Joins Lightcast industry + census on ZIP code, Lightcast occupation + census on ZIP code
  - Returns `OrderedDict` of ZIP-level sheet frames:
    - ZIP Industry Detail — industry jobs/earnings/growth per ZIP with census context
    - ZIP Occupation Detail — occupation jobs/wages/openings per ZIP with census context
    - Census Context — demographics, education, income per ZIP
    - Top ZIPs by Jobs — employment concentration analysis
    - Wage Analysis — wage distribution (P10/P50/P90) per ZIP
  - Returns empty/None gracefully if CSVs don't exist

- [x] **Add `--fetch-zip` CLI flag** (`cli.py`)
  - Optional `--fetch-zip` flag
  - When set: runs the three fetchers (30-60 min batch job), then exits
  - Pickle cache lives under `config.zip_data / ".cache/"` and is gitignored
  - Prints progress: "Fetching ZIP 234/418..."

- [x] **Add ZIP tab to the Streamlit dashboard** (`dashboard.py`)
  - `st.tabs(["MSA-Level Report", "ZIP-Level Spatial"])`
  - ZIP tab checks if `config.zip_data / "industry.csv"` exists
  - If CSVs exist: calls `build_zip_sheets(config)` (instant, reads CSVs only) and renders:
    - ZIP-level choropleth map (Plotly) showing jobs or wages by ZIP
    - Data tables in expanders
    - Download button for ZIP Excel
  - If CSVs don't exist: show instructions — `Run: industry-report --config <path> --fetch-zip`

- [x] **Commit pre-fetched CSV data for deployed industries**
  - Copy the 3 CSV files from `report-framework/reports/2026-03-26-dr-j-industry-report-healthcare/1-src/` into `configs/healthcare_dfw/`
  - Copy or generate equivalent for `configs/construction_dfw/` when available
  - ~260 KB per industry total (52K industry + 96K occupation + 116K census)

- [x] **Update `.gitignore`**
  - Add `configs/*/.cache/` to keep pickle files out of git

- [x] **Update `AGENTS.md`**
  - Document ZIP-level architecture
  - Document `--fetch-zip` CLI flag
  - Document data directory convention (`configs/<stem>/`)
  - Update architecture diagram
  - Update output sheets table

- [x] **Write tests** (TDD — write before/during implementation)
  - Test `ReportConfig.zip_data` resolves to correct path
  - Test `build_zip_sheets()` with fixture CSVs (copied from report-framework data)
  - Test that missing CSVs returns empty/None gracefully
  - Test CLI `--fetch-zip` flag parsing

## File layout after implementation

```
configs/
  healthcare_dfw.toml
  healthcare_dfw/              ← committed to git
    industry.csv               (52 KB, 308 rows)
    occupation.csv             (96 KB, 401 rows)
    census.csv                 (116 KB, 281 rows)
    .cache/                    ← gitignored
      ind_zip_*.pkl
      occ_zip_*.pkl
      census_*.pkl
  construction_dfw.toml
  construction_dfw/
    industry.csv
    occupation.csv
    census.csv
  output/
    Healthcare_Report_Data.xlsx

src/industry_report/
  cli.py                       ← add --fetch-zip flag
  config.py                    ← add zip_data property
  fetch_zip.py                 ← NEW: ported ZIP-level fetchers
  build_zip.py                 ← NEW: ported ZIP-level sheet builder
  build.py                     ← existing, unchanged
  dashboard.py                 ← add ZIP-Level Spatial tab
  ...
```

## Dependencies

| Package | Purpose | Required by |
|---------|---------|-------------|
| `censusdis` | Census ACS data at ZCTA level | `fetch_zip.py` (optional `[zip]` extra) |

## Risks / Open questions

- **ZIP list source**: The `report-framework` hardcoded 418 ZIPs for DFW in a geography manifest. We need to decide: embed the ZIP list in the TOML config, use a companion `geography_manifest.json`, or derive it from MSA boundaries at fetch time.
- **`censusdis` dependency**: Only needed for the fetch step. Dashboard just reads CSVs. Can be an optional `[zip]` extra.
- **Data freshness**: Committed CSVs will age. Need a documented process to refresh them when Lightcast releases new dataruns.

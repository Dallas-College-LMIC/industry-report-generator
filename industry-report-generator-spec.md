# Industry Report Generator — Specification

## Overview

A config-driven CLI tool that produces formatted data tables for Dallas College LMIC industry reports. Given a set of NAICS and SOC codes, the tool queries the Lightcast API (Core LMI + JPA) and outputs a multi-sheet Excel workbook matching the table structure used in published reports (e.g., Healthcare, Aerospace).

The tool is API-first. If JPA access is unavailable, it falls back to reading manually-downloaded Lightcast Excel exports.

---

## Problem

Currently, producing data tables for an industry report requires:

1. Logging into Lightcast's web UI and manually downloading Excel exports (overview.xls, jpa.xls)
2. Manually pulling staffing pattern and occupation data
3. Running a Python script (`industry-report`) that parses those downloads into formatted sheets
4. Separately running an API pipeline (`report-framework`) for ZIP-level spatial data
5. Manually assembling data into the report document

Each new industry report repeats this entire process. The only things that change between reports are the NAICS codes, SOC codes, and industry name.

## Goals

- **One command, any industry**: `python -m industry_report --config healthcare_dfw.toml`
- **API-first**: Fetch everything directly from Lightcast + Census APIs where possible
- **Manual fallback**: Accept pre-downloaded Excel files for data not available via API
- **Report-aligned output**: Output sheets match the actual tables used in published industry reports, not generic data dumps
- **Config-driven**: Swapping industries means editing a TOML file, not code

## Non-goals (for now)

- ZIP-level spatial analysis and mapping (separate module later)
- Narrative text generation
- Program completions / education alignment tables (data source TBD)
- Report document assembly (Word/PDF generation)

---

## Output Tables

The tool produces an Excel workbook with the following sheets. These map directly to the tables found in the Healthcare and Aerospace industry reports produced by Dallas College LMIC.

### 1. Occupational Employment

The primary employment table used in every report. One row per selected SOC code.

| Column | Description | Source |
|---|---|---|
| SOC | Standard Occupational Classification code | Config |
| Description | Occupation title | Core LMI |
| 2026 Jobs | Current employment count in the MSA | Core LMI `Jobs.2026` |
| 2026-2029 Change | Projected absolute job growth | Core LMI `Jobs.2029 - Jobs.2026` |
| % Change | Projected growth rate | Derived |
| Avg. Annual Openings | Annual openings from growth + replacements | Core LMI `Openings.2026` |
| Median Hourly Wage | Median (P50) hourly wage | Core LMI `Earnings.Percentile50` |
| Typical Entry Education | Education level typically required | Core LMI |

**Living wage flag**: Wages at or below the Dallas County living wage ($23.36/hr for 1 adult) should be flagged in the output (red text or separate column).

**Notes**: The healthcare report uses absolute change; the aero report uses % change. The tool outputs both and lets the report author choose which to display.

### 2. Wage Analysis

Occupation-level wage summary, sorted by median wage descending.

| Column | Description | Source |
|---|---|---|
| Occupation | Occupation title (short form) | Core LMI |
| Median Hourly Wage | P50 hourly wage | Core LMI `Earnings.Percentile50` |
| Entry Wage (P10) | 10th percentile hourly wage | Core LMI `Earnings.Percentile10` |
| Experienced Wage (P90) | 90th percentile hourly wage | Core LMI `Earnings.Percentile90` |
| Typical Entry Education | Education level | Core LMI |
| Below Living Wage | Boolean flag | Derived (P50 <= $23.36) |

### 3. Regional Comparison

Side-by-side comparison of the MSA vs. state vs. national benchmarks. Used in the healthcare report's "Regional Comparison" section and useful as a standard section for any industry.

| Metric | DFW | Texas | United States |
|---|---|---|---|
| Jobs (Total) | Core LMI | Core LMI | Core LMI |
| Job Postings (Monthly Avg) | JPA | JPA | JPA |
| Postings per 1,000 Jobs | Derived | Derived | Derived |
| Projected Job Growth (2026-2029) | Core LMI | Core LMI | Core LMI |
| Earnings per Job | Core LMI | Core LMI | Core LMI |

**Implementation note**: This requires running the same Core LMI query at three geography levels (MSA, state, nation) and the same JPA totals query at three levels. The config specifies the MSA; state and national are automatic.

### 4. Top Employers

Ranked list of companies with the most job postings in the MSA for the selected NAICS codes.

| Column | Description | Source |
|---|---|---|
| Company | Employer name | JPA `post_rankings(facet='company')` |
| Unique Postings | Number of unique job postings | JPA |

**Default limit**: Top 8 employers (matching current report format).

**Fallback**: If JPA unavailable, read from overview.xls "Demand" sheet.

### 5. In-Demand Skills

Top specialized skills appearing in job postings for the industry in the MSA.

| Column | Description | Source |
|---|---|---|
| Skill | Skill name | JPA `post_rankings(facet='hard_skills')` |
| Postings | Number of postings mentioning this skill | JPA |
| % of Total Postings | Share of all postings | JPA / derived |

**Default limit**: Top 15 skills.

**Fallback**: If JPA unavailable, read from jpa.xls "Top Specialized Skills" sheet.

### 6. Workforce Demographics

Three sub-tables showing the demographic composition of the workforce in the selected occupations at the MSA level.

**6a. Age Breakdown**

| Age Group | Jobs | % of Total |
|---|---|---|
| 14-18 | ... | ... |
| 19-24 | ... | ... |
| 25-34 | ... | ... |
| ... | ... | ... |

**6b. Race and Ethnicity Breakdown**

| Race/Ethnicity | Jobs | % of Total |
|---|---|---|
| White | ... | ... |
| Hispanic or Latino | ... | ... |
| Black or African American | ... | ... |
| ... | ... | ... |

**6c. Gender Breakdown**

| Gender | Jobs | % of Total |
|---|---|---|
| Males | ... | ... |
| Females | ... | ... |

**Source**: Core LMI `emsi.us.occupation.demographics` dataset at MSA level, filtered by selected SOC codes.

**Fallback**: overview.xls sheets "Occ Age Breakdown", "Occ Race Ethnicity Breakdown", "Occ Gender Breakdown".

---

## Data Sources

### Lightcast Core LMI API (via pyghtcast)

Authentication: OAuth via `LCAPI_USER` / `LCAPI_PASS` environment variables.

| Dataset | Used for | Geography |
|---|---|---|
| `EMSI.us.Industry` | Total jobs, earnings, growth by NAICS | MSA, State, National |
| `EMSI.us.Occupation` | Jobs, wages, openings, education by SOC | MSA |
| `emsi.us.occupation.demographics` | Age, race, gender breakdowns by SOC | MSA |

**Query pattern** (via pyghtcast):
```python
from pyghtcast.lightcast import Lightcast

lc = Lightcast(username, password)
query = lc.build_query_corelmi(columns, constraints)
df = lc.query_corelmi(dataset, query, datarun)
```

Constraints filter by Area (MSA code), Industry (NAICS codes), or Occupation (SOC codes).

### Lightcast JPA API (Job Posting Analytics)

Authentication: OAuth with scope `postings:us`. Base URL: `https://emsiservices.com/jpa/`

**Current status**: `JobPostingsConnection` class exists in pyghtcast but is broken — missing `base_url` and `scope` in `__init__`. Needs a 2-line fix in `/home/ammar/Documents/projects/work/pyghtcast/pyghtcast/base.py` plus a wrapper class in `lightcast.py`.

**Required fix**:
```python
# base.py line 194-195, add to __init__:
self.base_url = "https://emsiservices.com/jpa/"
self.scope = "postings:us"
self.get_new_token()
self.name = "US_Postings"
```

| Endpoint | Used for | Key parameters |
|---|---|---|
| `post_totals(payload)` | Total postings, unique companies, salary median | NAICS filter, MSA filter |
| `post_rankings(facet, payload)` | Top skills, top employers, education breakdown | facet: `hard_skills`, `company`, `edulevels` |
| `post_timeseries(payload)` | Monthly posting volume, salary trends | date range |

**JPA filter payload example**:
```json
{
  "filter": {
    "when": {"start": "2025-04", "end": "2026-04"},
    "naics2": ["62"],
    "msa": ["19100"]
  },
  "rank": {"by": "unique_postings", "limit": 15}
}
```

### Manual Excel Fallback

When JPA API is unavailable, the tool reads pre-downloaded Lightcast exports:

| File | Sheets used | Data extracted |
|---|---|---|
| `overview.xls` | Sheet 2 (summary) | Monthly avg jobs posted |
| | Sheet 3 (employment) | Current employed, 3-year growth |
| | "Demand" sheet | Top 8 employers |
| | "Occ Age Breakdown" | Age demographics |
| | "Occ Race Ethnicity Breakdown" | Race/ethnicity demographics |
| | "Occ Gender Breakdown" | Gender demographics |
| `jpa.xls` | Sheet 2 (executive summary) | Employers competing count |
| | "Advertised Salary Trend" | Salary trend data |
| | "Top Specialized Skills" | Top 15 skills |
| `occ.csv` | All rows | SOC, description, openings, median earnings, jobs |

These files are the standard Lightcast report exports downloaded from the web UI. They use legacy `.xls` format (read via `xlrd`).

---

## Configuration

TOML format. One file per industry/region combination.

```toml
[report]
name = "Healthcare"                    # Used in output filename and sheet titles
output_dir = "./output"

[industry]
naics_codes = [                        # 4-digit NAICS codes for the industry
    "6211", "6212", "6213", "6214", "6215", "6216", "6219",
    "6221", "6222", "6223", "6231", "6232", "6233", "6239",
    "6241", "6242", "6243",
]
label = "Healthcare Industries"        # Aggregation label for Lightcast queries

[occupation]
soc_codes = [                          # SOC codes for key occupations to track
    "29-1141", "29-1171", "31-1128", "31-1131", "31-9092",
    "43-6013", "11-9111", "29-2061", "31-9091", "29-2018",
    "29-1292", "29-2034", "31-9097", "29-2072", "29-2099",
]
label = "Healthcare Occupations"

[geography]
msa_code = "19100"                     # Lightcast MSA code
msa_name = "Dallas-Fort Worth-Arlington, TX"
state_code = "48"                      # For state-level comparison
living_wage = 23.36                    # Hourly living wage threshold for flagging

[manual_inputs]                        # All optional. Paths to Lightcast Excel downloads.
overview_xls = ""                      # Set to file path to enable manual fallback
jpa_xls = ""
occ_csv = ""
```

**To create a new industry report**: copy a config file, change the NAICS codes, SOC codes, and label. Everything else stays the same for DFW reports.

---

## Architecture

```
industry-report-generator/
├── flake.nix                        # Nix dev environment (Python 3.13, uv)
├── pyproject.toml                   # uv project with dependencies
├── configs/
│   ├── healthcare_dfw.toml          # Healthcare config
│   └── aerospace_dfw.toml           # Aerospace config (example)
└── src/industry_report/
    ├── __init__.py
    ├── cli.py                       # Entrypoint: --config flag
    ├── config.py                    # TOML loader → ReportConfig dataclass
    ├── fetch_corelmi.py             # Core LMI queries (industry, occupation, demographics)
    ├── fetch_postings.py            # JPA queries (skills, employers, salary, postings)
    ├── read_manual.py               # Fallback Excel reader
    ├── build.py                     # Assemble API + fallback data → output sheet frames
    └── export.py                    # dclmic_export → formatted Excel workbook
```

### Data flow

```
config.toml
    │
    ├──→ fetch_corelmi.py ──→ industry data (3 geo levels)
    │                     ──→ occupation data (MSA)
    │                     ──→ demographic data (MSA)
    │
    ├──→ fetch_postings.py ──→ skills, employers, salary, postings (MSA)
    │         │
    │         └──→ (on failure) read_manual.py ──→ same data from Excel files
    │
    └──→ build.py ──→ 6 output DataFrames (one per sheet)
              │
              └──→ export.py ──→ formatted .xlsx workbook
```

### Fallback logic

For each output sheet, `build.py` checks data sources in order:

1. API data available → use it
2. API failed/unavailable → check if manual Excel file was provided → use it
3. Neither available → skip the sheet (workbook still generates with remaining sheets)

This means:
- **With JPA + Core LMI**: All 6 sheets generated, zero manual work
- **With Core LMI only + manual Excel**: All 6 sheets (Core LMI for tables 1-2, demographics 6; manual for 3-5)
- **With Core LMI only, no Excel**: Sheets 1, 2, 6 only (occupational employment, wage analysis, demographics)

---

## Dependencies

```toml
[project]
name = "industry-report-generator"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pandas>=2.3.2",
    "openpyxl>=3.1.5",
    "xlrd>=2.0.1",          # For reading legacy .xls fallback files
    "pyghtcast",             # Lightcast API wrapper
    "dclmic-export",         # Excel export with auto-formatting
]

[tool.uv.sources]
pyghtcast = { git = "https://github.com/Dallas-College-LMIC/pyghtcast" }
dclmic-export = { git = "https://github.com/Dallas-College-LMIC/dclmic-export" }
```

Dev environment via Nix flake (pattern from `report-framework/flake.nix`): Python 3.13, uv, ruff, pylsp.

---

## Prerequisite: pyghtcast Fix

Before building this tool, the `JobPostingsConnection` class in pyghtcast needs to be fixed. The class has all the methods implemented but is missing initialization of `base_url` and `scope`, making it non-functional.

**File**: `/home/ammar/Documents/projects/work/pyghtcast/pyghtcast/base.py`
**Change**: Add `base_url`, `scope`, `get_new_token()`, and `name` to `JobPostingsConnection.__init__`

**File**: `/home/ammar/Documents/projects/work/pyghtcast/pyghtcast/lightcast.py`
**Change**: Add a `JobPostings` wrapper class exposing `post_totals`, `post_rankings`, `post_timeseries`

This is a ~10-line change across 2 files in the pyghtcast library. The `JPA` credential access (`postings:us` scope) also needs to be confirmed with Lightcast.

---

## Future Extensions

These are explicitly out of scope for v1 but the architecture should not preclude them:

- **ZIP-level spatial module**: Reintroduce the report-framework's ZIP-level API pipeline for map generation. Would add `fetch_zip_industry.py`, `fetch_zip_occupation.py`, `fetch_census.py` modules.
- **Education & credential alignment**: Add a completions data source (Lightcast or THECB) and a new output sheet matching the aero report's CIP code table.
- **Additional JPA sheets**: Education breakdown, experience breakdown, advertised salary trend (monthly) — all available from JPA but not in current report templates.
- **Multi-region support**: Run the same industry config against different MSAs.
- **Report document generation**: Use output Excel as input to a Word/PDF template.

# Pulse Data Sources — Frequently-Updated Economic Indicators

**Date**: 2026-05-07
**Status**: Complete

## Context

The industry-report-generator currently produces static, point-in-time industry reports from Lightcast data. The dashboard (Streamlit) shows MSA-level report sheets and ZIP-level spatial analysis — both built from batch-fetched data that updates quarterly at best.

Stakeholders (workforce boards, economic development councils, employers, college leadership, students) need **current signals** between annual reports. This plan adds a "Pulse" tab to the dashboard that surfaces frequently-updated economic data from free public APIs plus the existing Lightcast job postings data, all auto-filtered to the industry and geography from the TOML config.

### Stakeholder questions the pulse tab answers

| Question | Sources that answer it |
|---|---|
| "Should we launch a new training program for healthcare?" | JPA (postings volume, skills in demand) + BFS (business formation rising?) + Dallas Fed (employers struggling to hire?) + BLS CES (jobs actually growing?) |
| "Are layoffs about to spike in construction?" | WARN notices (any filings?) + UI claims (trending up?) + Dallas Fed (employment index negative?) |
| "Is DFW outperforming Texas/the US?" | BLS CES + BFS + UI claims — all with state/national comparison |
| "Should a student enroll in this program?" | JPA (employers actively hiring, skills demanded) + BLS CES (jobs exist) + UI claims (sector isn't contracting) + Dallas Fed (employers hiring) + sales tax (local economy healthy) |
| "What skills are employers looking for right now?" | JPA (in-demand skills, specialized skills, software skills) |

### Approach: maximalist first iteration

Wire all 9 data sources (including the existing Lightcast job postings). Ship the full spread, see what stakeholders actually use, refine based on feedback.

---

## Data Source Inventory

### Tier 0 — Existing stack, new surface

#### 1. Lightcast Job Postings (JPA)

The strongest single source already in the stack — daily ingestion + dedup, bi-weekly enrichment refresh. Currently buried in the MSA-Level Report tab behind a "Generate Report" button. Needs to be a first-class pulse indicator.

| Aspect | Detail |
|---|---|
| **Access** | Already wired via `fetch_postings.py` (JPA API) + `read_manual.py` (Excel fallback) |
| **Cadence** | Daily ingestion, bi-weekly enrichment refresh |
| **API** | Lightcast JPA (`postings:us` scope) — currently unavailable for our credentials |
| **Fallback** | Manual `.xls` export from Lightcast web UI via `read_manual.py` |
| **Existing functions** | `fetch_totals()` (unique postings, companies, salary), `fetch_top_skills()`, `fetch_top_employers()`, `fetch_salary_trend()` |
| **Manual fallbacks** | `read_jpa_totals()`, `read_employers()`, `read_skills()`, `read_salary_trend()`, `read_employers_competing()` |
| **Env vars** | `LCAPI_USER`, `LCAPI_PASS` (already configured) |

**What this adds to Pulse:** Job posting volume trend over time, unique employers competing for talent, advertised salary trend, in-demand skills — all specific to the configured NAICS codes and MSA. This is the most industry-specific signal in the entire pulse dashboard; every other source is regional/state-level. The JPA data is the one that answers "what's happening in *this* industry right now?"

**Constraint:** JPA API scope (`postings:us`) is currently unavailable. All JPA data flows through manual Excel fallbacks. The pulse tab should call the same code path (`build.py` → `read_manual.py`) and surface whatever's available.

### Tier 1 — Easy (REST APIs, free, well-documented)

#### 2. FRED API (Aggregator)

The single most valuable *new* integration. One API key gets you UI claims, Dallas Fed survey series, Census BFS, and more.

| Aspect | Detail |
|---|---|
| **Access** | Free. Register at `fredaccount.stlouisfed.org` → instant 32-char API key |
| **Rate limits** | 120 requests/min with key |
| **Python library** | `fredapi` (mature, returns pandas Series/DataFrame) |
| **Key series** | `TXICLAIMS` (initial UI claims TX), `TXCCLAIMS` (continued claims TX), `TXINSUREDUR` (insured unemployment rate TX), ~160 Dallas Fed TMOS/TSSOS/TROS series, BFS series (release rid=443) |
| **Env var** | `FRED_API_KEY` |

#### 3. Texas WARN Act Notices (Socrata)

Daily, leading indicator — Dallas Fed research shows WARN spikes precede unemployment bumps by ~2 months.

| Aspect | Detail |
|---|---|
| **Access** | Free on Texas Open Data Portal via Socrata (SODA API) |
| **Dataset ID** | `8w53-c4f6` on `data.texas.gov` |
| **API** | Socrata SODA — JSON/CSV/GeoJSON, SoQL query language |
| **Auth** | Optional app token (free) for higher rate limits; works without one |
| **Python library** | `sodapy` or plain `pandas.read_csv()` on export URL |
| **Fields** | `notice_date`, `job_site_name`, `county_name`, `wda_name`, `total_layoff_number`, `layoff_date`, `city_name` |
| **Env var** | `SOCRATA_APP_TOKEN` (optional) |

#### 4. Texas UI Claims via FRED

Weekly, near real-time. Three FRED series IDs cover the full picture.

| Aspect | Detail |
|---|---|
| **Series IDs** | `TXICLAIMS`, `TXCCLAIMS`, `TXINSUREDUR` |
| **Cadence** | Weekly |
| **Integration** | Same `fredapi` call as FRED general |

#### 5. Dallas Fed Outlook Surveys

Monthly sentiment/expectations data. Available via two paths: FRED series (easiest) or direct XLS download from Dallas Fed website (full detail).

| Aspect | Detail |
|---|---|
| **FRED releases** | rid=374 (Manufacturing), rid=376 (Service Sector), rid=377 (Retail) |
| **Direct downloads** | `dallasfed.org/research/surveys/tmos/data` → index.xls, index_sa.xls (unadjusted + seasonally adjusted, back to June 2004) |
| **Service sector** | `dallasfed.org/research/surveys/tssos/data` → same format |
| **Workforce relevance** | Survey includes hiring difficulties, labor shortages, recruitment strategies |
| **Integration** | `fredapi` for key indexes; `pandas.read_excel()` for full breakdown |

#### 6. Texas Comptroller Sales Tax Allocations (Socrata)

Monthly (2-month real-economy lag). Proxy for consumer/commercial activity, especially retail/hospitality/construction.

| Aspect | Detail |
|---|---|
| **Access** | Free via Texas Open Data Portal (Socrata SODA API) |
| **Dataset IDs** | `qsh8-tby8` (County/MTA/SPD allocations), `vfba-b57j` (City allocations) |
| **API** | Same Socrata infrastructure as WARN notices |
| **Python library** | `sodapy` (shared with WARN) |
| **DFW counties** | Filter by Dallas, Tarrant, Collin, Denton |
| **Env var** | `SOCRATA_APP_TOKEN` (shared with WARN) |

### Tier 2 — Moderate effort

#### 7. Census Business Formation Statistics (BFS)

Monthly, 11-12 day lag. Leading indicator for new business activity and future job creation.

| Aspect | Detail |
|---|---|
| **Access** | Free via Census API (no key required for basic access) |
| **API endpoint** | `api.census.gov/data/timeseries/eits/bfs` |
| **Python** | `requests.get()` or `censusdis` (already in stack for ZIP-level) |
| **Also on FRED** | Key BFS series mirrored on FRED (release rid=443) — can use `fredapi` instead |
| **Granularity** | By NAICS sector, by state, by county |

#### 8. BLS Metro CES (DFW Nonfarm Payroll by Industry)

Monthly, 6-7 week lag. Authoritative employment counts — the "official number."

| Aspect | Detail |
|---|---|
| **Access** | Free via BLS Public Data API v2 (requires registration key) |
| **Auth** | Register at BLS website → email confirms API key. V1 = 25 queries/day (no key), V2 = 500 queries/day (free key) |
| **Python** | `requests.post('https://api.bls.gov/publicAPI/v2/timeseries/data/', ...)` or `bls` / `bls-api` packages |
| **Series IDs** | Format: `SMSU19100000000000001` — need to look up specific NAICS-industry series for MSA 19100 |
| **Caveat** | ~900 employment/hours/earnings series discontinued with Jan 2026 release. Must verify which DFW series survived |
| **Also on FRED** | Some BLS series mirrored on FRED — may be able to use `fredapi` instead |
| **Env var** | `BLS_API_KEY` |

### Tier 3 — Harder / deferred

#### 9. TWC Weekly Claims by County / Industry

The industry-cut data would be directly usable but there's no clean API.

| Aspect | Detail |
|---|---|
| **Access** | Published on TWC data-reports page as downloadable files |
| **API** | None found. Would need web scraping |
| **URL** | `twc.texas.gov/data-reports/unemployment-data` → "UI Claims by County" |
| **Alternative** | BLS LAUS has county-level data via BLS API but monthly, not weekly |
| **Decision** | Defer. Start with FRED state-level UI claims, add county/industry cuts later if stakeholders ask |

---

## Dashboard Design: "Pulse" Tab

A new third tab alongside "MSA-Level Report" and "ZIP-Level Spatial":

```
st.tabs(["MSA-Level Report", "ZIP-Level Spatial", "Pulse"])
```

### Layout

1. **Key Metrics Bar** — job postings count, employers competing, latest UI claims, 30-day WARN count, latest Dallas Fed employment index, latest BLS jobs number, monthly BFS change, sales tax YoY
2. **Job Posting Activity Panel** — posting volume trend, unique employers, advertised salary trend, in-demand skills (all from existing Lightcast JPA data, industry-specific)
3. **Labor Market Stress Panel** — UI claims trend (2-3 years) + WARN notices over time + Dallas Fed employment index overlay
4. **Economic Activity Panel** — BLS employment trend + BFS business applications + sales tax allocations by county
5. **Employer Sentiment Panel** — Dallas Fed survey results (manufacturing + service sector indexes, hiring difficulty question)
6. **Recent WARN Notices Table** — filterable, recent 90 days, highlight sector-relevant entries matching config NAICS codes

All auto-filtered to the industry/geography from TOML config where possible:
- NAICS codes → filter BFS/BLS by sector **+ job postings (already filtered by JPA payload)**
- Counties (Dallas, Tarrant, Collin, Denton) → filter sales tax/WARN
- State (TX) → filter UI claims, Dallas Fed

---

## Implementation Steps

### Phase 0 — Infrastructure

- [x] **Add new dependencies to `pyproject.toml`**
  - `fredapi` — FRED API (covers UI claims, Dallas Fed, BFS)
  - `sodapy` — Socrata API (covers WARN notices, TX sales tax)
  - Add `[project.optional-dependencies] pulse = ["fredapi", "sodapy"]`
  - Or make them part of the `dashboard` extra since pulse is dashboard-only

- [x] **Add API key env vars to `.env` and `cli.py`**
  - `FRED_API_KEY` — required
  - `BLS_API_KEY` — optional (can use FRED mirrors instead)
  - `SOCRATA_APP_TOKEN` — optional (works without, just lower rate limits)
  - Update `_load_env()` in `cli.py` to document new vars
  - Add to `.env.example` (not `.env` which is gitignored)

- [x] **Create `src/industry_report/fetch_pulse.py`** — new module
  - One function per data source, each returns `pd.DataFrame | None`
  - Every function wrapped in `try/except`, returns `None` on failure (follows existing API-first pattern)
  - All functions accept `config: ReportConfig` so they can use `config.msa_code`, `config.state_code`, `config.naics_codes`, etc.

- [x] **Update `AGENTS.md`** with pulse module documentation

### Phase 0.5 — Lightcast Job Postings (existing stack)

- [ ] **Add job posting pulse fetcher to `fetch_pulse.py`**
  - `fetch_job_posting_pulse(config)` — calls existing `fetch_totals()`, `fetch_top_employers()`, `fetch_top_skills()`, `fetch_salary_trend()` from `fetch_postings.py`
  - Falls back to `read_manual.py` functions: `read_jpa_totals()`, `read_employers()`, `read_skills()`, `read_salary_trend()`, `read_employers_competing()`
  - Returns a dict of DataFrames: `"posting_totals"`, `"top_employers"`, `"top_skills"`, `"salary_trend"`, `"employers_competing"`
  - Follows the same API-first, manual-fallback, return-None-on-failure pattern as `build.py`

- [ ] **Write tests for job posting pulse fetcher**
  - Mock `fetch_postings` functions to test the pulse wrapper
  - Mock `read_manual` functions to test fallback chain
  - Test that all-None (no JPA access, no manual files) returns gracefully

### Phase 1 — FRED API (highest value, covers 3 sources)

- [x] **Implement `fetch_fred_series()` in `fetch_pulse.py`**
  - Generic helper: takes a FRED series ID (or list), returns DataFrame with date + value columns
  - Uses `fredapi` with `FRED_API_KEY` env var
  - Handles missing key gracefully (returns `None`, logs warning)

- [x] **Implement `fetch_ui_claims()`**
  - Calls `fetch_fred_series()` for `TXICLAIMS`, `TXCCLAIMS`, `TXINSUREDUR`
  - Returns a DataFrame with weekly observations, last 2-3 years
  - Derives: 4-week moving average, YoY percent change

- [x] **Implement `fetch_dallas_fed_surveys()`**
  - Two paths:
    - (a) FRED series IDs for key indexes (general business activity, employment, production, prices) via `fetch_fred_series()`
    - (b) Direct XLS download from `dallasfed.org/research/surveys/tmos/data` for full detail including special questions
  - Returns DataFrame with monthly index values, last 2-3 years
  - Cover both Manufacturing (TMOS) and Service Sector (TSSOS)

- [x] **Implement `fetch_bfs()`**
  - Primary: Census API endpoint `api.census.gov/data/timeseries/eits/bfs`
  - Fallback: FRED BFS series
  - Filter by state (TX) and sector where possible
  - Returns DataFrame with monthly business application counts

- [x] **Write tests for FRED-based fetchers**
  - Mock `fredapi.Fred` to avoid network calls
  - Test `fetch_ui_claims()` with mock series data
  - Test `fetch_dallas_fed_surveys()` with mock data
  - Test graceful failure when `FRED_API_KEY` is missing

### Phase 2 — Socrata API (covers 2 sources)

- [x] **Implement `fetch_warn_notices()` in `fetch_pulse.py`**
  - Uses `sodapy.Socrata("data.texas.gov", app_token)` or falls back to `pandas.read_csv()`
  - Dataset ID: `8w53-c4f6`
  - SoQL filter: `where="layoff_date > '2025-01-01'"` (last ~18 months)
  - Filter to DFW-relevant counties (Dallas, Tarrant, Collin, Denton, Ellis, Rockwall, Kaufman, Johnson)
  - Returns DataFrame with notice_date, company, county, layoff_count, layoff_date
  - Derives: monthly aggregate, 30-day rolling count

- [x] **Implement `fetch_sales_tax()` in `fetch_pulse.py`**
  - Uses `sodapy` on `data.texas.gov`
  - Dataset ID: `qsh8-tby8` (County/MTA/SPD)
  - Filter to DFW counties: Dallas, Tarrant, Collin, Denton
  - Returns DataFrame with monthly allocation amounts by county
  - Derives: YoY percent change, county comparison

- [x] **Write tests for Socrata-based fetchers**
  - Mock `sodapy.Socrata` client
  - Test WARN filtering by county and date range
  - Test sales tax filtering by county
  - Test graceful failure when `SOCRATA_APP_TOKEN` is missing (should still work)

### Phase 3 — BLS API

- [x] **Implement `fetch_bls_employment()` in `fetch_pulse.py`**
  - Uses BLS API v2 (`api.bls.gov/publicAPI/v2/timeseries/data/`)
  - Need to first discover which DFW MSA series IDs survived the Jan 2026 discontinuation
  - Fallback: use FRED if BLS series are mirrored there
  - Returns DataFrame with monthly employment by industry, last 2-3 years
  - Derives: monthly change, YoY change

- [x] **Discover surviving BLS series IDs for DFW MSA 19100**
  - Check which NAICS industry detail series exist post-Jan 2026
  - Document the working series IDs
  - If too many were discontinued, consider using state-level BLS series as fallback

- [x] **Write tests for BLS fetcher**
  - Mock BLS API response
  - Test with known series IDs
  - Test graceful failure

### Phase 4 — Build Pulse Sheets

- [x] **Create `src/industry_report/build_pulse.py`** — new module
  - `build_pulse_data(config) -> dict[str, pd.DataFrame]` — calls all fetchers, assembles DataFrames
  - Does NOT return OrderedDict of "sheets" — instead returns a dict of named DataFrames for the dashboard to render directly
  - Each key is a section name: `"job_postings"`, `"ui_claims"`, `"warn_notices"`, `"dallas_fed"`, `"sales_tax"`, `"bfs"`, `"bls_employment"`
  - All fetcher calls wrapped in try/except; missing sources simply don't appear

- [x] **Derive cross-source metrics**
  - "Labor Market Stress Index" — composite of UI claims trend + WARN count + Dallas Fed employment index
  - YoY comparisons for everything
  - Sector relevance tagging — match WARN notice companies/industries to config NAICS codes where possible

### Phase 5 — Dashboard Pulse Tab

- [x] **Add "Pulse" tab to `dashboard.py`**
  - `st.tabs(["MSA-Level Report", "ZIP-Level Spatial", "Pulse"])`

- [x] **Implement Key Metrics Bar**
  - `st.columns(8)` with `st.metric()` for:
    - **Job postings (monthly avg)** — from Lightcast JPA
    - **Employers competing** — unique companies posting
    - Latest initial UI claims (+ WoW change)
    - 30-day WARN notice count
    - Dallas Fed employment index (latest)
    - DFW employment level (BLS, latest)
    - Monthly BFS change
    - Sales tax YoY change (Dallas County)
  - Each metric shows `—` if data unavailable

- [x] **Implement Job Posting Activity Panel**
  - Plotly line chart: Advertised salary trend over time (from `read_salary_trend` / `fetch_salary_trend`)
  - Plotly dual-axis chart: Posting volume + unique employers over time (from `read_jpa_totals` / `fetch_totals`)
  - Top skills bar chart (from `read_skills` / `fetch_top_skills`)
  - Top employers bar chart (from `read_employers` / `fetch_top_employers`)
  - This is the most industry-specific panel — everything here is filtered to config NAICS + MSA
  - Falls back gracefully if JPA API is down and no manual files are configured (show info message)

- [x] **Implement Labor Market Stress Panel**
  - Plotly line chart: UI initial claims + 4-week moving average (2-3 year history)
  - Plotly bar chart: Monthly WARN notice count over time
  - Overlay: Dallas Fed employment index on secondary axis
  - Annotations for notable events (COVID, recessions) if dates are known

- [x] **Implement Economic Activity Panel**
  - Plotly line chart: BLS DFW employment trend (monthly)
  - Plotly line chart: BFS business applications for TX (monthly)
  - Plotly grouped bar chart: Sales tax allocations by DFW county (monthly)

- [x] **Implement Employer Sentiment Panel**
  - Dallas Fed survey results table (latest month vs. previous vs. series average)
  - Plotly multi-line chart: Manufacturing + Service Sector key indexes over time
  - Highlight hiring difficulty / labor shortage special questions when available

- [x] **Implement Recent WARN Notices Table**
  - `st.dataframe()` with recent 90 days of WARN filings
  - Filterable by county
  - Highlight rows where the company/industry may match config NAICS (best-effort string matching)
  - Show: company name, county, layoff count, notice date, layoff date

- [x] **Add data freshness indicators**
  - Each section shows "Last updated: [date]" from the most recent observation
  - Job postings: show enrichment refresh date if available
  - If data is > 2 periods stale, show a warning

### Phase 6 — Polish & Deploy

- [x] **Add caching to pulse fetchers**
  - Use `@st.cache_data(ttl=...)` in the dashboard for each pulse fetcher
  - Job postings: cache 1 day
  - UI claims: cache 1 day (weekly data)
  - WARN notices: cache 1 day
  - Dallas Fed: cache 1 day (monthly data)
  - BLS/BFS: cache 1 day
  - Sales tax: cache 1 day

- [x] **Handle missing API keys gracefully in dashboard**
  - If `FRED_API_KEY` not set: show info message, still render Socrata-based panels
  - If `SOCRATA_APP_TOKEN` not set: still works (just lower rate limits)
  - If all keys missing: show setup instructions in the Pulse tab

- [x] **Update `pyproject.toml` for Streamlit Community Cloud deployment**
  - Ensure `fredapi` and `sodapy` are in the `dashboard` optional dependency group
  - Add `FRED_API_KEY` and `SOCRATA_APP_TOKEN` to Streamlit Cloud secrets docs

- [x] **Write integration tests**
  - Test the full pulse pipeline with mocked API responses
  - Test dashboard rendering with fixture pulse data
  - Test graceful degradation when individual sources fail

- [x] **Update `AGENTS.md`** — final pass

---

## New File Layout

```
src/industry_report/
  cli.py                       ← add FRED_API_KEY, SOCRATA_APP_TOKEN to env docs
  config.py                    ← unchanged (may add DFW county list helper)
  fetch_pulse.py               ← NEW: all pulse data fetchers (incl. job posting wrapper)
  build_pulse.py               ← NEW: assemble pulse DataFrames for dashboard
  dashboard.py                 ← add Pulse tab with 6 panels + key metrics bar
  fetch_postings.py            ← existing, called by fetch_pulse.py
  read_manual.py               ← existing, called by fetch_pulse.py as fallback
  ...existing modules...
```

## New Dependencies

| Package | Purpose | Covers |
|---------|---------|--------|
| `fredapi` | FRED API wrapper | UI claims, Dallas Fed surveys, BFS (mirror), BLS (mirror) |
| `sodapy` | Socrata API client | WARN notices, TX sales tax allocations |

No new dependency needed for job postings — it reuses the existing `fetch_postings.py` and `read_manual.py` code paths.

## Required API Keys

| Key | Registration | Env var | Required? |
|-----|-------------|---------|-----------|
| FRED API key | `fredaccount.stlouisfed.org` (instant) | `FRED_API_KEY` | Yes (covers 4+ sources) |
| BLS API key | `data.bls.gov/registrationEngine/` (email) | `BLS_API_KEY` | No (can use FRED mirrors) |
| Socrata app token | `data.texas.gov/profile/app_tokens` | `SOCRATA_APP_TOKEN` | No (works without, lower rate limits) |
| Lightcast credentials | Dallas College LMIC internal | `LCAPI_USER` / `LCAPI_PASS` | Already configured |

## Risks / Open Questions

- **JPA API scope unavailable**: `postings:us` scope is not available with current credentials. All JPA data flows through manual Excel fallbacks. The pulse tab must handle the case where no manual files are configured (show info message, not crash).
- **BLS Metro CES discontinuations**: ~900 series were cut in Jan 2026. Need to verify which DFW industry series still exist before building UI around them. May need to fall back to state-level BLS data.
- **TWC county/industry UI claims**: No API found. Deferred to a future iteration. State-level via FRED is the starting point.
- **Dallas Fed special questions**: The hiring-difficulty questions appear intermittently (not every month). Need to handle missing data gracefully.
- **NAICS-to-WARN matching**: WARN notices list company names and counties but not NAICS codes. Matching to config industries will be approximate (keyword matching or manual mapping).
- **Rate limits**: FRED is generous (120/min). Socrata is fine with app token. BLS is the tightest (500/day for v2). Dashboard caching mitigates all of these.
- **Data freshness on Streamlit Cloud**: The dashboard re-runs on each page load. `@st.cache_data(ttl=...)` prevents hitting APIs on every load, but the first load after cache expiry will be slow if all sources are fetched sequentially.

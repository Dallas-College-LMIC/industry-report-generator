# Remaining Tasks

## JPA API Access

Current Lightcast credentials only have Core LMI scope (`agnitio`). Job Posting Analytics (`postings:us`) returns `invalid_client`. All JPA-dependent sheets fall back to manual Excel files.

- [ ] Request JPA scope from Lightcast (or get separate JPA credentials)
- [ ] Test all `fetch_postings.py` functions once access is granted
- [ ] Wire `fetch_salary_trend()` into build pipeline (function exists but isn't called)

## Untested Manual Fallbacks

These `read_manual.py` functions exist but have never been tested against real files:

- [ ] `read_employers()` — reads top employers from overview.xls 'Demand' sheet
- [ ] `read_skills()` — reads specialized skills from jpa.xls
- [ ] `read_salary_trend()` — reads advertised wage trend from jpa.xls
- [ ] `read_demographics()` — reads age/race/gender breakdowns from overview.xls
- [ ] `read_employers_competing()` — reads employer competition count from jpa.xls
- [ ] `read_occ_csv()` — reads occupation data from CSV fallback

Need to test with actual Lightcast export files from a real report.

## Regional Comparison Enhancements

The report frame shows additional metrics we don't pull yet:

- [ ] Job Postings (Monthly Avg) — requires JPA or manual overview.xls
- [ ] Postings per 1,000 Jobs — derived from postings + jobs
- [ ] Demographic comparisons (racial/ethnic diversity) across DFW/Texas/US
- [ ] Report frame shows "Projected Job Growth (2020-2030)" with longer time horizon — currently we only compute 2026-2029

## Report Frame Alignment

The healthcare report's occupational employment table includes columns our tool doesn't produce:

- [ ] Typical Entry Level Education — available from BLS SOC definitions, not in Lightcast API
- [ ] Description column — currently using `soc_titles` from config, but the report uses longer descriptions

## Sheets That Need Manual Excel Test Files

To properly test the full pipeline, we need sample Lightcast export files:

- [ ] overview.xls (legacy .xls format) — employers, demographics, totals
- [ ] jpa.xls (legacy .xls format) — skills, salary trend, employer competition
- [ ] occ.csv — occupation fallback data

## Configuration & UX

- [ ] Validate TOML config (check SOC/NAICS codes are valid format, soc_codes and soc_titles are same length)
- [ ] Better error messages when API is unreachable (currently silent pass with no data)
- [ ] Progress logging — show which sheets succeeded/failed and from which source (API vs manual)
- [ ] Support multiple MSAs in one config (e.g., DFW + Houston comparison report)

## Education & Credential Alignment

Entirely new data source needed. Reports show CIP program completions at local colleges.

- [ ] Identify data source (IPEDS API, Lightcast, or manual NCES data)
- [ ] Build CIP code → industry/occupation mapping
- [ ] Create fetcher module for completions data
- [ ] Build "Education & Credential Alignment" sheet

## ZIP-Level Spatial Module

Separate module from MSA-level tables. Report-framework already has working implementation (`geometry-discovery` agent, `censusdis`, geography manifests) that can be ported or referenced.

- [ ] Port `censusdis` integration for Census/ACS data at ZCTA level
- [ ] Port geography manifest system (define ZIPs per MSA/industry)
- [ ] Build `Industry_by_ZIP` sheet (jobs, earnings per ZIP)
- [ ] Build `Occupations_by_ZIP` sheet (occupation jobs/wages per ZIP)
- [ ] Build `Top_ZIPs` sheet (employment concentration, per capita rates)
- [ ] Build `Census_Context` sheet (demographics by ZIP)
- [ ] Shapefile output for GIS/mapping

## Out of Scope (Defer Indefinitely)

- **Narrative/analysis sections** — Industry Overview, Policy & Priorities, Technology Transformation, Future Outlook are written by analysts, not automated.

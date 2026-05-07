# Dallas College LMIC — Industry Report Content Specification

## Purpose

This document defines the standard content structure for Dallas College Labor Market Intelligence Center (LMIC) industry reports. It specifies what data appears in each section, where that data comes from, and what can be automated versus what requires analyst writing.

This spec is industry-agnostic. The same structure applies to Healthcare, Aerospace, Arts, or any other NAICS sector — only the industry codes and occupation codes change.

---

## Report Inputs

Every industry report is defined by three inputs:

1. **Industry codes (NAICS)** — which industries to include (e.g., NAICS 62 for Health Care and Social Assistance)
2. **Occupation codes (SOC)** — which occupations to highlight (e.g., Registered Nurses, Medical Assistants)
3. **Region** — the metropolitan area (e.g., Dallas-Fort Worth-Arlington, TX MSA)

All data in the report flows from these three inputs.

---

## Report Sections

### 1. Industry Overview

**Purpose**: Set the stage — how big is this industry in the region, why does it matter, and what are the key dynamics?

**Data points**:
- Total industry employment in the MSA (Lightcast Industry data, current year)
- Estimated economic footprint / total earnings (Lightcast Industry data, total earnings)
- Industry's share of regional employment (derived: industry jobs ÷ total regional jobs)
- Key subsectors and their relative size (Lightcast Industry data by 4-digit NAICS)

**What's automatable**: All data points above. Pull from Lightcast industry dataset filtered by NAICS codes and MSA.

**What's manual**: The narrative framing — why this industry matters to DFW, qualitative context about growth drivers, recession resilience, structural trends. This requires analyst interpretation.

---

### 2. Employment Trends

**Purpose**: Show current employment levels across key occupations, projected growth, and where the demand pressure is.

**Data table — Occupational Employment**:

| Data point | Source |
|---|---|
| SOC code | Lightcast Occupation data |
| Occupation title | Lightcast Occupation data |
| Current year jobs (e.g., 2026) | Lightcast Occupation data, filtered by MSA + SOC codes |
| Projected change (e.g., 2026-2029) | Lightcast Occupation data (projected year jobs minus current year jobs) |
| Percent change | Derived from above |
| Average annual openings | Lightcast Occupation data (`Openings.2026` metric — pulled directly from LC, not aggregated from ZIP data) |
| Median hourly wage | Lightcast Occupation data (50th percentile earnings) |
| Typical entry-level education | Lightcast Occupation data |

**Living wage flag**: Any occupation with median hourly wage at or below the local living wage (currently $23.36/hr in Dallas County) should be flagged. The living wage threshold should be specified per report.

**What's automatable**: The entire table. All columns come from a single Lightcast Occupation query for the selected SOC codes in the MSA. The openings metric (`Openings.2026`) is a standard Lightcast field — no manual aggregation needed.

**What's manual**: Narrative analysis — which occupations face the most demand pressure, what's driving growth in specific roles, wage misalignment commentary.

---

### 3. Wage Analysis

**Purpose**: Show the wage distribution across key occupations, highlighting the range from entry-level to experienced workers.

**Data table — Wage Distribution**:

| Data point | Source |
|---|---|
| Occupation title | Lightcast Occupation data |
| Entry wage (10th percentile hourly) | Lightcast Occupation data |
| Median wage (50th percentile hourly) | Lightcast Occupation data |
| Experienced wage (90th percentile hourly) | Lightcast Occupation data |
| Typical entry-level education | Lightcast Occupation data |
| Below living wage flag | Derived (median wage ≤ living wage threshold) |

**What's automatable**: The entire table. Same Lightcast occupation dataset as Employment Trends, different columns.

**What's manual**: Interpretation — wage compression issues, comparison to cost of living, implications for recruitment and retention.

---

### 4. Employer Landscape

**Purpose**: Identify who the major employers are in this industry in the region and how competitive the hiring environment is.

**Data table — Top Employers**:

| Data point | Source |
|---|---|
| Company name | Lightcast Job Posting Analytics (JPA), ranked by unique postings |
| Number of unique job postings | Lightcast JPA |

**Supporting metrics**:
- Total number of employers competing for talent (Lightcast JPA, unique companies count)
- Monthly average job postings in the industry (Lightcast JPA, posting volume)

**Default**: Top 8 employers by posting volume.

**What's automatable**: The employer ranking table and supporting metrics. All from Lightcast JPA filtered by NAICS codes and MSA.

**What's manual**: Narrative about the employer ecosystem — the role of large health systems vs. ambulatory providers, geographic concentration, competitive dynamics, how large systems set wage benchmarks. This is qualitative analysis that requires industry knowledge.

---

### 5. Skills and Competencies

**Purpose**: Show what skills employers are actually asking for in job postings, and how the skills landscape is evolving.

**Data table — In-Demand Specialized Skills**:

| Data point | Source |
|---|---|
| Skill name | Lightcast JPA, ranked by posting frequency |
| Number of postings mentioning this skill | Lightcast JPA |
| Percentage of total postings | Derived |

**Additional data** (if available from JPA):
- Top common/soft skills (separate ranking)
- Top software/technical skills (separate ranking)
- Projected skill growth rates

**Default**: Top 15 specialized skills.

**What's automatable**: All skill ranking tables from Lightcast JPA.

**What's manual**: Narrative about skills-based hiring trends, how skills connect to education programs, the shift from credentials to demonstrated competencies. Heavily analyst-driven.

---

### 6. Workforce Demographics

**Purpose**: Show the demographic composition of the current workforce in the selected occupations.

**Data tables**:

**6a. Age Breakdown**

| Data point | Source |
|---|---|
| Age group (e.g., 14-18, 19-24, 25-34...) | Lightcast Occupation Demographics |
| Number of jobs in age group | Lightcast Occupation Demographics |
| Percentage of total | Derived |

**6b. Race and Ethnicity Breakdown**

| Data point | Source |
|---|---|
| Race/ethnicity category | Lightcast Occupation Demographics |
| Number of jobs | Lightcast Occupation Demographics |
| Percentage of total | Derived |

**6c. Gender Breakdown**

| Data point | Source |
|---|---|
| Gender | Lightcast Occupation Demographics |
| Number of jobs | Lightcast Occupation Demographics |
| Percentage of total | Derived |

**What's automatable**: All three demographic tables from Lightcast occupation demographics data at the MSA level.

**What's manual**: Any diversity and inclusion analysis, comparison to regional population demographics, implications for pipeline development.

---

### 7. Regional Comparison

**Purpose**: Benchmark the MSA against state and national averages to show where the region is strong or constrained relative to peers.

**Data table**:

| Metric | DFW | Texas | United States |
|---|---|---|---|
| Total industry jobs | Lightcast Industry | Lightcast Industry | Lightcast Industry |
| Job postings (monthly avg) | Lightcast JPA | Lightcast JPA | Lightcast JPA |
| Postings per 1,000 jobs | Derived | Derived | Derived |
| Projected job growth | Lightcast Industry | Lightcast Industry | Lightcast Industry |
| Average earnings per job | Lightcast Industry | Lightcast Industry | Lightcast Industry |

**What's automatable**: The entire table. Same Lightcast queries run at three geography levels (MSA, state, nation).

**What's manual**: Analysis of what the comparison means — is DFW's labor market tighter than average? Is workforce supply keeping up with demand? What does higher posting intensity signal?

---

### 8. Education and Credential Alignment

**Purpose**: Show how well regional education programs are producing graduates to fill industry demand.

**Data table**:

| Data point | Source |
|---|---|
| CIP code | Lightcast or THECB (Texas Higher Education Coordinating Board) |
| Program name | Same |
| Annual completions (multi-year trend) | Same |
| Average annual openings for aligned occupation | Lightcast Occupation data |
| Gap (openings minus completions) | Derived |

**What's automatable**: The table structure and openings data. Completions data source is TBD — it may come from Lightcast's completions dataset or from THECB program reporting.

**What's manual**: Interpretation of gaps — whether a numeric gap represents real undersupply, narrative about career pathways (e.g., CNA → LVN → RN), Dallas College's specific program positioning.

**Note**: This section was present in the Aerospace report but empty in the Healthcare report. The data source for program completions needs to be identified before this can be standardized.

---

### 9. Policy and Priorities

**Purpose**: Describe the policy environment shaping workforce development for this industry.

**What's automatable**: Nothing. This is entirely analyst-written.

**Content typically includes**:
- Relevant state legislation (e.g., SJR 62, HB 3801, SB 2058 for healthcare)
- Federal regulatory changes affecting the industry
- THECB strategic direction and funding mechanisms
- Dallas College's positioning as a workforce intermediary
- Industry-specific regulatory bodies (e.g., Texas Board of Nursing, FAA Part 147)

---

### 10. Workforce Regulations and Training

**Purpose**: Describe the regulatory environment for workforce entry and advancement in the industry.

**What's automatable**: Nothing. This is entirely analyst-written.

**Content typically includes**:
- Licensure and certification requirements for key occupations
- State-level regulatory bodies and recent policy changes
- Training pathway structures (stackable credentials, apprenticeships)
- Dallas College's role in workforce pipeline development

---

### 11. Technology Transformation

**Purpose**: Describe how technology is reshaping the industry and its workforce implications.

**What's automatable**: Nothing. This is entirely analyst-written.

**Content typically includes**:
- Key technology trends affecting the industry
- Impact on workforce roles and skill requirements
- Implications for training and education programs

---

### 12. Future Outlook

**Purpose**: Forward-looking analysis of the industry's trajectory in the region.

**What's automatable**: Nothing. This is entirely analyst-written.

**Content typically includes**:
- 5-10 year demand projections
- Structural shifts in care delivery, workforce models, or industry structure
- Scenario analysis (optimistic vs. constrained)
- Recommendations for workforce strategy

---

## Summary: What's Automatable

| Section | Data table | Narrative |
|---|---|---|
| Industry Overview | **Automatable** | Manual |
| Employment Trends | **Automatable** | Manual |
| Wage Analysis | **Automatable** | Manual |
| Employer Landscape | **Automatable** | Manual |
| Skills and Competencies | **Automatable** | Manual |
| Workforce Demographics | **Automatable** | Manual |
| Regional Comparison | **Automatable** | Manual |
| Education & Credential Alignment | **Partially automatable** (openings yes, completions TBD) | Manual |
| Policy and Priorities | — | Manual |
| Workforce Regulations & Training | — | Manual |
| Technology Transformation | — | Manual |
| Future Outlook | — | Manual |

**Bottom line**: 7 out of 12 sections contain data tables that can be fully automated. The remaining 5 sections are entirely narrative. For the automatable sections, the data tables are produced by changing NAICS/SOC codes in a config file — no manual Lightcast downloads, no spreadsheet manipulation.

---

## Lightcast Data Sources (Non-Technical Summary)

| What we need | Lightcast product | What it gives us |
|---|---|---|
| Employment counts, wages, projections, education levels by occupation | **Occupation Overview / Staffing Patterns** | The core employment and wage tables |
| Industry-level employment, earnings, growth | **Industry Overview** | Industry size, economic footprint, regional comparison |
| Workforce age, race/ethnicity, gender | **Occupation Demographics** | Demographic breakdown tables |
| Job posting volume, top employers, top skills, advertised salaries | **Job Posting Analytics (JPA)** | Employer landscape, skills tables, regional comparison posting metrics |
| Program completions by CIP code | **Completions dataset** (or THECB) | Education alignment table (TBD) |

All of these are available as downloadable Excel reports from the Lightcast web interface. Most are also available via API, which enables full automation.

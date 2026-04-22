"""Assemble API and fallback data into output sheet frames."""

from collections import OrderedDict

import dclmic_export
import pandas as pd

from .config import ReportConfig
from .fetch_corelmi import fetch_occupation_data, fetch_regional_comparison
from .fetch_postings import (
    fetch_salary_trend,
    fetch_top_employers,
    fetch_top_skills,
    fetch_totals,
)
from .read_manual import (
    read_demographics,
    read_employers,
    read_employers_competing,
    read_jpa_totals,
    read_occ_csv,
    read_overview_totals,
    read_salary_trend as read_manual_salary_trend,
    read_skills,
)

# Column rename map: API column names → report-friendly names
OCCUPATION_COLUMN_MAP = {
    "Occupation": "SOC",
    "Area": None,  # drop
    "ClassOfWorker": None,  # drop
    "Jobs.2026": "2026 Jobs",
    "Jobs.2029": "2029 Jobs",
    "Openings.2026": "Avg. Annual Openings",
    "Earnings.Percentile10.2024": "Entry Wage (P10)",
    "Earnings.Percentile50.2024": "Median Hourly Wage",
    "Earnings.Percentile90.2024": "Experienced Wage (P90)",
}

# Map SOC codes to occupation titles for readability
SOC_TITLE_MAP = {}  # populated from config at build time


def _clean_occupation_df(df: pd.DataFrame, living_wage: float) -> pd.DataFrame:
    """Rename columns, compute derived fields, add living wage flag."""
    df = df.rename(columns=OCCUPATION_COLUMN_MAP)
    cols_to_drop = [c for c in df.columns if c is None]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    # Add occupation title from SOC code
    if "SOC" in df.columns and SOC_TITLE_MAP:
        df.insert(1, "Occupation", df["SOC"].map(SOC_TITLE_MAP))

    # Derived columns
    if "2026 Jobs" in df.columns and "2029 Jobs" in df.columns:
        df["2026-2029 Change"] = df["2029 Jobs"] - df["2026 Jobs"]
        df["% Change"] = (df["2026-2029 Change"] / df["2026 Jobs"]).round(4)

    if "Median Hourly Wage" in df.columns:
        df["Below Living Wage"] = df["Median Hourly Wage"] <= living_wage

    return df


def _build_occupations_sheet(config: ReportConfig, occ_api: pd.DataFrame | None) -> pd.DataFrame | None:
    """Build the Occupational Employment table."""
    if occ_api is not None and not occ_api.empty:
        return _clean_occupation_df(occ_api.copy(), config.living_wage)

    # Fallback to manual CSV
    csv_path = config.occ_csv if config.occ_csv else None
    return read_occ_csv(csv_path)


def _build_wage_sheet(config: ReportConfig, occ_api: pd.DataFrame | None) -> pd.DataFrame | None:
    """Build the Wage Analysis table from occupation data."""
    if occ_api is None or occ_api.empty:
        return None

    df = occ_api.copy()
    df = df.rename(columns=OCCUPATION_COLUMN_MAP)
    cols_to_drop = [c for c in df.columns if c is None]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    # Select wage-relevant columns only
    wage_cols = ["SOC", "Occupation", "Median Hourly Wage", "Entry Wage (P10)", "Experienced Wage (P90)"]
    available = [c for c in wage_cols if c in df.columns]
    if not available:
        return None

    df = df[available].copy()

    # Add occupation title if we have SOC but not Occupation
    if "SOC" in df.columns and "Occupation" not in df.columns and SOC_TITLE_MAP:
        df.insert(1, "Occupation", df["SOC"].map(SOC_TITLE_MAP))
    if "Median Hourly Wage" in df.columns:
        df["Below Living Wage"] = df["Median Hourly Wage"] <= config.living_wage

    return df.sort_values("Median Hourly Wage", ascending=False).reset_index(drop=True)


def _find_col(df: pd.DataFrame, *keywords) -> str | None:
    """Find first column name matching all keywords."""
    for col in df.columns:
        if all(kw in col for kw in keywords):
            return col
    return None


def _build_regional_comparison(
    config: ReportConfig, regional_api: dict | None, postings_totals: dict | None
) -> pd.DataFrame | None:
    """Build the Regional Comparison table: DFW vs Texas vs US."""
    if regional_api is None:
        return None

    rows = []

    # Jobs
    jobs_row = {"Metric": "Jobs (Total)"}
    for level, df in regional_api.items():
        col = _find_col(df, "Jobs", "2026")
        jobs_row[level] = df[col].sum() if col and not df.empty else None
    rows.append(jobs_row)

    # Earnings per job
    earnings_row = {"Metric": "Earnings per Job"}
    for level, df in regional_api.items():
        col_e = _find_col(df, "Earnings")
        col_j = _find_col(df, "Jobs", "2026")
        if col_e and col_j and not df.empty:
            total_earnings = df[col_e].sum()
            total_jobs = df[col_j].sum()
            earnings_row[level] = round(total_earnings / total_jobs, 2) if total_jobs else None
        else:
            earnings_row[level] = None
    rows.append(earnings_row)

    # Growth
    growth_row = {"Metric": "Projected Job Growth (2026-2029)"}
    for level, df in regional_api.items():
        col26 = _find_col(df, "Jobs", "2026")
        col29 = _find_col(df, "Jobs", "2029")
        if col26 and col29 and not df.empty:
            j26 = df[col26].sum()
            j29 = df[col29].sum()
            growth_row[level] = round((j29 - j26) / j26, 4) if j26 else None
        else:
            growth_row[level] = None
    rows.append(growth_row)

    # Posting metrics if available from JPA
    if postings_totals is not None:
        rows.append(
            {
                "Metric": "Job Postings (Monthly Avg)",
                "msa": postings_totals.get("unique_postings"),
                "state": None,
                "nation": None,
            }
        )

    df = pd.DataFrame(rows)
    col_map = {"msa": config.msa_name, "state": "Texas", "nation": "United States"}
    df = df.rename(columns=col_map)
    return df


def _build_employers_sheet(
    config: ReportConfig, api_employers: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Build Top Employers sheet."""
    if api_employers is not None and not api_employers.empty:
        return api_employers
    return read_employers(config.jpa_xls, config.overview_xls)


def _build_skills_sheet(config: ReportConfig, api_skills: pd.DataFrame | None) -> pd.DataFrame | None:
    """Build In-Demand Skills sheet."""
    if api_skills is not None and not api_skills.empty:
        return api_skills
    return read_skills(config.jpa_xls)


def _build_summary_sheet(
    config: ReportConfig,
    occ_api: pd.DataFrame | None,
    api_totals: dict | None,
) -> pd.DataFrame | None:
    """Build 'Did you know' summary sheet."""
    data = {}

    # Try API for total jobs
    if occ_api is not None and not occ_api.empty:
        jobs_col = _find_col(occ_api, "Jobs", "2026")
        if jobs_col:
            data["Total Jobs"] = int(occ_api[jobs_col].sum())

    # Try JPA for postings
    if api_totals is not None:
        data["Monthly Average Jobs Posted"] = api_totals.get("unique_postings")
    else:
        jpa_totals = read_jpa_totals(config.jpa_xls)
        if jpa_totals:
            data.setdefault("Monthly Average Jobs Posted", jpa_totals.get("unique_postings"))

    # Manual fallback
    manual_totals = read_overview_totals(config.overview_xls)
    if manual_totals:
        data.setdefault("Total Jobs", manual_totals["current_employed"])
        data.setdefault("Monthly Average Jobs Posted", manual_totals["monthly_avg_postings"])
        data["% 3-year Job Demand Growth Rate"] = manual_totals["three_yr_growth"]

    # Employers competing
    employers_competing = read_employers_competing(config.jpa_xls)
    if api_totals and "unique_companies" in api_totals:
        data["Employers Competing"] = api_totals["unique_companies"]
    elif employers_competing:
        data.setdefault("Employers Competing", employers_competing)

    if not data:
        return None

    return dclmic_export.dict_to_df_for_xl(data)


def build_all_sheets(config: ReportConfig) -> OrderedDict[str, pd.DataFrame]:
    """Main entry point: fetch all data and build output sheets.

    Returns an OrderedDict of sheet_name -> DataFrame. Sheets with no data are omitted.
    """
    sheets = OrderedDict()

    # Populate SOC title lookup from config
    global SOC_TITLE_MAP
    SOC_TITLE_MAP = dict(zip(config.soc_codes, config.soc_titles)) if config.soc_titles else {}

    # Fetch API data
    occ_api = None
    regional_api = None
    api_totals = None
    api_skills = None
    api_employers = None

    try:
        occ_api = fetch_occupation_data(config.soc_codes, config.msa_code)
    except Exception:
        pass

    try:
        regional_api = fetch_regional_comparison(config.naics_codes, config.msa_code, config.state_code)
    except Exception:
        pass

    try:
        api_totals = fetch_totals(config.naics_codes, config.msa_code)
    except Exception:
        pass

    try:
        api_skills = fetch_top_skills(config.naics_codes, config.msa_code)
    except Exception:
        pass

    try:
        api_employers = fetch_top_employers(config.naics_codes, config.msa_code)
    except Exception:
        pass

    # Build each sheet (API first, manual fallback, skip if neither)
    summary = _build_summary_sheet(config, occ_api, api_totals)
    if summary is not None:
        sheets["Did you know"] = summary

    occupations = _build_occupations_sheet(config, occ_api)
    if occupations is not None:
        sheets["Notable Occupations"] = occupations

    wage = _build_wage_sheet(config, occ_api)
    if wage is not None:
        sheets["Wage Analysis"] = wage

    employers = _build_employers_sheet(config, api_employers)
    if employers is not None:
        sheets["Notable Employers in DFW"] = employers

    skills = _build_skills_sheet(config, api_skills)
    if skills is not None:
        sheets["In-Demand Skills"] = skills

    comparison = _build_regional_comparison(config, regional_api, api_totals)
    if comparison is not None:
        sheets["Regional Comparison"] = comparison

    # Demographics (from manual or API)
    demo_source = read_demographics(config.overview_xls)
    if demo_source["age"] is not None:
        sheets["Age Breakdown"] = demo_source["age"]
    if demo_source["race_ethnicity"] is not None:
        sheets["Race and Ethnicity Breakdown"] = demo_source["race_ethnicity"]
    if demo_source["gender"] is not None:
        sheets["Gender Breakdown"] = demo_source["gender"]

    # Salary trend
    salary = read_manual_salary_trend(config.jpa_xls)
    if salary is not None:
        sheets["Advertised Wage Trend"] = salary

    # Work where you live
    emp_competing = read_employers_competing(config.jpa_xls)
    if emp_competing is not None:
        sheets["Work where you live"] = dclmic_export.dict_to_df_for_xl({"Employers Competing": emp_competing})

    return sheets

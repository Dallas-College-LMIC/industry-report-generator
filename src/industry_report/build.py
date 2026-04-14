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
    read_occ_csv,
    read_overview_totals,
    read_salary_trend as read_manual_salary_trend,
    read_skills,
)


def _build_occupations_sheet(config: ReportConfig, occ_api: pd.DataFrame | None) -> pd.DataFrame | None:
    """Build the Occupational Employment table."""
    # Try API first
    if occ_api is not None and not occ_api.empty:
        df = occ_api.copy()
        # Core LMI returns occupation descriptions as the index or a column
        # Normalize column names for the report
        rename_map = {}
        if "Jobs 2026" in df.columns:
            rename_map["Jobs 2026"] = "2026 Jobs"
        if "Openings 2026" in df.columns:
            rename_map["Openings 2026"] = "Avg. Annual Openings"

        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    # Fallback to manual CSV
    return read_occ_csv(config.overview_xls if config.occ_csv is None else config.occ_csv) or read_occ_csv(
        config.occ_csv
    )


def _build_wage_sheet(config: ReportConfig, occ_api: pd.DataFrame | None) -> pd.DataFrame | None:
    """Build the Wage Analysis table from occupation data."""
    if occ_api is None or occ_api.empty:
        return None

    df = occ_api.copy()
    # Select wage-relevant columns and add living wage flag
    # Column names depend on what Core LMI returns
    return df


def _build_regional_comparison(
    config: ReportConfig, regional_api: dict | None, postings_totals: dict | None
) -> pd.DataFrame | None:
    """Build the Regional Comparison table: DFW vs Texas vs US."""
    if regional_api is None:
        return None

    rows = []
    metrics = {
        "Jobs (Total)": ["Jobs 2026", "Jobs.2026"],
        "Earnings per Job": ["Earnings 2025", "Earnings.2025"],
    }

    for label, col_options in metrics.items():
        row = {"Metric": label}
        for level, df in regional_api.items():
            if df is not None and not df.empty:
                # Try each possible column name
                for col in col_options:
                    if col in df.columns:
                        row[level] = df[col].sum()
                        break
                else:
                    row[level] = None
            else:
                row[level] = None
        rows.append(row)

    # Add growth metric
    growth_row = {"Metric": "Projected Job Growth (2026-2029)"}
    for level, df in regional_api.items():
        if df is not None and not df.empty:
            jobs_2026_col = next((c for c in df.columns if "Jobs" in c and "2026" in c), None)
            jobs_2029_col = next((c for c in df.columns if "Jobs" in c and "2029" in c), None)
            if jobs_2026_col and jobs_2029_col:
                j26 = df[jobs_2026_col].sum()
                j29 = df[jobs_2029_col].sum()
                growth_row[level] = (j29 - j26) / j26 if j26 else None
            else:
                growth_row[level] = None
        else:
            growth_row[level] = None
    rows.append(growth_row)

    # Add posting metrics if available from JPA
    if postings_totals is not None:
        rows.append(
            {
                "Metric": "Job Postings (Monthly Avg)",
                "msa": postings_totals.get("unique_postings"),
                "state": None,
                "nation": None,
            }
        )

    if not rows:
        return None

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
    return read_employers(config.overview_xls)


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
        jobs_col = next((c for c in occ_api.columns if "Jobs" in c and "2026" in c), None)
        if jobs_col:
            data["Current Employed"] = occ_api[jobs_col].sum()

    # Try JPA for postings
    if api_totals is not None:
        data["Monthly Average Jobs Posted"] = api_totals.get("unique_postings")

    # Manual fallback
    manual_totals = read_overview_totals(config.overview_xls)
    if manual_totals:
        data.setdefault("Current Employed", manual_totals["current_employed"])
        data.setdefault("Monthly Average Jobs Posted", manual_totals["monthly_avg_postings"])
        data["% 3-year Job Demand Growth Rate"] = manual_totals["three_yr_growth"]

    # Employers competing
    employers_competing = read_employers_competing(config.jpa_xls)
    if api_totals and "unique_companies" in api_totals:
        data["Employers Competing"] = api_totals["unique_companies"]
    elif employers_competing:
        data["Employers Competing"] = employers_competing

    if not data:
        return None

    return dclmic_export.dict_to_df_for_xl(data)


def build_all_sheets(config: ReportConfig) -> OrderedDict[str, pd.DataFrame]:
    """Main entry point: fetch all data and build output sheets.

    Returns an OrderedDict of sheet_name -> DataFrame. Sheets with no data are omitted.
    """
    sheets = OrderedDict()

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

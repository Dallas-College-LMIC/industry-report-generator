"""Read manually-downloaded Lightcast Excel exports as fallback.

Handles overview.xls/xlsx, jpa.xls/xlsx, and occ.csv files downloaded from the Lightcast web UI.
Returns None for any missing or unreadable files.
"""

import pandas as pd
from pathlib import Path


def _read_sheet(path: Path | None, sheet_name: str | int, header: int = 0, nrows: int | None = None) -> pd.DataFrame | None:
    """Try reading a sheet from an Excel file (.xls or .xlsx)."""
    if path is None or not path.exists():
        return None
    try:
        return pd.read_excel(str(path), sheet_name=sheet_name, header=header, nrows=nrows)
    except Exception:
        return None


def _read_cell(path: Path | None, sheet_name: str | int, row: int, col: int) -> str | None:
    """Read a single cell value from an Excel file."""
    df = _read_sheet(path, sheet_name, header=None)
    if df is None:
        return None
    try:
        val = df.iloc[row, col]
        return str(val).replace(",", "") if pd.notna(val) else None
    except (IndexError, ValueError):
        return None


def read_jpa_totals(jpa_path: Path | None) -> dict | None:
    """Extract unique postings and companies from JPA Executive Summary."""
    df = _read_sheet(jpa_path, "Executive Summary", header=None)
    if df is None:
        return None

    try:
        # Find values by scanning for labels
        result = {}
        for i in range(len(df)):
            val = str(df.iloc[i, 0]).strip() if pd.notna(df.iloc[i, 0]) else ""
            if val == "Unique Postings":
                result["unique_postings"] = int(str(df.iloc[i + 1, 0]).replace(",", ""))
            elif val == "Companies Posting":
                result["unique_companies"] = int(str(df.iloc[i + 1, 0]).replace(",", ""))
        return result if result else None
    except Exception:
        return None


def read_overview_totals(overview_xls: Path | None) -> dict | None:
    """Extract summary metrics from overview.xls: current employed, 3yr growth, monthly postings."""
    if overview_xls is None or not overview_xls.exists():
        return None

    try:
        employment_df = pd.read_excel(str(overview_xls), sheet_name=3, header=3)

        region_col = "Region"
        msa_match = employment_df[employment_df[region_col].str.contains("Dallas-Fort Worth", na=False)]

        if msa_match.empty:
            return None

        row = msa_match.iloc[0]
        current_employed = row.get("2024 Jobs") or row.get("2026 Jobs")
        three_yr_growth = row.get("% Change")

        # Try reading monthly postings from overview
        monthly_postings = None
        val = _read_cell(overview_xls, 2, 7, 0)
        if val:
            try:
                monthly_postings = int(val)
            except ValueError:
                pass

        return {
            "current_employed": current_employed,
            "three_yr_growth": three_yr_growth,
            "monthly_avg_postings": monthly_postings,
        }
    except Exception:
        return None


def read_employers(jpa_path: Path | None, overview_xls: Path | None = None) -> pd.DataFrame | None:
    """Extract top employers from JPA 'Job Postings Top Companies' or overview 'Demand' sheet."""
    # Try JPA first
    df = _read_sheet(jpa_path, "Job Postings Top Companies", header=2)
    if df is not None and not df.empty:
        return df.head(10)

    # Fallback to overview
    if overview_xls is None or not overview_xls.exists():
        return None
    try:
        df = pd.read_excel(str(overview_xls), sheet_name="Demand", header=2)
        cutoff = df.loc[df["Top Companies"] == "Top Job Titles"].index
        if cutoff.empty:
            return df.head(8)
        return df.iloc[: cutoff[0]].head(8)
    except Exception:
        return None


def read_demographics(overview_xls: Path | None) -> dict[str, pd.DataFrame | None]:
    """Extract age, race/ethnicity, and gender breakdowns from overview.xls."""
    result = {
        "age": None,
        "race_ethnicity": None,
        "gender": None,
    }

    if overview_xls is None or not overview_xls.exists():
        return result

    try:
        result["age"] = pd.read_excel(str(overview_xls), sheet_name="Occ Age Breakdown", header=2)
    except Exception:
        pass
    try:
        result["race_ethnicity"] = pd.read_excel(
            str(overview_xls), sheet_name="Occ Race Ethnicity Breakdown", header=2
        )
    except Exception:
        pass
    try:
        result["gender"] = pd.read_excel(str(overview_xls), sheet_name="Occ Gender Breakdown", header=2)
    except Exception:
        pass

    return result


def read_skills(jpa_xls: Path | None) -> pd.DataFrame | None:
    """Extract top specialized skills from JPA file."""
    return _read_sheet(jpa_xls, "Top Specialized Skills", header=2)


def read_common_skills(jpa_path: Path | None) -> pd.DataFrame | None:
    """Extract top common/soft skills from JPA file."""
    return _read_sheet(jpa_path, "Top Common Skills", header=2)


def read_software_skills(jpa_path: Path | None) -> pd.DataFrame | None:
    """Extract top software/technical skills from JPA file."""
    return _read_sheet(jpa_path, "Top Software Skills", header=2)


def read_salary_trend(jpa_xls: Path | None) -> pd.DataFrame | None:
    """Extract advertised salary trend from jpa.xls."""
    if jpa_xls is None or not jpa_xls.exists():
        return None

    try:
        return pd.read_excel(str(jpa_xls), sheet_name="Advertised Salary Trend", header=2)
    except Exception:
        return None


def read_employers_competing(jpa_xls: Path | None) -> int | None:
    """Extract employers competing count from JPA Executive Summary."""
    totals = read_jpa_totals(jpa_xls)
    if totals and "unique_companies" in totals:
        return totals["unique_companies"]
    return None


def read_occ_csv(occ_csv: Path | None) -> pd.DataFrame | None:
    """Read notable occupations from occ.csv."""
    if occ_csv is None or not occ_csv.exists():
        return None

    try:
        return pd.read_csv(occ_csv)
    except Exception:
        return None

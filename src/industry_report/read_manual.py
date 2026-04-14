"""Read manually-downloaded Lightcast Excel exports as fallback.

Handles overview.xls, jpa.xls, and occ.csv files downloaded from the Lightcast web UI.
Returns None for any missing or unreadable files.
"""

import pandas as pd
import xlrd
from pathlib import Path


def _safe_xls(path: Path | None) -> xlrd.Book | None:
    if path is None or not path.exists():
        return None
    try:
        return xlrd.open_workbook(path)
    except Exception:
        return None


def read_overview_totals(overview_xls: Path | None) -> dict | None:
    """Extract summary metrics from overview.xls: current employed, 3yr growth, monthly postings."""
    book = _safe_xls(overview_xls)
    if book is None:
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
        monthly_postings = int(book.sheet_by_index(2).cell_value(7, 0).replace(",", ""))

        return {
            "current_employed": current_employed,
            "three_yr_growth": three_yr_growth,
            "monthly_avg_postings": monthly_postings,
        }
    except Exception:
        return None


def read_employers(overview_xls: Path | None) -> pd.DataFrame | None:
    """Extract top employers from overview.xls 'Demand' sheet."""
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
    """Extract top specialized skills from jpa.xls."""
    if jpa_xls is None or not jpa_xls.exists():
        return None

    try:
        return pd.read_excel(str(jpa_xls), sheet_name="Top Specialized Skills", header=2).head(15)
    except Exception:
        return None


def read_salary_trend(jpa_xls: Path | None) -> pd.DataFrame | None:
    """Extract advertised salary trend from jpa.xls."""
    if jpa_xls is None or not jpa_xls.exists():
        return None

    try:
        return pd.read_excel(str(jpa_xls), sheet_name="Advertised Salary Trend", header=2)
    except Exception:
        return None


def read_employers_competing(jpa_xls: Path | None) -> int | None:
    """Extract employers competing count from jpa.xls."""
    book = _safe_xls(jpa_xls)
    if book is None:
        return None

    try:
        return int(book.sheet_by_index(2).cell_value(6, 0).replace(",", ""))
    except Exception:
        return None


def read_occ_csv(occ_csv: Path | None) -> pd.DataFrame | None:
    """Read notable occupations from occ.csv."""
    if occ_csv is None or not occ_csv.exists():
        return None

    try:
        return pd.read_csv(occ_csv)
    except Exception:
        return None

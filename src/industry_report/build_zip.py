"""Build ZIP-level spatial analysis sheets from pre-fetched CSV data.

Reads three CSV files from ``config.zip_data/``:
- ``industry.csv``  — Lightcast industry employment per ZIP
- ``occupation.csv`` — Lightcast occupation employment per ZIP
- ``census.csv`` — Census ACS demographics per ZCTA

Returns an OrderedDict of named DataFrames for export.  Returns an
empty OrderedDict if the CSVs do not exist.
"""

from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ReportConfig


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_csv(path: Path) -> pd.DataFrame | None:
    """Load a CSV file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _normalize_industry(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure ZIP (Area) is a zero-padded 5-char string."""
    if "Area" in df.columns:
        df["Area"] = df["Area"].astype(str).str.zfill(5)
    return df


def _normalize_occupation(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure ZIP (Area) is a zero-padded 5-char string."""
    if "Area" in df.columns:
        df["Area"] = df["Area"].astype(str).str.zfill(5)
    return df


def _normalize_census(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure ZCTA is a zero-padded 5-char string; replace sentinel values."""
    df = df.replace(-666666, np.nan)
    if "ZCTA" in df.columns:
        df["ZCTA"] = df["ZCTA"].astype(str).str.zfill(5)
    return df


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------


def _build_zip_industry_detail(
    industry: pd.DataFrame, census: pd.DataFrame | None
) -> pd.DataFrame | None:
    """ZIP-level industry jobs/earnings/growth with optional census context."""
    if industry is None or industry.empty:
        return None

    industry = _normalize_industry(industry.copy())

    if census is not None and not census.empty:
        census = _normalize_census(census.copy())
        df = industry.merge(census, left_on="Area", right_on="ZCTA", how="left")
    else:
        df = industry

    # Derived columns
    df["Job Change 2026-2031"] = df.get("Jobs.2031", pd.Series(0, index=df.index)) - df.get(
        "Jobs.2026", pd.Series(0, index=df.index)
    )

    pop_col = "Total_Population" if "Total_Population" in df.columns else None
    if "Jobs.2026" in df.columns and pop_col:
        df["Industry Jobs per 1000 Residents"] = (df["Jobs.2026"] / df[pop_col]) * 1000

    if "Earnings.2025" in df.columns and "Jobs.2026" in df.columns:
        df["Avg Earnings per Job ($)"] = np.where(
            df["Jobs.2026"] > 0, df["Earnings.2025"] / df["Jobs.2026"], np.nan
        )

    # Rename key columns
    rename = {
        "Area": "ZIP Code",
        "Jobs.2026": "Industry Jobs 2026",
        "Jobs.2031": "Industry Jobs 2031",
        "Earnings.2025": "Total Industry Earnings 2025",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Select output columns (only those that exist)
    desired = [
        "ZIP Code",
        "Industry",
        "Industry Jobs 2026",
        "Industry Jobs 2031",
        "Job Change 2026-2031",
        "Total Industry Earnings 2025",
        "Avg Earnings per Job ($)",
        "Industry Jobs per 1000 Residents",
    ]
    cols = [c for c in desired if c in df.columns]
    return df[cols].copy()


def _build_zip_occupation_detail(
    occupation: pd.DataFrame, census: pd.DataFrame | None
) -> pd.DataFrame | None:
    """ZIP-level occupation jobs/wages/openings with optional census context."""
    if occupation is None or occupation.empty:
        return None

    occupation = _normalize_occupation(occupation.copy())

    if census is not None and not census.empty:
        census = _normalize_census(census.copy())
        df = occupation.merge(census, left_on="Area", right_on="ZCTA", how="left")
    else:
        df = occupation

    # Derived columns
    if "Jobs.2026" in df.columns and "Jobs.2031" in df.columns:
        df["Job Change 2026-2031"] = df["Jobs.2031"] - df["Jobs.2026"]

    if "Jobs.2026" in df.columns and "Openings.2026" in df.columns:
        df["Openings per 100 Jobs"] = (df["Openings.2026"] / df["Jobs.2026"]) * 100

    pop_col = "Total_Population" if "Total_Population" in df.columns else None
    if "Jobs.2026" in df.columns and pop_col:
        df["Occupation Jobs per 1000 Residents"] = (df["Jobs.2026"] / df[pop_col]) * 1000

    # Rename
    rename = {
        "Area": "ZIP Code",
        "Jobs.2026": "Occupation Jobs 2026",
        "Jobs.2031": "Occupation Jobs 2031",
        "Openings.2026": "Annual Openings 2026",
        "Replacements.2026": "Annual Replacements 2026",
        "Earnings.Percentile10.2024": "Wage P10 ($/hr)",
        "Earnings.Percentile50.2024": "Wage P50 ($/hr)",
        "Earnings.Percentile90.2024": "Wage P90 ($/hr)",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    desired = [
        "ZIP Code",
        "Occupation",
        "Occupation Jobs 2026",
        "Occupation Jobs 2031",
        "Job Change 2026-2031",
        "Annual Openings 2026",
        "Annual Replacements 2026",
        "Openings per 100 Jobs",
        "Wage P10 ($/hr)",
        "Wage P50 ($/hr)",
        "Wage P90 ($/hr)",
        "Occupation Jobs per 1000 Residents",
    ]
    cols = [c for c in desired if c in df.columns]
    return df[cols].copy()


def _build_census_context(
    census: pd.DataFrame,
    industry: pd.DataFrame | None,
    occupation: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Demographics, education, income per ZIP — filtered to ZIPs with data."""
    if census is None or census.empty:
        return None

    census = _normalize_census(census.copy())

    # Filter to ZIPs that have industry or occupation data
    zips_with_data: set[str] = set()
    if industry is not None and not industry.empty:
        ind = _normalize_industry(industry.copy())
        zips_with_data.update(ind["Area"].unique())
    if occupation is not None and not occupation.empty:
        occ = _normalize_occupation(occupation.copy())
        zips_with_data.update(occ["Area"].unique())

    if zips_with_data:
        df = census[census["ZCTA"].isin(zips_with_data)].copy()
    else:
        df = census.copy()

    # Rename
    rename = {
        "ZCTA": "ZIP Code",
        "Total_Population": "Population",
        "Median_Household_Income": "Median HH Income ($)",
        "Per_Capita_Income": "Per Capita Income ($)",
        "Labor_Force_Participation_Rate": "Labor Force Participation (%)",
        "Unemployment_Rate": "Unemployment (%)",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    desired = [
        "ZIP Code",
        "Population",
        "Population_Under_18",
        "Population_18_to_64",
        "Population_65_plus",
        "Working_Age_25_54",
        "Less_than_HS",
        "HS_Grad_or_Equivalent",
        "Some_College",
        "Associates_Degree",
        "Bachelors_or_Higher",
        "Median HH Income ($)",
        "Per Capita Income ($)",
        "In_Labor_Force",
        "Employed",
        "Unemployed",
        "Labor Force Participation (%)",
        "Unemployment (%)",
        "Pct_White",
        "Pct_Black",
        "Pct_Asian",
        "Pct_Hispanic",
    ]
    cols = [c for c in desired if c in df.columns]
    return df[cols].copy()


def _build_top_zips_by_jobs(
    industry: pd.DataFrame, occupation: pd.DataFrame, census: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Top ZIPs by employment concentration."""
    frames: list[pd.DataFrame] = []

    if industry is not None and not industry.empty:
        ind = _normalize_industry(industry.copy())
        total = ind["Jobs.2026"].sum()
        if total > 0:
            ind["Share (%)"] = (ind["Jobs.2026"] / total) * 100
        top = ind.nlargest(25, "Jobs.2026")[["Area", "Jobs.2026", "Jobs.2031", "Share (%)"]].copy()
        top["Type"] = "Industry"
        top = top.rename(
            columns={"Area": "ZIP Code", "Jobs.2026": "Jobs 2026", "Jobs.2031": "Jobs 2031"}
        )
        frames.append(top)

    if occupation is not None and not occupation.empty:
        occ = _normalize_occupation(occupation.copy())
        total = occ["Jobs.2026"].sum()
        if total > 0:
            occ["Share (%)"] = (occ["Jobs.2026"] / total) * 100
        top = occ.nlargest(25, "Jobs.2026")[["Area", "Jobs.2026", "Jobs.2031", "Share (%)"]].copy()
        top["Type"] = "Occupation"
        top = top.rename(
            columns={"Area": "ZIP Code", "Jobs.2026": "Jobs 2026", "Jobs.2031": "Jobs 2031"}
        )
        frames.append(top)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)

    # Add census context if available
    if census is not None and not census.empty:
        cen = _normalize_census(census.copy())
        combined = combined.merge(
            cen[["ZCTA", "Total_Population", "Median_Household_Income"]].rename(
                columns={
                    "ZCTA": "ZIP Code",
                    "Total_Population": "Population",
                    "Median_Household_Income": "Median HH Income ($)",
                }
            ),
            on="ZIP Code",
            how="left",
        )
        if "Population" in combined.columns:
            combined["Jobs per 1000 Residents"] = (
                combined["Jobs 2026"] / combined["Population"]
            ) * 1000

    return combined


def _build_wage_analysis(
    occupation: pd.DataFrame, census: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Wage distribution (P10/P50/P90) per ZIP, sorted by median wage."""
    if occupation is None or occupation.empty:
        return None

    occ = _normalize_occupation(occupation.copy())

    # Select relevant columns
    desired = {
        "Area": "ZIP Code",
        "Jobs.2026": "Jobs 2026",
        "Earnings.Percentile10.2024": "Hourly Wage P10 ($)",
        "Earnings.Percentile50.2024": "Hourly Wage P50 ($)",
        "Earnings.Percentile90.2024": "Hourly Wage P90 ($)",
    }
    rename = {k: v for k, v in desired.items() if k in occ.columns}
    df = occ[list(rename.keys())].copy().rename(columns=rename)

    # Annual wages (2080 hrs/yr)
    if "Hourly Wage P50 ($)" in df.columns:
        df["Annual Wage P50 ($)"] = df["Hourly Wage P50 ($)"] * 2080
    if "Hourly Wage P10 ($)" in df.columns:
        df["Annual Wage P10 ($)"] = df["Hourly Wage P10 ($)"] * 2080
    if "Hourly Wage P90 ($)" in df.columns:
        df["Annual Wage P90 ($)"] = df["Hourly Wage P90 ($)"] * 2080

    # Wage spread
    if "Hourly Wage P90 ($)" in df.columns and "Hourly Wage P10 ($)" in df.columns:
        df["Wage Spread (P90/P10)"] = df["Hourly Wage P90 ($)"] / df["Hourly Wage P10 ($)"]

    # Census context: median HH income
    if census is not None and not census.empty:
        cen = _normalize_census(census.copy())
        df = df.merge(
            cen[["ZCTA", "Median_Household_Income"]].rename(
                columns={"ZCTA": "ZIP Code", "Median_Household_Income": "Median HH Income ($)"}
            ),
            on="ZIP Code",
            how="left",
        )

    # Sort by median wage descending
    sort_col = "Hourly Wage P50 ($)"
    if sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_zip_sheets(config: ReportConfig) -> OrderedDict[str, pd.DataFrame]:
    """Read ZIP-level CSVs from config.zip_data and build analysis sheets.

    Returns an OrderedDict of sheet_name → DataFrame.
    Omits sheets whose data is unavailable.
    Returns an empty OrderedDict if no CSVs exist.
    """
    sheets: OrderedDict[str, pd.DataFrame] = OrderedDict()
    data_dir = config.zip_data

    industry = _load_csv(data_dir / "industry.csv")
    occupation = _load_csv(data_dir / "occupation.csv")
    census = _load_csv(data_dir / "census.csv")

    # Industry detail
    ind_detail = _build_zip_industry_detail(industry, census)
    if ind_detail is not None:
        sheets["ZIP Industry Detail"] = ind_detail

    # Occupation detail
    occ_detail = _build_zip_occupation_detail(occupation, census)
    if occ_detail is not None:
        sheets["ZIP Occupation Detail"] = occ_detail

    # Census context
    cen_ctx = _build_census_context(census, industry, occupation)
    if cen_ctx is not None:
        sheets["Census Context"] = cen_ctx

    # Top ZIPs by jobs
    top_zips = _build_top_zips_by_jobs(industry, occupation, census)
    if top_zips is not None:
        sheets["Top ZIPs by Jobs"] = top_zips

    # Wage analysis
    wage = _build_wage_analysis(occupation, census)
    if wage is not None:
        sheets["Wage Analysis"] = wage

    return sheets

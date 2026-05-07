"""Pulse data fetchers — frequently-updated economic indicators.

Every public function returns ``pd.DataFrame | None`` so a missing API key or
network error never crashes the pipeline.

Data sources
------------
1. FRED (UI claims, Dallas Fed surveys, BFS mirror, BLS mirror)
2. Socrata / Texas Open Data (WARN notices, sales tax allocations)
3. BLS Public API (DFW employment — direct, with FRED fallback)
4. Census BFS API (business formation — direct, with FRED fallback)
5. Lightcast JPA (job postings, skills, employers, salary trend)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Sequence

import pandas as pd
import requests

try:
    from fredapi import Fred as _Fred
except ImportError:
    _Fred = None  # type: ignore[assignment,misc]

try:
    from sodapy import Socrata as _Socrata
except ImportError:
    _Socrata = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DFW county helpers
# ---------------------------------------------------------------------------
DFW_COUNTIES = ["Dallas", "Tarrant", "Collin", "Denton", "Ellis", "Rockwall", "Kaufman", "Johnson"]

# Default look-back window for time-series
_LOOKBACK_YEARS = 3


# ---------------------------------------------------------------------------
# Generic FRED helper
# ---------------------------------------------------------------------------


def fetch_fred_series(
    series_ids: str | Sequence[str],
    observation_start: str | None = None,
    observation_end: str | None = None,
    api_key: str | None = None,
) -> pd.DataFrame | None:
    """Fetch one or more FRED series and return a tidy DataFrame.

    Parameters
    ----------
    series_ids
        A single FRED series ID (e.g. ``"TXICLAIMS"``) or a list of them.
    observation_start
        Start date string ``"YYYY-MM-DD"``.  Defaults to
        ``now - _LOOKBACK_YEARS``.
    observation_end
        End date string.  Defaults to today.
    api_key
        FRED API key.  Falls back to ``FRED_API_KEY`` env var.

    Returns
    -------
    DataFrame with columns ``["date", "series_id", "value"]`` or ``None``
    on any failure (missing key, network error, etc.).
    """
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        logger.warning("FRED_API_KEY not set — skipping FRED fetch")
        return None

    if isinstance(series_ids, str):
        series_ids = [series_ids]

    if observation_start is None:
        observation_start = (datetime.now() - timedelta(days=365 * _LOOKBACK_YEARS)).strftime(
            "%Y-%m-%d"
        )
    if observation_end is None:
        observation_end = datetime.now().strftime("%Y-%m-%d")

    if _Fred is None:
        logger.warning("fredapi not installed — skipping FRED fetch")
        return None

    try:
        fred = _Fred(api_key=key, api_key_backup=key)
    except Exception as exc:
        logger.warning("Could not initialise fredapi: %s", exc)
        return None

    frames: list[pd.DataFrame] = []
    for sid in series_ids:
        try:
            s: pd.Series = fred.get_series(
                sid,
                observation_start=observation_start,
                observation_end=observation_end,
            )
            if s is None or s.empty:
                continue
            df = s.reset_index()
            df.columns = ["date", "value"]
            df["series_id"] = sid
            frames.append(df)
        except Exception as exc:
            logger.info("FRED series %s not available: %s", sid, exc)

    if not frames:
        return None

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])
    return result


# ---------------------------------------------------------------------------
# 1. UI Claims (Texas, via FRED)
# ---------------------------------------------------------------------------

UI_CLAIMS_SERIES = {
    "TXICLAIMS": "Initial Claims",
    "TXCCLAIMS": "Continued Claims",
    "TXINSUREDUR": "Insured Unemployment Rate",
}


def fetch_ui_claims(api_key: str | None = None) -> pd.DataFrame | None:
    """Fetch Texas UI claims (initial, continued, insured unemployment rate).

    Returns a DataFrame with weekly observations and derived columns:
    ``4wk_ma``, ``yoy_pct_change`` (per series).
    """
    raw = fetch_fred_series(list(UI_CLAIMS_SERIES.keys()), api_key=api_key)
    if raw is None or raw.empty:
        return None

    raw["series_name"] = raw["series_id"].map(UI_CLAIMS_SERIES)

    # Derive 4-week moving average and YoY per series
    derived_rows: list[pd.DataFrame] = []
    for sid in UI_CLAIMS_SERIES:
        subset = raw[raw["series_id"] == sid].sort_values("date").copy()
        subset["4wk_ma"] = subset["value"].rolling(4, min_periods=1).mean()
        subset["value_year_ago"] = subset["value"].shift(52)
        subset["yoy_pct_change"] = (
            (subset["value"] - subset["value_year_ago"]) / subset["value_year_ago"] * 100
        ).round(2)
        derived_rows.append(subset)

    return pd.concat(derived_rows, ignore_index=True).drop(
        columns=["value_year_ago"], errors="ignore"
    )


# ---------------------------------------------------------------------------
# 2. Dallas Fed Outlook Surveys (via FRED key series)
# ---------------------------------------------------------------------------

# Key TMOS (Texas Manufacturing Outlook Survey) series on FRED
TMOS_SERIES = {
    "TXBOSIRG": "General Business Activity",
    "TXBOSIRE": "Employment",
    "TXBOSIRP": "Production",
    "TXBOSIRW": "Wages",
    "TXBOSIC": "Capacity Utilization",
    "TXBOSISU": "Supplier Delivery Time",
    "TXBOSIRN": "New Orders",
}

# Key TSSOS (Texas Service Sector Outlook Survey) series on FRED
TSSOS_SERIES = {
    "TXBOSIRGS": "General Business Activity",
    "TXBOSIRES": "Employment",
    "TXBOSIRPS": "Production",
    "TXBOSIRWS": "Wages",
    "TXBOSIRNS": "New Orders",
}


def fetch_dallas_fed_surveys(api_key: str | None = None) -> pd.DataFrame | None:
    """Fetch Dallas Fed Manufacturing (TMOS) and Service Sector (TSSOS) indexes.

    Returns a DataFrame with monthly index values, ``survey`` label
    (``"Manufacturing"`` or ``"Service Sector"``), and ``series_name``.
    """
    raw_ids = list(TMOS_SERIES.keys()) + list(TSSOS_SERIES.keys())

    raw = fetch_fred_series(raw_ids, api_key=api_key)
    if raw is None or raw.empty:
        return None

    # Tag with survey type and human-readable name
    def _label(row: pd.Series) -> str:
        sid = row["series_id"]
        if sid in TMOS_SERIES:
            return TMOS_SERIES[sid]
        if sid in TSSOS_SERIES:
            return TSSOS_SERIES[sid]
        return sid

    def _survey(row: pd.Series) -> str:
        sid = row["series_id"]
        if sid in TMOS_SERIES:
            return "Manufacturing"
        if sid in TSSOS_SERIES:
            return "Service Sector"
        return "Unknown"

    raw["series_name"] = raw.apply(_label, axis=1)
    raw["survey"] = raw.apply(_survey, axis=1)

    return raw


# ---------------------------------------------------------------------------
# 3. Census Business Formation Statistics (BFS)
# ---------------------------------------------------------------------------


def fetch_bfs(
    state_code: str = "48",
    api_key: str | None = None,
) -> pd.DataFrame | None:
    """Fetch Census Business Formation Statistics for Texas.

    Uses the Census BFS API.  Falls back to FRED BFS series on failure.

    Returns a DataFrame with monthly business application counts.
    """
    # --- Primary: Census API ---
    try:
        url = "https://api.census.gov/data/timeseries/eits/bfs"
        params = {
            "get": "cell_value,data_type_code,time_slot_id,error_data",
            "time": "from,2023",
            "geo_level": "state",
            "geography": state_code,
            "seasonally_adj": "yes",
            "category_code": "total",
            "data_type_code": "BA_BA",
            "time_slot_id": "M",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 1:
            cols = data[0]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=cols)
            df = df.rename(columns={"cell_value": "value", "time": "date"})
            df["date"] = pd.to_datetime(df["date"], format="%Y-%m")
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df["series_name"] = "Business Applications (TX)"
            df["yoy_pct_change"] = (
                df.sort_values("date")
                .set_index("date")["value"]
                .pct_change(12)
                .mul(100)
                .round(2)
                .values
            )
            return df[["date", "value", "series_name", "yoy_pct_change"]].dropna(subset=["value"])
    except Exception as exc:
        logger.info("Census BFS API failed, trying FRED: %s", exc)

    # --- Fallback: FRED ---
    # FRED has BFS series like "BFS4288BA" (TX total BA, seasonally adjusted)
    fred_sid = f"BFS{state_code}88BA"  # may or may not exist
    raw = fetch_fred_series(fred_sid, api_key=api_key)
    if raw is not None and not raw.empty:
        raw["series_name"] = "Business Applications (TX, FRED)"
        raw["yoy_pct_change"] = (
            raw.sort_values("date")
            .set_index("date")["value"]
            .pct_change(12)
            .mul(100)
            .round(2)
            .values
        )
        return raw
    return None


# ---------------------------------------------------------------------------
# 4. BLS Metro CES Employment (DFW MSA)
# ---------------------------------------------------------------------------


def fetch_bls_employment(
    msa_code: str = "19100",
    api_key: str | None = None,
) -> pd.DataFrame | None:
    """Fetch BLS Current Employment Statistics for the DFW MSA.

    Uses BLS Public API v2.  Falls back to FRED on failure.

    Returns a DataFrame with monthly employment by industry, last ~3 years.
    """
    bls_key = api_key or os.environ.get("BLS_API_KEY")

    # BLS series IDs for MSA: SMSU{MSA}00000000000001 (total nonfarm)
    # Format: SM + U + MSA + 00000000000001
    # We'll try a few key industry supersectors
    prefix = f"SMU{msa_code}0000000"
    series_map = {
        f"{prefix}00000001": "Total Nonfarm",
        f"{prefix}05000001": "Total Private",
        f"{prefix}08000001": "Goods Producing",
        f"{prefix}09000001": "Service Providing",
        f"{prefix}10000001": "Mining and Logging",
        f"{prefix}20000001": "Construction",
        f"{prefix}30000001": "Manufacturing",
        f"{prefix}40000001": "Trade, Transportation, Utilities",
        f"{prefix}50000001": "Information",
        f"{prefix}55000001": "Financial Activities",
        f"{prefix}60000001": "Professional and Business Services",
        f"{prefix}65000001": "Education and Health Services",
        f"{prefix}70000001": "Leisure and Hospitality",
        f"{prefix}80000001": "Other Services",
        f"{prefix}90000001": "Government",
    }
    series_ids = list(series_map.keys())

    start_year = datetime.now().year - _LOOKBACK_YEARS
    end_year = datetime.now().year

    try:
        payload = {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
        if bls_key:
            payload["registrationKey"] = bls_key

        resp = requests.post(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "REQUEST_SUCCEEDED":
            logger.warning("BLS API returned: %s", data.get("message"))
            raise RuntimeError("BLS request failed")

        rows = []
        for series in data.get("Results", {}).get("series", []):
            sid = series["seriesID"]
            industry = series_map.get(sid, sid)
            for obs in series.get("data", []):
                rows.append(
                    {
                        "date": pd.Timestamp(
                            year=int(obs["year"]), month=int(obs["period"][1:]), day=1
                        ),
                        "value": float(obs["value"]) if obs["value"] != "-" else None,
                        "series_id": sid,
                        "industry": industry,
                    }
                )

        if not rows:
            raise RuntimeError("No BLS data rows returned")

        df = pd.DataFrame(rows).dropna(subset=["value"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # YoY change per industry
        derived = []
        for ind, grp in df.groupby("industry"):
            g = grp.sort_values("date").copy()
            g["yoy_pct_change"] = g["value"].pct_change(12).mul(100).round(2)
            derived.append(g)

        return pd.concat(derived, ignore_index=True) if derived else None

    except Exception as exc:
        logger.info("BLS API failed, trying FRED: %s", exc)

    # --- Fallback: FRED ---
    # Try the total nonfarm series on FRED
    fred_sid = f"SMSU{msa_code}00000000000001"
    raw = fetch_fred_series(fred_sid, api_key=os.environ.get("FRED_API_KEY"))
    if raw is not None and not raw.empty:
        raw["industry"] = "Total Nonfarm"
        raw["yoy_pct_change"] = (
            raw.sort_values("date")
            .set_index("date")["value"]
            .pct_change(12)
            .mul(100)
            .round(2)
            .values
        )
        return raw
    return None


# ---------------------------------------------------------------------------
# 5. Texas WARN Act Notices (Socrata)
# ---------------------------------------------------------------------------


def fetch_warn_notices(
    counties: Sequence[str] | None = None,
    months_back: int = 18,
) -> pd.DataFrame | None:
    """Fetch Texas WARN Act notices from Texas Open Data Portal.

    Parameters
    ----------
    counties
        List of county names to filter (default: DFW 8-county area).
    months_back
        How many months of history to fetch (default 18).

    Returns a DataFrame with ``notice_date``, ``company``, ``county``,
    ``layoff_count``, ``layoff_date``, plus derived ``month`` aggregate key.
    """
    if counties is None:
        counties = DFW_COUNTIES

    cutoff = (datetime.now() - timedelta(days=30 * months_back)).strftime("%Y-%m-%d")
    county_filter = ", ".join(f"'{c}'" for c in counties)

    try:
        app_token = os.environ.get("SOCRATA_APP_TOKEN", "")
        if _Socrata is not None:
            client = _Socrata("data.texas.gov", app_token or None, timeout=20)
            results = client.get(
                "8w53-c4f6",
                where=f"layoff_date > '{cutoff}' AND county_name in ({county_filter})",
                limit=10_000,
            )
        else:
            # Fallback: plain CSV download via Socrata API URL
            url = (
                f"https://data.texas.gov/resource/8w53-c4f6.csv?"
                f"$where=layoff_date > '{cutoff}' AND county_name in ({county_filter})"
                f"&$limit=10000"
            )
            results = pd.read_csv(url, timeout=20).to_dict("records")

        if not results:
            return None

        df = pd.DataFrame(results)

        # Normalise column names (Socrata returns lowercase)
        col_map = {
            "notice_date": "notice_date",
            "job_site_name": "company",
            "company_name": "company",
            "county_name": "county",
            "total_layoff_number": "layoff_count",
            "layoff_date": "layoff_date",
            "city_name": "city",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Ensure types
        if "layoff_count" in df.columns:
            df["layoff_count"] = (
                pd.to_numeric(df["layoff_count"], errors="coerce").fillna(0).astype(int)
            )
        if "notice_date" in df.columns:
            df["notice_date"] = pd.to_datetime(df["notice_date"], errors="coerce")
        if "layoff_date" in df.columns:
            df["layoff_date"] = pd.to_datetime(df["layoff_date"], errors="coerce")

        # Derive month key for aggregation
        df["month"] = df["layoff_date"].dt.to_period("M").dt.to_timestamp()

        return df

    except Exception as exc:
        logger.warning("WARN notices fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 6. Texas Comptroller Sales Tax Allocations (Socrata)
# ---------------------------------------------------------------------------


def fetch_sales_tax(
    counties: Sequence[str] | None = None,
    months_back: int = 36,
) -> pd.DataFrame | None:
    """Fetch Texas Comptroller sales tax allocations for DFW counties.

    Returns a DataFrame with monthly allocation amounts by county,
    plus derived YoY percent change.
    """
    if counties is None:
        counties = DFW_COUNTIES[:4]  # Dallas, Tarrant, Collin, Denton

    cutoff = (datetime.now() - timedelta(days=30 * months_back)).strftime("%Y-%m-%d")
    county_filter = ", ".join(f"'{c}'" for c in counties)

    try:
        app_token = os.environ.get("SOCRATA_APP_TOKEN", "")

        if _Socrata is not None:
            client = _Socrata("data.texas.gov", app_token or None, timeout=20)
            results = client.get(
                "qsh8-tby8",
                where=f"month_of_allocation > '{cutoff}' AND county_name in ({county_filter})",
                limit=10_000,
            )
        else:
            url = (
                f"https://data.texas.gov/resource/qsh8-tby8.csv?"
                f"$where=month_of_allocation > '{cutoff}' AND county_name in ({county_filter})"
                f"&$limit=10000"
            )
            results = pd.read_csv(url, timeout=20).to_dict("records")

        if not results:
            return None

        df = pd.DataFrame(results)

        # Normalise columns
        col_map = {
            "county_name": "county",
            "month_of_allocation": "date",
            "amount": "value",
            "allocation_amount": "value",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "value" in df.columns:
            df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # YoY per county
        derived = []
        for county, grp in df.groupby("county"):
            g = grp.sort_values("date").copy()
            g["yoy_pct_change"] = g["value"].pct_change(12).mul(100).round(2)
            derived.append(g)

        return pd.concat(derived, ignore_index=True) if derived else None

    except Exception as exc:
        logger.warning("Sales tax fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 7. Lightcast JPA (Job Posting Analytics)
# ---------------------------------------------------------------------------


def fetch_jpa_postings(
    naics_codes: list[str],
    msa_code: str,
) -> dict[str, pd.DataFrame | dict | None]:
    """Fetch JPA data: totals, top skills, top employers.

    Uses the existing ``fetch_postings`` module which talks to the Lightcast
    JPA API via ``pyghtcast``.

    Returns a dict with keys ``"totals"``, ``"top_skills"``,
    ``"top_employers"``.  Individual values are ``None`` on failure.
    """
    from .fetch_postings import fetch_top_employers, fetch_top_skills, fetch_totals

    result: dict[str, pd.DataFrame | dict | None] = {
        "totals": None,
        "top_skills": None,
        "top_employers": None,
    }

    try:
        result["totals"] = fetch_totals(naics_codes, msa_code)
    except Exception as exc:
        logger.info("JPA totals failed: %s", exc)

    try:
        result["top_skills"] = fetch_top_skills(naics_codes, msa_code)
    except Exception as exc:
        logger.info("JPA top skills failed: %s", exc)

    try:
        result["top_employers"] = fetch_top_employers(naics_codes, msa_code)
    except Exception as exc:
        logger.info("JPA top employers failed: %s", exc)

    return result

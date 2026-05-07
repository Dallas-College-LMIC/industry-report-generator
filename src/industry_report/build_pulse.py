"""Assemble pulse data for the dashboard.

Calls all fetchers from ``fetch_pulse.py`` and returns a dict of named
DataFrames.  Individual fetcher failures are logged and silently skipped —
the dashboard simply omits panels for missing data.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .config import ReportConfig
from .fetch_pulse import (
    DFW_COUNTIES,
    fetch_bfs,
    fetch_bls_employment,
    fetch_dallas_fed_surveys,
    fetch_sales_tax,
    fetch_ui_claims,
    fetch_warn_notices,
)

logger = logging.getLogger(__name__)


def build_pulse_data(config: ReportConfig) -> dict[str, pd.DataFrame]:
    """Fetch all pulse data sources and return a dict of DataFrames.

    Returns
    -------
    dict mapping section name to DataFrame.  Keys that are present
    indicate successful fetches; missing keys mean the source was
    unavailable.

    Guaranteed keys
    ---------------
    ``"ui_claims"``, ``"warn_notices"``, ``"dallas_fed"``,
    ``"sales_tax"``, ``"bfs"``, ``"bls_employment"``
    """
    pulse: dict[str, pd.DataFrame] = {}

    # 1. UI Claims (Texas, via FRED)
    try:
        df = fetch_ui_claims()
        if df is not None and not df.empty:
            pulse["ui_claims"] = df
    except Exception as exc:
        logger.info("UI claims fetch failed: %s", exc)

    # 2. WARN notices (DFW counties, via Socrata)
    try:
        df = fetch_warn_notices(counties=DFW_COUNTIES)
        if df is not None and not df.empty:
            pulse["warn_notices"] = df
    except Exception as exc:
        logger.info("WARN notices fetch failed: %s", exc)

    # 3. Dallas Fed surveys (via FRED)
    try:
        df = fetch_dallas_fed_surveys()
        if df is not None and not df.empty:
            pulse["dallas_fed"] = df
    except Exception as exc:
        logger.info("Dallas Fed fetch failed: %s", exc)

    # 4. Sales tax allocations (DFW counties, via Socrata)
    try:
        df = fetch_sales_tax(counties=DFW_COUNTIES[:4])
        if df is not None and not df.empty:
            pulse["sales_tax"] = df
    except Exception as exc:
        logger.info("Sales tax fetch failed: %s", exc)

    # 5. Business Formation Statistics (TX, via Census/FRED)
    try:
        df = fetch_bfs(state_code=config.state_code)
        if df is not None and not df.empty:
            pulse["bfs"] = df
    except Exception as exc:
        logger.info("BFS fetch failed: %s", exc)

    # 6. BLS Employment (DFW MSA)
    try:
        df = fetch_bls_employment(msa_code=config.msa_code)
        if df is not None and not df.empty:
            pulse["bls_employment"] = df
    except Exception as exc:
        logger.info("BLS employment fetch failed: %s", exc)

    return pulse


def compute_key_metrics(pulse: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Extract latest values for the dashboard metrics bar.

    Returns a dict with keys like ``"ui_initial_claims"``,
    ``"warn_30day_count"``, etc.  Missing data yields ``None``.
    """
    metrics: dict[str, Any] = {}

    # UI Claims — latest initial claims + WoW change
    if "ui_claims" in pulse:
        ic = pulse["ui_claims"]
        initial = ic[ic["series_id"] == "TXICLAIMS"].sort_values("date")
        if not initial.empty:
            latest = initial.iloc[-1]
            metrics["ui_initial_claims"] = latest["value"]
            metrics["ui_initial_claims_4wk_ma"] = latest.get("4wk_ma")
            if len(initial) >= 2:
                metrics["ui_initial_claims_wow"] = round(
                    (latest["value"] - initial.iloc[-2]["value"]) / initial.iloc[-2]["value"] * 100,
                    1,
                )
            metrics["ui_initial_claims_date"] = latest["date"]

    # WARN — 30-day count
    if "warn_notices" in pulse:
        warn = pulse["warn_notices"]
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=30)
        if "layoff_date" in warn.columns:
            recent = warn[warn["layoff_date"] >= cutoff]
        elif "notice_date" in warn.columns:
            recent = warn[warn["notice_date"] >= cutoff]
        else:
            recent = pd.DataFrame()
        metrics["warn_30day_count"] = len(recent)
        metrics["warn_30day_layoffs"] = int(recent.get("layoff_count", pd.Series(dtype=int)).sum())

    # Dallas Fed — latest general business activity index
    if "dallas_fed" in pulse:
        fed = pulse["dallas_fed"]
        mfg_gba = fed[
            (fed["survey"] == "Manufacturing") & (fed["series_name"] == "General Business Activity")
        ]
        if not mfg_gba.empty:
            latest_fed = mfg_gba.sort_values("date").iloc[-1]
            metrics["dallas_fed_mfg_index"] = latest_fed["value"]
            metrics["dallas_fed_mfg_date"] = latest_fed["date"]

        svc_gba = fed[
            (fed["survey"] == "Service Sector")
            & (fed["series_name"] == "General Business Activity")
        ]
        if not svc_gba.empty:
            latest_svc = svc_gba.sort_values("date").iloc[-1]
            metrics["dallas_fed_svc_index"] = latest_svc["value"]

    # BLS — latest total nonfarm employment
    if "bls_employment" in pulse:
        bls = pulse["bls_employment"]
        total = bls[bls["industry"] == "Total Nonfarm"].sort_values("date")
        if not total.empty:
            latest_bls = total.iloc[-1]
            metrics["bls_employment_level"] = latest_bls["value"]
            metrics["bls_employment_yoy"] = latest_bls.get("yoy_pct_change")
            metrics["bls_employment_date"] = latest_bls["date"]

    # BFS — latest value + YoY
    if "bfs" in pulse:
        bfs = pulse["bfs"].sort_values("date")
        if not bfs.empty:
            latest_bfs = bfs.iloc[-1]
            metrics["bfs_business_apps"] = latest_bfs["value"]
            metrics["bfs_yoy"] = latest_bfs.get("yoy_pct_change")
            metrics["bfs_date"] = latest_bfs["date"]

    # Sales tax — latest Dallas County YoY
    if "sales_tax" in pulse:
        st = pulse["sales_tax"]
        dallas = st[st["county"] == "Dallas"].sort_values("date")
        if not dallas.empty:
            latest_st = dallas.iloc[-1]
            metrics["sales_tax_yoy"] = latest_st.get("yoy_pct_change")
            metrics["sales_tax_date"] = latest_st["date"]

    return metrics

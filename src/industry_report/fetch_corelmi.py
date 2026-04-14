"""Fetch occupation data from Lightcast Core LMI API at MSA level."""

import os

import pandas as pd
from pyghtcast.lightcast import Lightcast

OCCUPATION_METRICS = [
    "Jobs.2026",
    "Jobs.2029",
    "Openings.2026",
    "Earnings.Percentile10",
    "Earnings.Percentile50",
    "Earnings.Percentile90",
]

INDUSTRY_METRICS = [
    "Jobs.2026",
    "Jobs.2029",
    "Earnings.2025",
]


def _get_client() -> Lightcast:
    username = os.environ["LCAPI_USER"]
    password = os.environ["LCAPI_PASS"]
    return Lightcast(username, password)


def fetch_occupation_data(soc_codes: list[str], msa_code: str) -> pd.DataFrame:
    """Fetch occupation employment, openings, and wages for selected SOC codes at MSA level.

    Each SOC code gets its own row in the output.
    """
    lc = _get_client()

    # Create a map of occupation names to SOC codes for per-row results
    occ_map = {soc: [soc] for soc in soc_codes}

    constraints = [
        {"dimensionName": "Area", "map": {"MSA": [f"MSA{msa_code}"]}},
        {"dimensionName": "Occupation", "map": occ_map},
        {"dimensionName": "ClassOfWorker", "map": {"QCEW Employees": ["1"]}},
    ]

    query = lc.build_query_corelmi(cols=OCCUPATION_METRICS, constraints=constraints)
    return lc.query_corelmi(dataset="EMSI.us.Occupation", query=query, datarun="2026.1")


def fetch_industry_data(
    naics_codes: list[str], area_code: str
) -> pd.DataFrame:
    """Fetch industry employment and earnings at a given geography.

    area_code: "MSA19100" for DFW metro, "48" for Texas, "1" for US.
    """
    lc = _get_client()

    constraints = [
        {"dimensionName": "Area", "map": {"Region": [area_code]}},
        {"dimensionName": "Industry", "map": {"Industries": naics_codes}},
        {"dimensionName": "ClassOfWorker", "map": {"QCEW Employees": ["1"]}},
    ]

    query = lc.build_query_corelmi(cols=INDUSTRY_METRICS, constraints=constraints)
    return lc.query_corelmi(dataset="EMSI.us.Industry", query=query, datarun="2026.1")


def fetch_regional_comparison(naics_codes: list[str], msa_code: str, state_code: str) -> dict:
    """Fetch industry data at MSA, state, and national levels for comparison table."""
    return {
        "msa": fetch_industry_data(naics_codes, f"MSA{msa_code}"),
        "state": fetch_industry_data(naics_codes, state_code),
        "nation": fetch_industry_data(naics_codes, "1"),
    }

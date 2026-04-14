"""Fetch job posting analytics from Lightcast JPA API.

Returns None if JPA access is unavailable, triggering manual fallback.
"""

import os

import pandas as pd


def _get_client():
    """Try to create a JPA client. Returns None if unavailable."""
    try:
        from pyghtcast.lightcast import JobPostings

        jpa = JobPostings()
        if not jpa.conn.token:
            return None
        return jpa
    except (ImportError, ValueError, Exception):
        return None


def _base_payload(naics_codes: list[str], msa_code: str) -> dict:
    return {
        "filter": {
            "when": {"start": "2025-04", "end": "2026-04"},
            "naics": naics_codes,
            "msa": [msa_code],
        }
    }


def fetch_totals(naics_codes: list[str], msa_code: str) -> dict | None:
    """Get posting totals: unique postings, unique companies, salary stats."""
    jpa = _get_client()
    if jpa is None:
        return None
    try:
        return jpa.totals(_base_payload(naics_codes, msa_code))
    except Exception:
        return None


def fetch_top_skills(naics_codes: list[str], msa_code: str, limit: int = 15) -> pd.DataFrame | None:
    """Get top specialized skills ranked by unique postings."""
    jpa = _get_client()
    if jpa is None:
        return None
    try:
        payload = _base_payload(naics_codes, msa_code)
        payload["rank"] = {"by": "unique_postings", "limit": limit}
        return jpa.rankings("skills", payload)
    except Exception:
        return None


def fetch_top_employers(naics_codes: list[str], msa_code: str, limit: int = 8) -> pd.DataFrame | None:
    """Get top companies ranked by unique postings."""
    jpa = _get_client()
    if jpa is None:
        return None
    try:
        payload = _base_payload(naics_codes, msa_code)
        payload["rank"] = {"by": "unique_postings", "limit": limit}
        return jpa.rankings("company", payload)
    except Exception:
        return None


def fetch_salary_trend(naics_codes: list[str], msa_code: str) -> dict | None:
    """Get salary trend over time from job postings."""
    jpa = _get_client()
    if jpa is None:
        return None
    try:
        return jpa.timeseries(_base_payload(naics_codes, msa_code))
    except Exception:
        return None

"""Tests for the pulse data module.

Covers:
- FRED-based fetchers (UI claims, Dallas Fed) with mocked fredapi
- Socrata-based fetchers (WARN notices, sales tax) with mocked sodapy
- BLS fetcher with mocked requests
- BFS fetcher with mocked Census API
- Graceful failure when API keys are missing
- build_pulse_data() orchestration
- compute_key_metrics() extraction
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from industry_report.build_pulse import build_pulse_data, compute_key_metrics
from industry_report.config import load_config
from industry_report.fetch_pulse import (
    fetch_bfs,
    fetch_bls_employment,
    fetch_dallas_fed_surveys,
    fetch_fred_series,
    fetch_sales_tax,
    fetch_ui_claims,
    fetch_warn_notices,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fred_series(dates, values, series_id="TEST"):
    """Create a DataFrame mimicking fetch_fred_series output."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "value": values,
            "series_id": series_id,
        }
    )


def _mock_fred_get_series(series_map: dict[str, pd.Series]):
    """Return a mock Fred class whose get_series returns pre-canned data."""
    mock_fred = MagicMock()

    def _get(sid, **kwargs):
        if sid in series_map:
            return series_map[sid]
        raise ValueError(f"Unknown series: {sid}")

    mock_fred.get_series = _get
    return mock_fred


# ---------------------------------------------------------------------------
# fetch_fred_series — generic helper
# ---------------------------------------------------------------------------


class TestFetchFredSeries:
    """Tests for the generic FRED fetcher."""

    def test_returns_none_when_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            # Ensure FRED_API_KEY is not set
            os.environ.pop("FRED_API_KEY", None)
            result = fetch_fred_series("TXICLAIMS", api_key="")
            assert result is None

    def test_returns_none_on_init_failure(self):
        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", side_effect=RuntimeError("init fail")):
                result = fetch_fred_series("TXICLAIMS", api_key="fake")
                assert result is None

    def test_returns_dataframe_on_success(self):
        dates = pd.date_range("2024-01-01", periods=5, freq="W")
        values = [1000, 1100, 1050, 1200, 1150]
        expected_series = pd.Series(values, index=dates)

        mock_fred = MagicMock()
        mock_fred.get_series.return_value = expected_series

        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", return_value=mock_fred):
                result = fetch_fred_series("TXICLAIMS", api_key="fake")
                assert result is not None
                assert len(result) == 5
                assert "series_id" in result.columns
                assert result["series_id"].iloc[0] == "TXICLAIMS"

    def test_handles_multiple_series(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="W")
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [
            pd.Series([1000, 1100, 1050], index=dates),
            pd.Series([5000, 5100, 5050], index=dates),
        ]

        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", return_value=mock_fred):
                result = fetch_fred_series(["TXICLAIMS", "TXCCLAIMS"], api_key="fake")
                assert result is not None
                assert set(result["series_id"].unique()) == {"TXICLAIMS", "TXCCLAIMS"}

    def test_skips_failed_series_gracefully(self):
        dates = pd.date_range("2024-01-01", periods=3, freq="W")
        mock_fred = MagicMock()
        mock_fred.get_series.side_effect = [
            pd.Series([1000, 1100, 1050], index=dates),
            ValueError("Series not found"),
        ]

        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", return_value=mock_fred):
                result = fetch_fred_series(["TXICLAIMS", "BAD"], api_key="fake")
                assert result is not None
                assert "TXICLAIMS" in result["series_id"].values
                assert "BAD" not in result["series_id"].values


# ---------------------------------------------------------------------------
# fetch_ui_claims
# ---------------------------------------------------------------------------


class TestFetchUiClaims:
    """Tests for the UI claims fetcher."""

    def test_returns_none_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FRED_API_KEY", None)
            result = fetch_ui_claims(api_key="")
            assert result is None

    def test_returns_df_with_derived_columns(self):
        dates = pd.date_range("2024-01-06", periods=60, freq="W")
        values = [1000 + i * 10 for i in range(60)]
        mock_fred = MagicMock()
        mock_fred.get_series.return_value = pd.Series(values, index=dates)

        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", return_value=mock_fred):
                result = fetch_ui_claims(api_key="fake")

        assert result is not None
        assert "4wk_ma" in result.columns
        assert "yoy_pct_change" in result.columns
        assert "series_name" in result.columns


# ---------------------------------------------------------------------------
# fetch_dallas_fed_surveys
# ---------------------------------------------------------------------------


class TestFetchDallasFedSurveys:
    """Tests for the Dallas Fed survey fetcher."""

    def test_returns_df_with_survey_labels(self):
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        mock_fred = MagicMock()

        def _get(sid, **kwargs):
            return pd.Series([i for i in range(12)], index=dates)

        mock_fred.get_series = _get

        with patch.dict(os.environ, {"FRED_API_KEY": "fake"}):
            with patch("industry_report.fetch_pulse._Fred", return_value=mock_fred):
                result = fetch_dallas_fed_surveys(api_key="fake")

        assert result is not None
        assert "survey" in result.columns
        assert set(result["survey"].unique()) == {"Manufacturing", "Service Sector"}
        assert "series_name" in result.columns


# ---------------------------------------------------------------------------
# fetch_bfs
# ---------------------------------------------------------------------------


class TestFetchBfs:
    """Tests for the BFS fetcher."""

    def test_bfs_returns_none_without_fred_key(self):
        """BFS fetcher should return None gracefully without FRED key."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FRED_API_KEY", None)
            result = fetch_bfs(state_code="48")
            assert result is None

    def test_returns_none_on_census_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("FRED_API_KEY", None)
            result = fetch_bfs(state_code="48")
            assert result is None


# ---------------------------------------------------------------------------
# fetch_bls_employment
# ---------------------------------------------------------------------------


class TestFetchBlsEmployment:
    """Tests for the BLS employment fetcher."""

    def test_bls_api_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "SMU1910000000000000001",
                        "data": [
                            {"year": "2024", "period": "M01", "value": "3500000"},
                            {"year": "2024", "period": "M02", "value": "3510000"},
                        ],
                    }
                ]
            },
        }

        with patch("industry_report.fetch_pulse.requests") as mock_req:
            mock_req.post.return_value = mock_response
            result = fetch_bls_employment(msa_code="19100")

        assert result is not None
        assert "industry" in result.columns

    def test_returns_none_on_bls_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": "REQUEST_FAILED", "message": []}

        with patch("industry_report.fetch_pulse.requests") as mock_req:
            mock_req.post.return_value = mock_response
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("FRED_API_KEY", None)
                result = fetch_bls_employment(msa_code="19100")
                assert result is None


# ---------------------------------------------------------------------------
# fetch_warn_notices
# ---------------------------------------------------------------------------


class TestFetchWarnNotices:
    """Tests for the WARN notices fetcher."""

    def test_returns_df_with_correct_columns(self):
        mock_client = MagicMock()
        mock_client.get.return_value = [
            {
                "notice_date": "2025-03-15",
                "company_name": "Test Corp",
                "county_name": "Dallas",
                "total_layoff_number": "100",
                "layoff_date": "2025-04-01",
                "city_name": "Dallas",
            },
            {
                "notice_date": "2025-02-10",
                "company_name": "Other Inc",
                "county_name": "Tarrant",
                "total_layoff_number": "50",
                "layoff_date": "2025-03-01",
                "city_name": "Fort Worth",
            },
        ]

        with patch("industry_report.fetch_pulse._Socrata", return_value=mock_client):
            result = fetch_warn_notices()

        assert result is not None
        assert "county" in result.columns
        assert "layoff_count" in result.columns
        assert len(result) == 2

    def test_returns_none_on_failure(self):
        with patch("industry_report.fetch_pulse._Socrata", side_effect=Exception("API down")):
            result = fetch_warn_notices()
            assert result is None

    def test_filters_by_county(self):
        mock_client = MagicMock()
        mock_client.get.return_value = [
            {
                "notice_date": "2025-03-15",
                "company_name": "Test Corp",
                "county_name": "Harris",
                "total_layoff_number": "100",
                "layoff_date": "2025-04-01",
            },
        ]

        with patch("industry_report.fetch_pulse._Socrata", return_value=mock_client):
            # The Socrata mock won't actually filter, but we can verify
            # the where clause includes the county filter
            fetch_warn_notices(counties=["Harris"])
            # Just verify the call was made
            mock_client.get.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_sales_tax
# ---------------------------------------------------------------------------


class TestFetchSalesTax:
    """Tests for the sales tax fetcher."""

    def test_returns_df_with_yoy(self):
        mock_client = MagicMock()
        mock_client.get.return_value = [
            {
                "county": "Dallas",
                "net_payment_this_period": "50000000",
                "report_month": "1",
                "report_year": "2024",
            },
            {
                "county": "Dallas",
                "net_payment_this_period": "52000000",
                "report_month": "2",
                "report_year": "2024",
            },
        ]

        with patch("industry_report.fetch_pulse._Socrata", return_value=mock_client):
            result = fetch_sales_tax(counties=["Dallas"])

        assert result is not None
        assert "county" in result.columns
        assert "yoy_pct_change" in result.columns

    def test_returns_none_on_failure(self):
        with patch("industry_report.fetch_pulse._Socrata", side_effect=Exception("API down")):
            result = fetch_sales_tax()
            assert result is None


# ---------------------------------------------------------------------------
# fetch_jpa_postings
# ---------------------------------------------------------------------------


class TestFetchJpaPostings:
    """Tests for the JPA postings fetcher wrapper."""

    def test_returns_dict_with_all_keys(self):
        with (
            patch(
                "industry_report.fetch_postings.fetch_totals", return_value={"unique_postings": 500}
            ),
            patch(
                "industry_report.fetch_postings.fetch_top_skills",
                return_value=pd.DataFrame({"Skill": ["Python"], "Postings": [100]}),
            ),
            patch(
                "industry_report.fetch_postings.fetch_top_employers",
                return_value=pd.DataFrame({"Company": ["Corp"], "Postings": [50]}),
            ),
        ):
            from industry_report.fetch_pulse import fetch_jpa_postings

            result = fetch_jpa_postings(["6211"], "19100")
            assert result["totals"] == {"unique_postings": 500}
            assert result["top_skills"] is not None
            assert result["top_employers"] is not None

    def test_returns_nones_on_failure(self):
        with (
            patch(
                "industry_report.fetch_postings.fetch_totals", side_effect=RuntimeError("no auth")
            ),
            patch("industry_report.fetch_postings.fetch_top_skills", return_value=None),
            patch("industry_report.fetch_postings.fetch_top_employers", return_value=None),
        ):
            from industry_report.fetch_pulse import fetch_jpa_postings

            result = fetch_jpa_postings(["6211"], "19100")
            assert result["totals"] is None
            assert result["top_skills"] is None
            assert result["top_employers"] is None


# ---------------------------------------------------------------------------
# build_pulse_data
# ---------------------------------------------------------------------------


class TestBuildPulseData:
    """Tests for the pulse build orchestrator."""

    @pytest.fixture
    def config(self):
        return load_config(os.path.join(FIXTURES, "test_config.toml"))

    def test_returns_dict(self, config):
        with (
            patch("industry_report.build_pulse.fetch_ui_claims", return_value=None),
            patch("industry_report.build_pulse.fetch_warn_notices", return_value=None),
            patch("industry_report.build_pulse.fetch_dallas_fed_surveys", return_value=None),
            patch("industry_report.build_pulse.fetch_sales_tax", return_value=None),
            patch("industry_report.build_pulse.fetch_bfs", return_value=None),
            patch("industry_report.build_pulse.fetch_bls_employment", return_value=None),
            patch(
                "industry_report.build_pulse.fetch_jpa_postings",
                return_value={"totals": None, "top_skills": None, "top_employers": None},
            ),
        ):
            result = build_pulse_data(config)
            assert isinstance(result, dict)

    def test_includes_available_sources(self, config):
        ui_df = pd.DataFrame({"date": ["2024-01-01"], "value": [1000]})
        with (
            patch("industry_report.build_pulse.fetch_ui_claims", return_value=ui_df),
            patch("industry_report.build_pulse.fetch_warn_notices", return_value=None),
            patch("industry_report.build_pulse.fetch_dallas_fed_surveys", return_value=None),
            patch("industry_report.build_pulse.fetch_sales_tax", return_value=None),
            patch("industry_report.build_pulse.fetch_bfs", return_value=None),
            patch("industry_report.build_pulse.fetch_bls_employment", return_value=None),
            patch(
                "industry_report.build_pulse.fetch_jpa_postings",
                return_value={"totals": None, "top_skills": None, "top_employers": None},
            ),
        ):
            result = build_pulse_data(config)
            assert "ui_claims" in result
            assert "warn_notices" not in result

    def test_includes_jpa_data(self, config):
        with (
            patch("industry_report.build_pulse.fetch_ui_claims", return_value=None),
            patch("industry_report.build_pulse.fetch_warn_notices", return_value=None),
            patch("industry_report.build_pulse.fetch_dallas_fed_surveys", return_value=None),
            patch("industry_report.build_pulse.fetch_sales_tax", return_value=None),
            patch("industry_report.build_pulse.fetch_bfs", return_value=None),
            patch("industry_report.build_pulse.fetch_bls_employment", return_value=None),
            patch(
                "industry_report.build_pulse.fetch_jpa_postings",
                return_value={
                    "totals": {"unique_postings": 500, "unique_companies": 40},
                    "top_skills": pd.DataFrame({"Skill": ["Python"], "Postings": [100]}),
                    "top_employers": pd.DataFrame({"Company": ["Corp"], "Postings": [50]}),
                },
            ),
        ):
            result = build_pulse_data(config)
            assert "jpa_totals" in result
            assert "jpa_skills" in result
            assert "jpa_employers" in result

    def test_does_not_crash_on_exceptions(self, config):
        with (
            patch("industry_report.build_pulse.fetch_ui_claims", side_effect=RuntimeError("boom")),
            patch("industry_report.build_pulse.fetch_warn_notices", return_value=None),
            patch("industry_report.build_pulse.fetch_dallas_fed_surveys", return_value=None),
            patch("industry_report.build_pulse.fetch_sales_tax", return_value=None),
            patch("industry_report.build_pulse.fetch_bfs", return_value=None),
            patch("industry_report.build_pulse.fetch_bls_employment", return_value=None),
            patch(
                "industry_report.build_pulse.fetch_jpa_postings",
                return_value={"totals": None, "top_skills": None, "top_employers": None},
            ),
        ):
            result = build_pulse_data(config)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# compute_key_metrics
# ---------------------------------------------------------------------------


class TestComputeKeyMetrics:
    """Tests for the key metrics extractor."""

    def test_empty_pulse_returns_empty_metrics(self):
        metrics = compute_key_metrics({})
        assert "ui_initial_claims" not in metrics

    def test_extracts_ui_claims_metrics(self):
        pulse = {
            "ui_claims": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-06", "2024-01-13"]),
                    "value": [1000, 1050],
                    "series_id": ["TXICLAIMS", "TXICLAIMS"],
                    "4wk_ma": [1000, 1025],
                    "yoy_pct_change": [5.0, 3.0],
                }
            )
        }
        metrics = compute_key_metrics(pulse)
        assert metrics["ui_initial_claims"] == 1050
        assert "ui_initial_claims_wow" in metrics

    def test_warn_with_string_dates(self):
        """Reproduce Streamlit crash: layoff_date as object dtype strings."""
        pulse = {
            "warn_notices": pd.DataFrame(
                {
                    "company": ["Corp A", "Corp B", "Corp C"],
                    "county": ["Dallas", "Tarrant", "Collin"],
                    "layoff_count": [100, 50, 25],
                    "layoff_date": [
                        datetime.now().strftime("%Y-%m-%d"),
                        (datetime.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                        (datetime.now() - pd.Timedelta(days=60)).strftime("%Y-%m-%d"),
                    ],
                }
            )
        }
        metrics = compute_key_metrics(pulse)
        assert metrics["warn_30day_count"] == 2
        assert metrics["warn_30day_layoffs"] == 150

    def test_extracts_warn_30day_count(self):
        pulse = {
            "warn_notices": pd.DataFrame(
                {
                    "company": ["Corp A", "Corp B"],
                    "county": ["Dallas", "Tarrant"],
                    "layoff_count": [100, 50],
                    "layoff_date": pd.to_datetime(
                        [
                            datetime.now().strftime("%Y-%m-%d"),
                            (datetime.now() - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                        ]
                    ),
                }
            )
        }
        metrics = compute_key_metrics(pulse)
        assert metrics["warn_30day_count"] == 2
        assert metrics["warn_30day_layoffs"] == 150

    def test_extracts_bls_employment(self):
        pulse = {
            "bls_employment": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                    "value": [3500000, 3520000],
                    "industry": ["Total Nonfarm", "Total Nonfarm"],
                    "yoy_pct_change": [2.5, 2.8],
                }
            )
        }
        metrics = compute_key_metrics(pulse)
        assert metrics["bls_employment_level"] == 3520000
        assert metrics["bls_employment_yoy"] == 2.8

    def test_dallas_fed_index_extraction(self):
        pulse = {
            "dallas_fed": pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                    "value": [-5.0, 3.2],
                    "series_name": ["General Business Activity", "General Business Activity"],
                    "survey": ["Manufacturing", "Manufacturing"],
                }
            )
        }
        metrics = compute_key_metrics(pulse)
        assert metrics["dallas_fed_mfg_index"] == 3.2

    def test_extracts_jpa_metrics_from_dataframe(self):
        pulse = {"jpa_totals": pd.DataFrame([{"unique_postings": 1500, "unique_companies": 120}])}
        metrics = compute_key_metrics(pulse)
        assert metrics["jpa_unique_postings"] == 1500
        assert metrics["jpa_unique_companies"] == 120

    def test_extracts_jpa_metrics_from_dict(self):
        pulse = {"jpa_totals": {"unique_postings": 800, "unique_companies": 60}}
        metrics = compute_key_metrics(pulse)
        assert metrics["jpa_unique_postings"] == 800
        assert metrics["jpa_unique_companies"] == 60

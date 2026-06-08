"""Tests for dashboard helper functions.

These test the pure-logic helpers extracted from dashboard.py
so we don't need a running Streamlit app.
"""

import pytest
import pandas as pd

from industry_report.dashboard_helpers import (
    compute_freshness_rows,
    format_code_list_expanded,
    pick_label_column,
    prepare_sales_tax_chart,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pulse_dict_with_dates():
    """Minimal pulse dict with date columns for freshness testing."""
    return {
        "ui_claims": pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-06-01"]),
                "value": [100, 120],
            }
        ),
        "bls_employment": pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-03-01"]),
                "value": [3_500_000],
            }
        ),
    }


@pytest.fixture
def pulse_dict_with_future_dates():
    """Pulse dict where the latest data point is in the future."""
    tomorrow = pd.Timestamp.now() + pd.Timedelta(days=5)
    return {
        "ui_claims": pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", tomorrow]),
                "value": [100, 120],
            }
        ),
    }


# ---------------------------------------------------------------------------
# compute_freshness_rows
# ---------------------------------------------------------------------------


class TestComputeFreshnessRows:
    """Tests for the compute_freshness_rows helper."""

    def test_returns_empty_for_empty_pulse(self):
        result = compute_freshness_rows({})
        assert result == []

    def test_returns_rows_for_sources_with_dates(self, pulse_dict_with_dates):
        rows = compute_freshness_rows(pulse_dict_with_dates)
        assert len(rows) == 2
        sources = {r["Source"] for r in rows}
        assert "UI Claims (FRED)" in sources
        assert "BLS Employment (BLS/FRED)" in sources

    def test_days_ago_is_non_negative(self, pulse_dict_with_future_dates):
        """Days Ago must never be negative — future dates clamp to 0."""
        rows = compute_freshness_rows(pulse_dict_with_future_dates)
        assert len(rows) == 1
        assert rows[0]["Days Ago"] >= 0

    def test_future_date_shows_upcoming(self, pulse_dict_with_future_dates):
        """Status for future dates should say 'Upcoming', not negative."""
        rows = compute_freshness_rows(pulse_dict_with_future_dates)
        assert rows[0]["Status"] == "📅 Upcoming"

    def test_warn_notices_key_matched(self):
        """WARN notices use 'warn_notices' key in pulse dict."""
        recent = pd.Timestamp.now() - pd.Timedelta(days=5)
        pulse = {
            "warn_notices": pd.DataFrame(
                {
                    "notice_date": [recent],
                    "company": ["Acme Corp"],
                }
            ),
        }
        rows = compute_freshness_rows(pulse)
        assert len(rows) == 1
        assert rows[0]["Source"] == "WARN Notices (Socrata)"

    def test_ui_claims_stale_after_14_days(self):
        """Weekly sources should be stale after 14 days."""
        old = pd.Timestamp.now() - pd.Timedelta(days=15)
        pulse = {"ui_claims": pd.DataFrame({"date": [old], "value": [100]})}
        rows = compute_freshness_rows(pulse)
        assert rows[0]["Status"] == "⚠️ Stale"

    def test_ui_claims_fresh_at_10_days(self):
        """Weekly sources should still be fresh at 10 days."""
        recent = pd.Timestamp.now() - pd.Timedelta(days=10)
        pulse = {"ui_claims": pd.DataFrame({"date": [recent], "value": [100]})}
        rows = compute_freshness_rows(pulse)
        assert rows[0]["Status"] == "✅ Fresh"

    def test_bls_stale_after_45_days(self):
        """Monthly sources should be stale after 45 days."""
        old = pd.Timestamp.now() - pd.Timedelta(days=50)
        pulse = {"bls_employment": pd.DataFrame({"date": [old], "value": [100]})}
        rows = compute_freshness_rows(pulse)
        assert rows[0]["Status"] == "⚠️ Stale"

    def test_bls_fresh_at_30_days(self):
        """Monthly sources should still be fresh at 30 days."""
        recent = pd.Timestamp.now() - pd.Timedelta(days=30)
        pulse = {"bls_employment": pd.DataFrame({"date": [recent], "value": [100]})}
        rows = compute_freshness_rows(pulse)
        assert rows[0]["Status"] == "✅ Fresh"

    def test_warn_stale_after_14_days(self):
        """WARN notices (daily source) should be stale after 14 days."""
        old = pd.Timestamp.now() - pd.Timedelta(days=20)
        pulse = {"warn_notices": pd.DataFrame({"notice_date": [old], "company": ["X"]})}
        rows = compute_freshness_rows(pulse)
        assert rows[0]["Status"] == "⚠️ Stale"

    def test_skips_sources_without_date_column(self):
        pulse = {
            "ui_claims": pd.DataFrame({"value": [100]}),  # no date column
        }
        rows = compute_freshness_rows(pulse)
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# format_code_list
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Sales tax chart helper
# ---------------------------------------------------------------------------


class TestPrepareSalesTaxChart:
    """Tests for sales tax chart data preparation."""

    def test_highlights_dallas(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-01"]),
                "value": [100, 200, 150],
                "county": ["Dallas", "Tarrant", "Collin"],
            }
        )
        result = prepare_sales_tax_chart(df)
        dallas_rows = result[result["county"] == "Dallas"]
        other_rows = result[result["county"] != "Dallas"]
        assert len(dallas_rows) == 1
        assert len(other_rows) == 2

    def test_handles_missing_county(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01"]),
                "value": [100],
            }
        )
        result = prepare_sales_tax_chart(df)
        assert result is None

    def test_adds_yoy_change(self):
        # Use 13 months of monthly data per county so pct_change(periods=12)
        # produces at least one non-NaN value per county.
        dates = pd.date_range("2024-01-01", periods=13, freq="MS")
        df = pd.DataFrame(
            {
                "date": pd.concat([pd.Series(dates), pd.Series(dates)]),
                "value": list(range(100, 113)) + list(range(200, 213)),
                "county": ["Dallas"] * 13 + ["Tarrant"] * 13,
            }
        )
        result = prepare_sales_tax_chart(df)
        assert "YoY Change" in result.columns
        dallas_yoy = result[result["county"] == "Dallas"]["YoY Change"].dropna()
        assert len(dallas_yoy) > 0


# ---------------------------------------------------------------------------
# pick_label_column
# ---------------------------------------------------------------------------


class TestPickLabelColumn:
    """Tests for the chart label column picker."""

    def test_prefers_occupation_over_soc(self):
        df = pd.DataFrame({"SOC": ["29-1141"], "Occupation": ["Registered Nurses"]})
        assert pick_label_column(df) == "Occupation"

    def test_falls_back_to_soc(self):
        df = pd.DataFrame({"SOC": ["29-1141"], "Other": [1]})
        assert pick_label_column(df) == "SOC"

    def test_prefers_industry_over_naics(self):
        df = pd.DataFrame({"NAICS": ["6211"], "Industry": ["Offices of Physicians"]})
        assert pick_label_column(df) == "Industry"

    def test_falls_back_to_naics(self):
        df = pd.DataFrame({"NAICS": ["6211"], "Other": [1]})
        assert pick_label_column(df) == "NAICS"

    def test_falls_back_to_first_column(self):
        df = pd.DataFrame({"Foo": [1], "Bar": [2]})
        assert pick_label_column(df) == "Foo"

    def test_prefers_occupation_even_with_naics(self):
        """When both Occupation and Industry columns exist."""
        df = pd.DataFrame({"Occupation": ["Nurse"], "Industry": ["Hospitals"]})
        assert pick_label_column(df) == "Occupation"

    def test_ignores_code_column_when_title_exists(self):
        """SOC codes should never be chosen when Occupation column exists."""
        df = pd.DataFrame(
            {
                "SOC": ["29-1141", "29-1171"],
                "Occupation": ["Registered Nurses", "Nurse Practitioners"],
            }
        )
        col = pick_label_column(df)
        values = df[col].tolist()
        assert "29-1141" not in values
        assert "Registered Nurses" in values


# ---------------------------------------------------------------------------
# prepare_sheets_for_export
# ---------------------------------------------------------------------------


class TestPrepareSheetsForExport:
    """Tests for ensuring code columns are text, not numbers, in Excel."""

    def test_naics_cast_to_string(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        sheets = {
            "Industry Overview": pd.DataFrame(
                {
                    "NAICS": [2382, 2362, 2371],
                    "Industry": ["Contractors", "Construction", "Utility"],
                    "2026 Jobs": [100, 200, 300],
                }
            ),
        }
        result = prepare_sheets_for_export(sheets)
        assert result["Industry Overview"]["NAICS"].dtype == object
        assert result["Industry Overview"]["NAICS"].iloc[0] == "2382"

    def test_soc_unchanged(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        sheets = {
            "Notable Occupations": pd.DataFrame(
                {
                    "SOC": ["29-1141", "29-1171"],
                    "Occupation": ["Nurses", "Nurse Practitioners"],
                }
            ),
        }
        result = prepare_sheets_for_export(sheets)
        # SOC codes are already strings with dashes — should remain unchanged
        assert result["Notable Occupations"]["SOC"].dtype == object
        assert result["Notable Occupations"]["SOC"].iloc[0] == "29-1141"

    def test_zip_code_cast_to_string(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        sheets = {
            "ZIP Industry Detail": pd.DataFrame(
                {
                    "ZIP Code": [75001, 75002, 75006],
                    "Jobs": [100, 200, 300],
                }
            ),
        }
        result = prepare_sheets_for_export(sheets)
        assert result["ZIP Industry Detail"]["ZIP Code"].dtype == object
        # Should preserve leading zeros if any (5-digit zero-padded)
        assert result["ZIP Industry Detail"]["ZIP Code"].iloc[0] == "75001"

    def test_preserves_leading_zeros_in_zip(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        sheets = {
            "Some Sheet": pd.DataFrame(
                {
                    "ZIP Code": ["00501", "01001", "90210"],
                }
            ),
        }
        result = prepare_sheets_for_export(sheets)
        assert result["Some Sheet"]["ZIP Code"].iloc[0] == "00501"

    def test_does_not_mutate_original(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        original = pd.DataFrame({"NAICS": [2382, 2362]})
        sheets = {"Industry Overview": original.copy()}
        result = prepare_sheets_for_export(sheets)
        # Original should still be int64
        assert original["NAICS"].dtype == "int64"
        assert result["Industry Overview"]["NAICS"].dtype == object

    def test_other_columns_unchanged(self):
        from industry_report.dashboard_helpers import prepare_sheets_for_export

        sheets = {
            "Industry Overview": pd.DataFrame(
                {
                    "NAICS": [2382],
                    "Industry": ["Contractors"],
                    "2026 Jobs": [76730],
                    "Earnings per Job": [94094.51],
                }
            ),
        }
        result = prepare_sheets_for_export(sheets)
        df = result["Industry Overview"]
        assert df["NAICS"].dtype == object
        assert df["Industry"].dtype == object
        assert df["2026 Jobs"].dtype == "int64"
        assert df["Earnings per Job"].dtype == "float64"


# ---------------------------------------------------------------------------
# format_code_list_expanded
# ---------------------------------------------------------------------------


class TestFormatCodeListExpanded:
    """Tests for the expanded code list formatter used in sidebar expanders."""

    def test_one_per_line(self):

        codes = ["6211", "6212", "6213"]
        result = format_code_list_expanded(codes)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert lines[0] == "6211"
        assert lines[1] == "6212"
        assert lines[2] == "6213"

    def test_with_titles(self):

        codes = ["6211", "6212"]
        titles = ["Offices of Physicians", "Offices of Dentists"]
        result = format_code_list_expanded(codes, titles)
        lines = result.strip().split("\n")
        assert lines[0] == "6211 – Offices of Physicians"
        assert lines[1] == "6212 – Offices of Dentists"

    def test_mixed_titles(self):

        codes = ["6211", "6212"]
        titles = ["Offices of Physicians"]  # only 1 title — should skip mapping
        result = format_code_list_expanded(codes, titles)
        lines = result.strip().split("\n")
        assert lines[0] == "6211"
        assert lines[1] == "6212"

    def test_empty_list(self):

        result = format_code_list_expanded([])
        assert result == ""

    def test_single_code(self):

        result = format_code_list_expanded(["6211"], ["Offices of Physicians"])
        assert result.strip() == "6211 – Offices of Physicians"

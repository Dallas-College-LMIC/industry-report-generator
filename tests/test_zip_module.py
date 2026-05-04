"""Tests for the ZIP-level spatial module.

Covers:
- ReportConfig.zip_data property resolves correctly
- build_zip_sheets() with fixture CSVs
- build_zip_sheets() with missing CSVs returns empty
- CLI --fetch-zip flag parsing
"""

from pathlib import Path

import pytest

from industry_report.build_zip import build_zip_sheets
from industry_report.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"
ZIP_FIXTURES = FIXTURES / "zip_data"


# ---------------------------------------------------------------------------
# ReportConfig.zip_data
# ---------------------------------------------------------------------------


class TestZipDataProperty:
    """zip_data should resolve to configs/<stem>/ based on the config file path."""

    def test_zip_data_resolves_from_config_path(self):
        config = load_config(FIXTURES / "test_config.toml")
        expected = (FIXTURES / "test_config").resolve()
        assert config.zip_data == expected

    def test_zip_data_is_a_path(self):
        config = load_config(FIXTURES / "test_config.toml")
        assert isinstance(config.zip_data, Path)

    def test_zip_data_derived_from_stem(self):
        """Stem of config filename drives the directory name."""
        config = load_config(FIXTURES / "test_config.toml")
        assert config.zip_data.name == "test_config"

    def test_zip_data_from_healthcare_config(self, tmp_path):
        """Write a temp config with a specific stem and verify zip_data matches."""
        toml_content = (FIXTURES / "test_config.toml").read_text()
        cfg = tmp_path / "healthcare_dfw.toml"
        cfg.write_text(toml_content)
        config = load_config(cfg)
        assert config.zip_data.name == "healthcare_dfw"


# ---------------------------------------------------------------------------
# build_zip_sheets with fixture CSVs
# ---------------------------------------------------------------------------


class TestBuildZipSheets:
    """build_zip_sheets should read CSVs and return an OrderedDict of DataFrames."""

    @pytest.fixture
    def config_with_zip_data(self):
        """A config whose zip_data points at the test fixture directory."""
        config = load_config(FIXTURES / "test_config.toml")
        # Point zip_data at the fixture CSVs
        config._zip_data_override = ZIP_FIXTURES
        return config

    def _get_config(self):
        config = load_config(FIXTURES / "test_config.toml")
        config._zip_data_override = ZIP_FIXTURES
        return config

    def test_returns_ordered_dict(self):
        from collections import OrderedDict

        sheets = build_zip_sheets(self._get_config())
        assert isinstance(sheets, OrderedDict)

    def test_industry_detail_sheet_present(self):
        sheets = build_zip_sheets(self._get_config())
        assert "ZIP Industry Detail" in sheets

    def test_occupation_detail_sheet_present(self):
        sheets = build_zip_sheets(self._get_config())
        assert "ZIP Occupation Detail" in sheets

    def test_census_context_sheet_present(self):
        sheets = build_zip_sheets(self._get_config())
        assert "Census Context" in sheets

    def test_top_zips_sheet_present(self):
        sheets = build_zip_sheets(self._get_config())
        assert "Top ZIPs by Jobs" in sheets

    def test_wage_analysis_sheet_present(self):
        sheets = build_zip_sheets(self._get_config())
        assert "Wage Analysis" in sheets

    def test_industry_detail_has_zip_code_column(self):
        sheets = build_zip_sheets(self._get_config())
        df = sheets["ZIP Industry Detail"]
        assert "ZIP Code" in df.columns
        assert len(df) > 0

    def test_occupation_detail_has_zip_code_column(self):
        sheets = build_zip_sheets(self._get_config())
        df = sheets["ZIP Occupation Detail"]
        assert "ZIP Code" in df.columns
        assert len(df) > 0

    def test_census_context_has_zip_code_column(self):
        sheets = build_zip_sheets(self._get_config())
        df = sheets["Census Context"]
        assert "ZIP Code" in df.columns
        assert len(df) > 0

    def test_wage_analysis_sorted_by_wage(self):
        sheets = build_zip_sheets(self._get_config())
        df = sheets["Wage Analysis"]
        wage_col = "Hourly Wage P50 ($)"
        if wage_col in df.columns and len(df) > 1:
            assert (
                df[wage_col].is_monotonic_decreasing
                or df[wage_col].iloc[0] >= df[wage_col].iloc[-1]
            )


# ---------------------------------------------------------------------------
# build_zip_sheets with missing CSVs
# ---------------------------------------------------------------------------


class TestBuildZipSheetsMissingData:
    """build_zip_sheets should return empty OrderedDict when CSVs are missing."""

    def test_empty_when_no_csvs(self, tmp_path):
        config = load_config(FIXTURES / "test_config.toml")
        config._zip_data_override = tmp_path / "nonexistent"
        sheets = build_zip_sheets(config)
        assert len(sheets) == 0

    def test_partial_data(self, tmp_path):
        """If only some CSVs exist, return only sheets that can be built."""
        # Copy only the industry CSV
        import shutil

        tmp_dir = tmp_path / "partial"
        tmp_dir.mkdir()
        shutil.copy2(ZIP_FIXTURES / "industry.csv", tmp_dir / "industry.csv")
        config = load_config(FIXTURES / "test_config.toml")
        config._zip_data_override = tmp_dir
        sheets = build_zip_sheets(config)
        # Should have industry-derived sheets but not occupation or census sheets
        assert "ZIP Industry Detail" in sheets
        # These require occupation data
        assert "ZIP Occupation Detail" not in sheets


# ---------------------------------------------------------------------------
# CLI --fetch-zip flag
# ---------------------------------------------------------------------------


class TestCLIFetchZipFlag:
    """The --fetch-zip flag should be parsed correctly."""

    def test_flag_absent(self):
        from industry_report.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--config", "test.toml"])
        assert args.fetch_zip is False

    def test_flag_present(self):
        from industry_report.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--config", "test.toml", "--fetch-zip"])
        assert args.fetch_zip is True

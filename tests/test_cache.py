"""Tests for the MSA-level sheet cache module."""

import json
import time
from pathlib import Path

import pandas as pd
import pytest

from industry_report.cache import cache_age_hours, load_sheets_cache, save_sheets_cache
from industry_report.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config(tmp_path):
    """Create a config whose zip_data points at a temp directory."""
    cfg = load_config(FIXTURES / "test_config.toml")
    cfg._zip_data_override = tmp_path / "test_config"
    return cfg


class TestSaveAndLoad:
    def test_round_trip(self, config):
        sheets = {
            "Industry Overview": pd.DataFrame({"NAICS": ["6211"], "Jobs": [1000]}),
            "Notable Occupations": pd.DataFrame({"SOC": ["29-1141"], "Wage": [35.0]}),
        }
        save_sheets_cache(config, sheets)
        loaded = load_sheets_cache(config)
        assert loaded is not None
        assert set(loaded.keys()) == {"Industry Overview", "Notable Occupations"}
        assert len(loaded["Industry Overview"]) == 1
        assert loaded["Industry Overview"]["Jobs"].iloc[0] == 1000

    def test_returns_none_when_no_cache(self, config):
        result = load_sheets_cache(config)
        assert result is None

    def test_returns_none_when_expired(self, config):
        sheets = {"Test": pd.DataFrame({"a": [1]})}
        save_sheets_cache(config, sheets)

        # Backdate the manifest
        manifest_path = config.zip_data / ".cache" / "msa" / "_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["timestamp"] = time.time() - 999999  # very old
        manifest_path.write_text(json.dumps(manifest))

        result = load_sheets_cache(config, max_age_seconds=86400)
        assert result is None

    def test_loads_stale_with_zero_max_age(self, config):
        sheets = {"Test": pd.DataFrame({"a": [1]})}
        save_sheets_cache(config, sheets)

        # Backdate the manifest
        manifest_path = config.zip_data / ".cache" / "msa" / "_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["timestamp"] = time.time() - 999999
        manifest_path.write_text(json.dumps(manifest))

        result = load_sheets_cache(config, max_age_seconds=0)
        assert result is not None
        assert "Test" in result

    def test_skips_empty_dataframes(self, config):
        sheets = {
            "Full": pd.DataFrame({"a": [1, 2]}),
            "Empty": pd.DataFrame(),
        }
        save_sheets_cache(config, sheets)
        loaded = load_sheets_cache(config)
        assert loaded is not None
        assert "Full" in loaded
        assert "Empty" not in loaded

    def test_handles_slashes_in_name(self, config):
        sheets = {"A/B Sector": pd.DataFrame({"x": [1]})}
        save_sheets_cache(config, sheets)
        loaded = load_sheets_cache(config)
        assert loaded is not None
        assert "A/B Sector" in loaded


class TestCacheAge:
    def test_returns_none_when_no_cache(self, config):
        assert cache_age_hours(config) is None

    def test_returns_recent_age(self, config):
        save_sheets_cache(config, {"T": pd.DataFrame({"a": [1]})})
        age = cache_age_hours(config)
        assert age is not None
        assert age < 1  # just saved

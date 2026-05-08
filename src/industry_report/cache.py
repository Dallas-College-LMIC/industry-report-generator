"""Disk cache for MSA-level report sheets.

Stores DataFrames as CSVs under ``configs/<stem>/.cache/msa/``.
The cache is used to:
- Serve reports instantly on dashboard load
- Survive Lightcast API outages (stale cache > no data)
- Avoid re-fetching quarterly data on every page load

Cache layout::

    configs/<stem>/.cache/
        msa/
            Industry Overview.csv
            Notable Occupations.csv
            ...
            _manifest.json    ← cache metadata (timestamp, sheet names)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

from .config import ReportConfig

logger = logging.getLogger(__name__)

# Cache is considered fresh for 7 days (Lightcast updates quarterly)
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def _cache_dir(config: ReportConfig) -> Path:
    """Return the MSA cache directory, creating it if needed."""
    d = config.zip_data / ".cache" / "msa"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(config: ReportConfig) -> Path:
    return _cache_dir(config) / "_manifest.json"


def save_sheets_cache(
    config: ReportConfig,
    sheets: dict[str, pd.DataFrame],
) -> None:
    """Persist built sheets to disk as CSVs."""
    cache_dir = _cache_dir(config)
    saved_names = []

    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        # Sanitise sheet name for filesystem
        safe = name.replace("/", "_").replace("\\", "_")
        path = cache_dir / f"{safe}.csv"
        df.to_csv(path, index=False)
        saved_names.append(name)

    # Write manifest
    manifest = {
        "timestamp": time.time(),
        "sheets": saved_names,
    }
    _manifest_path(config).write_text(json.dumps(manifest))
    logger.info("Cached %d sheets to %s", len(saved_names), cache_dir)


def load_sheets_cache(
    config: ReportConfig,
    max_age_seconds: float = CACHE_TTL_SECONDS,
) -> dict[str, pd.DataFrame] | None:
    """Load sheets from disk cache.

    Returns ``None`` if no cache exists or cache is older than
    *max_age_seconds*.  Pass ``max_age_seconds=0`` to load regardless
    of age (used as API failure fallback).
    """
    manifest_path = _manifest_path(config)
    if not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Check age (0 means accept any age — used for fallback)
    if max_age_seconds > 0:
        age = time.time() - manifest.get("timestamp", 0)
        if age > max_age_seconds:
            return None

    cache_dir = _cache_dir(config)
    sheets: dict[str, pd.DataFrame] = {}

    for name in manifest.get("sheets", []):
        safe = name.replace("/", "_").replace("\\", "_")
        path = cache_dir / f"{safe}.csv"
        if path.exists():
            try:
                df = pd.read_csv(path)
                if not df.empty:
                    sheets[name] = df
            except Exception as exc:
                logger.info("Could not read cached sheet %s: %s", name, exc)

    return sheets if sheets else None


def cache_age_hours(config: ReportConfig) -> float | None:
    """Return cache age in hours, or ``None`` if no cache exists."""
    manifest_path = _manifest_path(config)
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text())
        return (time.time() - manifest["timestamp"]) / 3600
    except (json.JSONDecodeError, KeyError, OSError):
        return None

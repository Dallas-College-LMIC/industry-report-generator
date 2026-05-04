"""Fetch ZIP-level data from Lightcast Core LMI and Census ACS.

This module is the offline batch-fetcher invoked by ``--fetch-zip``.
It iterates over ZIP codes, queries the APIs per-ZIP with pickle caching
for resumability, and writes three aggregated CSV files to
``config.zip_data/``:

- ``industry.csv``   — per-ZIP industry employment/earnings
- ``occupation.csv``  — per-ZIP occupation employment/wages/openings
- ``census.csv``      — per-ZCTA demographics from Census ACS 5-year

Requires ``LCAPI_USER`` / ``LCAPI_PASS`` env vars for Lightcast.
Census fetching requires the ``censusdis`` package (optional ``[zip]`` extra).
"""

import hashlib
import json
import os
import pickle
import sys
from pathlib import Path

import pandas as pd

from .config import ReportConfig


# ---------------------------------------------------------------------------
# Geography manifest
# ---------------------------------------------------------------------------

DEFAULT_GEOGRAPHY_MANIFEST = {
    "for_lightcast": {
        "geography_type": "zipcode",
        "geography_ids": [],  # populated from companion file or config
    },
    "for_census": {
        "geography_type": "zip_code_tabulation_area",
        "state_fips": "48",
        "geography_ids": [],
    },
}


def _load_zip_list(config: ReportConfig) -> list[str]:
    """Load the ZIP code list for this config.

    Tries, in order:
    1. ``config.zip_data / geography_manifest.json``
    2. Falls back to an empty list (logs a warning)
    """
    manifest_path = config.zip_data / "geography_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        return manifest.get("for_lightcast", {}).get("geography_ids", [])

    print(f"WARNING: No geography manifest found at {manifest_path}")
    print("  Create a geography_manifest.json in the config data directory.")
    print("  See the report-framework for an example manifest.")
    return []


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(*args) -> str:
    return hashlib.md5(str(args).encode()).hexdigest()


def _cache_dir(config: ReportConfig) -> Path:
    d = config.zip_data / ".cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_pickle(path: Path) -> pd.DataFrame | None:
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def _save_pickle(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(df, f)


# ---------------------------------------------------------------------------
# Lightcast fetchers
# ---------------------------------------------------------------------------


def _get_lightcast_client():
    from pyghtcast.lightcast import Lightcast

    username = os.environ.get("LCAPI_USER")
    password = os.environ.get("LCAPI_PASS")
    if not username or not password:
        raise ValueError("Missing LCAPI_USER or LCAPI_PASS environment variables")
    return Lightcast(username, password)


def _discover_datarun(lc, dataset: str = "EMSI.us.Industry") -> str:
    """Get the latest datarun version for a dataset via pyghtcast CLI."""
    import subprocess

    result = subprocess.run(
        ["pyghtcast", "discover", "datasets", "--json"],
        capture_output=True,
        text=True,
    )
    output_lines = result.stdout.strip().split("\n")
    for i, line in enumerate(output_lines):
        if line.startswith("{"):
            json_str = "\n".join(output_lines[i:])
            break
    else:
        raise ValueError("Could not find JSON in pyghtcast discover output")

    datasets = json.loads(json_str)
    for ds in datasets["datasets"]:
        if ds["name"] == dataset:
            return sorted(ds["versions"], key=lambda x: list(map(int, x.split("."))))[-1]
    raise ValueError(f"Could not find {dataset} dataset")


def fetch_zip_industry(config: ReportConfig) -> Path | None:
    """Fetch per-ZIP industry data from Lightcast Core LMI.

    Iterates ZIPs from the geography manifest, queries EMSI.us.Industry
    with all NAICS codes aggregated, caches per-ZIP pickles, and writes
    ``config.zip_data / industry.csv``.

    Returns the output path on success, None on failure.
    """
    zip_codes = _load_zip_list(config)
    if not zip_codes:
        print("No ZIP codes to fetch. Skipping industry fetch.")
        return None

    cache = _cache_dir(config)
    lc = _get_lightcast_client()
    datarun = _discover_datarun(lc, "EMSI.us.Industry")

    columns = ["Jobs.2026", "Jobs.2031", "Earnings.2025"]
    naics = config.naics_codes
    group_name = config.naics_label or "Selected Industries"

    print(f"\nFetching ZIP industry data ({len(zip_codes)} ZIPs, datarun {datarun})...")
    all_data: list[pd.DataFrame] = []

    for i, zip_code in enumerate(zip_codes, 1):
        key = _cache_key(zip_code, json.dumps(naics), datarun, json.dumps(columns))
        pkl = cache / f"ind_zip_{key}.pkl"

        df = _load_pickle(pkl)
        if df is None:
            try:
                zip_prefixed = f"ZIP{zip_code}"
                constraints = [
                    {"dimensionName": "Area", "map": {zip_code: [zip_prefixed]}},
                    {"dimensionName": "Industry", "map": {group_name: naics}},
                    {"dimensionName": "ClassOfWorker", "map": {"QCEW Employees": ["1"]}},
                ]
                query = lc.build_query_corelmi(columns, constraints)
                df = lc.query_corelmi("EMSI.us.Industry", query, datarun=datarun)
                _save_pickle(pkl, df)
            except Exception as e:
                print(f"  ✗ ZIP {zip_code}: {e}")
                continue

        all_data.append(df)

        if i % 50 == 0 or i == len(zip_codes):
            print(f"  Progress: {i}/{len(zip_codes)} ZIPs")

    if not all_data:
        print("ERROR: No industry data fetched.")
        return None

    df = pd.concat(all_data, ignore_index=True)
    df["Industry_Group"] = group_name

    if "Jobs.2026" in df.columns and "Jobs.2031" in df.columns:
        df["Growth_2026_2031"] = df["Jobs.2031"] - df["Jobs.2026"]
        df["GrowthRate_2026_2031"] = (df["Jobs.2031"] / df["Jobs.2026"]) - 1

    out = config.zip_data / "industry.csv"
    config.zip_data.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"✓ Saved {len(df)} rows to {out}")
    return out


def fetch_zip_occupation(config: ReportConfig) -> Path | None:
    """Fetch per-ZIP occupation data from Lightcast Core LMI.

    Same pattern as fetch_zip_industry but for EMSI.us.Occupation.
    Writes ``config.zip_data / occupation.csv``.
    """
    zip_codes = _load_zip_list(config)
    if not zip_codes:
        print("No ZIP codes to fetch. Skipping occupation fetch.")
        return None

    cache = _cache_dir(config)
    lc = _get_lightcast_client()
    datarun = _discover_datarun(lc, "EMSI.us.Occupation")

    columns = [
        "Jobs.2026",
        "Jobs.2031",
        "Openings.2026",
        "Replacements.2026",
        "Earnings.Percentile10.2024",
        "Earnings.Percentile50.2024",
        "Earnings.Percentile90.2024",
    ]
    soc = config.soc_codes
    group_name = config.soc_label or "Selected Occupations"

    print(f"\nFetching ZIP occupation data ({len(zip_codes)} ZIPs, datarun {datarun})...")
    all_data: list[pd.DataFrame] = []

    for i, zip_code in enumerate(zip_codes, 1):
        key = _cache_key(zip_code, json.dumps(soc), datarun, json.dumps(columns))
        pkl = cache / f"occ_zip_{key}.pkl"

        df = _load_pickle(pkl)
        if df is None:
            try:
                zip_prefixed = f"ZIP{zip_code}"
                constraints = [
                    {"dimensionName": "Area", "map": {zip_code: [zip_prefixed]}},
                    {"dimensionName": "Occupation", "map": {group_name: soc}},
                    {"dimensionName": "ClassOfWorker", "map": {"QCEW Employees": ["1"]}},
                ]
                query = lc.build_query_corelmi(columns, constraints)
                df = lc.query_corelmi("EMSI.us.Occupation", query, datarun=datarun)
                _save_pickle(pkl, df)
            except Exception as e:
                print(f"  ✗ ZIP {zip_code}: {e}")
                continue

        all_data.append(df)

        if i % 50 == 0 or i == len(zip_codes):
            print(f"  Progress: {i}/{len(zip_codes)} ZIPs")

    if not all_data:
        print("ERROR: No occupation data fetched.")
        return None

    df = pd.concat(all_data, ignore_index=True)
    df["Occupation_Group"] = group_name

    if "Jobs.2026" in df.columns and "Jobs.2031" in df.columns:
        df["Growth_2026_2031"] = df["Jobs.2031"] - df["Jobs.2026"]
        df["GrowthRate_2026_2031"] = (df["Jobs.2031"] / df["Jobs.2026"]) - 1

    out = config.zip_data / "occupation.csv"
    config.zip_data.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"✓ Saved {len(df)} rows to {out}")
    return out


def fetch_zip_census(config: ReportConfig) -> Path | None:
    """Fetch per-ZCTA demographics from Census ACS 5-year via censusdis.

    Requires the ``censusdis`` package (``[zip]`` optional extra).
    Writes ``config.zip_data / census.csv``.
    """
    try:
        import censusdis.data as ced
    except ImportError:
        print("ERROR: censusdis not installed. Install with: uv sync --extra zip")
        return None

    zip_codes = _load_zip_list(config)
    if not zip_codes:
        print("No ZIP codes to fetch. Skipping census fetch.")
        return None

    cache = _cache_dir(config)

    # Census variables — same set as the reference implementation
    variables = {
        "B01001_001E": "Total_Population",
        "B01001_003E": "Male_Under_5",
        "B01001_004E": "Male_5_to_9",
        "B01001_005E": "Male_10_to_14",
        "B01001_006E": "Male_15_to_17",
        "B01001_007E": "Male_18_to_19",
        "B01001_010E": "Male_22_to_24",
        "B01001_011E": "Male_25_to_29",
        "B01001_012E": "Male_30_to_34",
        "B01001_013E": "Male_35_to_39",
        "B01001_014E": "Male_40_to_44",
        "B01001_015E": "Male_45_to_49",
        "B01001_016E": "Male_50_to_54",
        "B01001_017E": "Male_55_to_59",
        "B01001_018E": "Male_60_to_61",
        "B01001_019E": "Male_62_to_64",
        "B01001_020E": "Male_65_to_66",
        "B01001_021E": "Male_67_to_69",
        "B01001_022E": "Male_70_to_74",
        "B01001_023E": "Male_75_to_79",
        "B01001_024E": "Male_80_to_84",
        "B01001_025E": "Male_85_plus",
        "B01001_027E": "Female_Under_5",
        "B01001_028E": "Female_5_to_9",
        "B01001_029E": "Female_10_to_14",
        "B01001_030E": "Female_15_to_17",
        "B01001_031E": "Female_18_to_19",
        "B01001_034E": "Female_22_to_24",
        "B01001_035E": "Female_25_to_29",
        "B01001_036E": "Female_30_to_34",
        "B01001_037E": "Female_35_to_39",
        "B01001_038E": "Female_40_to_44",
        "B01001_039E": "Female_45_to_49",
        "B01001_040E": "Female_50_to_54",
        "B01001_041E": "Female_55_to_59",
        "B01001_042E": "Female_60_to_61",
        "B01001_043E": "Female_62_to_64",
        "B01001_044E": "Female_65_to_66",
        "B01001_045E": "Female_67_to_69",
        "B01001_046E": "Female_70_to_74",
        "B01001_047E": "Female_75_to_79",
        "B01001_048E": "Female_80_to_84",
        "B01001_049E": "Female_85_plus",
        "B02001_001E": "Total_Race",
        "B02001_002E": "White_Alone",
        "B02001_003E": "Black_Alone",
        "B02001_004E": "AI_AN_Alone",
        "B02001_005E": "Asian_Alone",
        "B02001_006E": "NHPI_Alone",
        "B02001_007E": "Other_Race_Alone",
        "B02001_008E": "Two_or_More_Races",
        "B03003_001E": "Total_Ethnicity",
        "B03003_002E": "Not_Hispanic",
        "B03003_003E": "Hispanic_Latino",
        "B15002_001E": "Total_Education",
        "B15002_002E": "Male_Less_9th",
        "B15002_003E": "Male_Some_HS",
        "B15002_004E": "Male_HS_Grad",
        "B15002_005E": "Male_Some_College",
        "B15002_006E": "Male_Associates",
        "B15002_007E": "Male_Bachelors",
        "B15002_008E": "Male_Graduate",
        "B15002_009E": "Female_Less_9th",
        "B15002_010E": "Female_Some_HS",
        "B15002_011E": "Female_HS_Grad",
        "B15002_012E": "Female_Some_College",
        "B15002_013E": "Female_Associates",
        "B15002_014E": "Female_Bachelors",
        "B15002_015E": "Female_Graduate",
        "B23025_001E": "Total_Employment",
        "B23025_002E": "In_Labor_Force",
        "B23025_003E": "Civilian_Labor_Force",
        "B23025_004E": "Employed",
        "B23025_005E": "Unemployed",
        "B23025_006E": "Armed_Forces",
        "B23025_007E": "Not_in_Labor_Force",
        "B19013_001E": "Median_Household_Income",
        "B19301_001E": "Per_Capita_Income",
        "B11001_001E": "Total_Households",
    }

    var_codes = list(variables.keys())
    state_fips = config.state_code

    # Check cache
    key = _cache_key("census", state_fips, sorted(zip_codes), sorted(var_codes))
    pkl = cache / f"census_{key}.pkl"

    import time

    if pkl.exists():
        print(f"\n✓ Loading census data from cache: {pkl}")
        df = _load_pickle(pkl)
    else:
        print(f"\nFetching census data ({len(zip_codes)} ZCTAs, {len(var_codes)} variables)...")
        zcta_str = ",".join(zip_codes)

        # Batch variables (Census API ~50 vars max per call)
        all_results: list[pd.DataFrame] = []
        batch_size = 45
        batches = [var_codes[i : i + batch_size] for i in range(0, len(var_codes), batch_size)]

        for batch_num, var_batch in enumerate(batches, 1):
            print(f"  Batch {batch_num}/{len(batches)}: {len(var_batch)} variables...")
            try:
                df_batch = ced.download(
                    dataset="acs/acs5",
                    vintage=2022,
                    download_variables=var_batch,
                    zip_code_tabulation_area=zcta_str,
                )
                all_results.append(df_batch)
                print(f"    → Got {len(df_batch)} ZCTAs")
                time.sleep(0.2)
            except Exception as e:
                print(f"    Warning: {str(e)[:100]}")

        if not all_results:
            print("ERROR: No census data retrieved.")
            return None

        # Merge batches
        df = all_results[0]
        for df_next in all_results[1:]:
            df = df.merge(df_next, on="ZIP_CODE_TABULATION_AREA", how="outer")

        _save_pickle(pkl, df)
        print(f"✓ Cached to {pkl}")

    # Rename columns
    rename_map = {k: v for k, v in variables.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    if "ZIP_CODE_TABULATION_AREA" in df.columns:
        df = df.rename(columns={"ZIP_CODE_TABULATION_AREA": "ZCTA"})

    # Derived columns
    df["Population_Under_18"] = (
        df.get("Male_Under_5", 0)
        + df.get("Male_5_to_9", 0)
        + df.get("Male_10_to_14", 0)
        + df.get("Male_15_to_17", 0)
        + df.get("Female_Under_5", 0)
        + df.get("Female_5_to_9", 0)
        + df.get("Female_10_to_14", 0)
        + df.get("Female_15_to_17", 0)
    )

    df["Population_18_to_64"] = (
        df.get("Male_18_to_19", 0)
        + df.get("Male_22_to_24", 0)
        + df.get("Male_25_to_29", 0)
        + df.get("Male_30_to_34", 0)
        + df.get("Male_35_to_39", 0)
        + df.get("Male_40_to_44", 0)
        + df.get("Male_45_to_49", 0)
        + df.get("Male_50_to_54", 0)
        + df.get("Male_55_to_59", 0)
        + df.get("Male_60_to_61", 0)
        + df.get("Male_62_to_64", 0)
        + df.get("Female_18_to_19", 0)
        + df.get("Female_22_to_24", 0)
        + df.get("Female_25_to_29", 0)
        + df.get("Female_30_to_34", 0)
        + df.get("Female_35_to_39", 0)
        + df.get("Female_40_to_44", 0)
        + df.get("Female_45_to_49", 0)
        + df.get("Female_50_to_54", 0)
        + df.get("Female_55_to_59", 0)
        + df.get("Female_60_to_61", 0)
        + df.get("Female_62_to_64", 0)
    )

    df["Population_65_plus"] = (
        df.get("Male_65_to_66", 0)
        + df.get("Male_67_to_69", 0)
        + df.get("Male_70_to_74", 0)
        + df.get("Male_75_to_79", 0)
        + df.get("Male_80_to_84", 0)
        + df.get("Male_85_plus", 0)
        + df.get("Female_65_to_66", 0)
        + df.get("Female_67_to_69", 0)
        + df.get("Female_70_to_74", 0)
        + df.get("Female_75_to_79", 0)
        + df.get("Female_80_to_84", 0)
        + df.get("Female_85_plus", 0)
    )

    df["Working_Age_25_54"] = (
        df.get("Male_25_to_29", 0)
        + df.get("Male_30_to_34", 0)
        + df.get("Male_35_to_39", 0)
        + df.get("Male_40_to_44", 0)
        + df.get("Male_45_to_49", 0)
        + df.get("Male_50_to_54", 0)
        + df.get("Female_25_to_29", 0)
        + df.get("Female_30_to_34", 0)
        + df.get("Female_35_to_39", 0)
        + df.get("Female_40_to_44", 0)
        + df.get("Female_45_to_49", 0)
        + df.get("Female_50_to_54", 0)
    )

    df["Less_than_HS"] = (
        df.get("Male_Less_9th", 0)
        + df.get("Male_Some_HS", 0)
        + df.get("Female_Less_9th", 0)
        + df.get("Female_Some_HS", 0)
    )
    df["HS_Grad_or_Equivalent"] = df.get("Male_HS_Grad", 0) + df.get("Female_HS_Grad", 0)
    df["Some_College"] = df.get("Male_Some_College", 0) + df.get("Female_Some_College", 0)
    df["Associates_Degree"] = df.get("Male_Associates", 0) + df.get("Female_Associates", 0)
    df["Bachelors_or_Higher"] = (
        df.get("Male_Bachelors", 0)
        + df.get("Male_Graduate", 0)
        + df.get("Female_Bachelors", 0)
        + df.get("Female_Graduate", 0)
    )

    df["Labor_Force_Participation_Rate"] = (
        df.get("In_Labor_Force", 0)
        / df.get("Total_Employment", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)
    df["Unemployment_Rate"] = (
        df.get("Unemployed", 0)
        / df.get("Civilian_Labor_Force", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)

    df["Pct_White"] = (
        df.get("White_Alone", 0)
        / df.get("Total_Race", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)
    df["Pct_Black"] = (
        df.get("Black_Alone", 0)
        / df.get("Total_Race", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)
    df["Pct_Asian"] = (
        df.get("Asian_Alone", 0)
        / df.get("Total_Race", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)
    df["Pct_Hispanic"] = (
        df.get("Hispanic_Latino", 0)
        / df.get("Total_Ethnicity", pd.Series(1, index=df.index)).replace(0, 1)
        * 100
    ).round(2)

    out = config.zip_data / "census.csv"
    config.zip_data.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"✓ Saved {len(df)} rows to {out}")
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_fetch_zip(config: ReportConfig) -> None:
    """Run all three ZIP-level fetchers in sequence.

    Called by the CLI when ``--fetch-zip`` is set.
    """
    print("=" * 60)
    print(f"ZIP-Level Data Fetch: {config.name}")
    print(f"Region: {config.msa_name}")
    print(f"Data dir: {config.zip_data}")
    print("=" * 60)

    config.zip_data.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. Industry
    try:
        results["industry"] = fetch_zip_industry(config)
    except Exception as e:
        print(f"\n✗ Industry fetch failed: {e}")
        results["industry"] = None

    # 2. Occupation
    try:
        results["occupation"] = fetch_zip_occupation(config)
    except Exception as e:
        print(f"\n✗ Occupation fetch failed: {e}")
        results["occupation"] = None

    # 3. Census
    try:
        results["census"] = fetch_zip_census(config)
    except Exception as e:
        print(f"\n✗ Census fetch failed: {e}")
        results["census"] = None

    # Summary
    print("\n" + "=" * 60)
    print("FETCH SUMMARY")
    print("=" * 60)
    for name, path in results.items():
        if path:
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ✗ {name}: failed")

    if not any(results.values()):
        print("\nERROR: All fetches failed. Check credentials and network.")
        sys.exit(1)
    else:
        print("\n✓ ZIP-level data fetch complete.")

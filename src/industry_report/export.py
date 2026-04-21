"""Export assembled sheet frames to a formatted Excel workbook."""

from collections import OrderedDict
from pathlib import Path

import dclmic_export
import pandas as pd

from .config import ReportConfig

# Column formatting rules per sheet
COL_FORMAT = {
    "Notable Occupations": {
        "2026 Jobs": "thousands",
        "2029 Jobs": "thousands",
        "Avg. Annual Openings": "thousands",
        "2026-2029 Change": "thousands",
        "% Change": "percent",
        "Entry Wage (P10)": "currency",
        "Median Hourly Wage": "currency",
        "Experienced Wage (P90)": "currency",
    },
    "Wage Analysis": {
        "Entry Wage (P10)": "currency",
        "Median Hourly Wage": "currency",
        "Experienced Wage (P90)": "currency",
    },
    "In-Demand Skills": {
        "Projected Skill Growth": "percent",
    },
    "Regional Comparison": {
        "Jobs (Total)": "thousands",
        "Earnings per Job": "currency",
        "Projected Job Growth (2026-2029)": "percent",
    },
}


def export_workbook(frames: OrderedDict[str, pd.DataFrame], config: ReportConfig) -> Path:
    """Write all sheet frames to a formatted Excel file using dclmic_export.

    Returns the path to the output file.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    output_path = config.output_dir / f"{config.name.replace(' ', '_')}_Report_Data.xlsx"

    output_dir_str = str(config.output_dir)
    if not output_dir_str.endswith("/"):
        output_dir_str += "/"

    dclmic_export.save_dfs_as_xl(
        list_of_frames=list(frames.values()),
        col_format=COL_FORMAT,
        path=output_dir_str,
        file_name=output_path.stem,
        sheet_titles=list(frames.keys()),
    )

    return output_path

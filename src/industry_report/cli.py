"""CLI entrypoint for the industry report generator."""

import argparse
import sys

from .build import build_all_sheets
from .config import load_config
from .export import export_workbook


def main():
    parser = argparse.ArgumentParser(description="Generate industry report data tables")
    parser.add_argument("--config", required=True, help="Path to TOML config file")
    args = parser.parse_args()

    config = load_config(args.config)
    print(f"Generating report: {config.name}")
    print(f"NAICS codes: {len(config.naics_codes)} industries")
    print(f"SOC codes: {len(config.soc_codes)} occupations")
    print(f"Region: {config.msa_name}")
    print()

    print("Fetching data...")
    sheets = build_all_sheets(config)

    if not sheets:
        print("ERROR: No data could be fetched. Check API credentials and/or manual input file paths.")
        sys.exit(1)

    print(f"Built {len(sheets)} sheets: {', '.join(sheets.keys())}")

    output_path = export_workbook(sheets, config)
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()

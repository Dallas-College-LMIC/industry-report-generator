"""Launcher for the Streamlit dashboard.

Usage:
    industry-report-dashboard
"""

import subprocess
import sys
from pathlib import Path


def main():
    dashboard = Path(__file__).with_name("dashboard.py")
    cmd = [sys.executable, "-m", "streamlit", "run", str(dashboard)]
    sys.exit(subprocess.call(cmd))

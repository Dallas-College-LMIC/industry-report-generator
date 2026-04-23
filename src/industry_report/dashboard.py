"""Streamlit dashboard for the industry report generator.

Run locally:
    streamlit run src/industry_report/dashboard.py

Or via the installed console script:
    industry-report-dashboard run src/industry_report/dashboard.py
"""

import sys
from pathlib import Path

# Allow running directly with `streamlit run src/industry_report/dashboard.py`
# without having the package formally installed.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
for p in (str(SRC_ROOT), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from industry_report.build import build_all_sheets  # noqa: E402
from industry_report.config import load_config  # noqa: E402
from industry_report.export import export_workbook  # noqa: E402

st.set_page_config(
    page_title="Industry Report Dashboard",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar — config selection
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ Settings")

config_dir = PROJECT_ROOT / "configs"
config_files = sorted(config_dir.glob("*.toml")) if config_dir.exists() else []
config_names = [p.name for p in config_files]

if not config_files:
    st.error(f"No TOML config files found in {config_dir}. Please add one and refresh.")
    st.stop()

selected_name = st.sidebar.selectbox("Select industry config", config_names)
selected_path = config_dir / selected_name

config = load_config(selected_path)
st.sidebar.markdown("---")
st.sidebar.write(f"**Industry:** {config.name}")
st.sidebar.write(f"**Region:** {config.msa_name}")
st.sidebar.write(f"**NAICS codes:** {len(config.naics_codes)}")
st.sidebar.write(f"**SOC codes:** {len(config.soc_codes)}")
st.sidebar.markdown("---")

# ---------------------------------------------------------------------------
# Main — generate & display
# ---------------------------------------------------------------------------
st.title(f"📊 {config.name} — Industry Report Dashboard")
st.caption(f"Region: {config.msa_name}  •  MSA: {config.msa_code}")

if st.button("🔄 Generate Report from Lightcast", type="primary", use_container_width=True):
    with st.spinner("Fetching data from Lightcast APIs..."):
        try:
            sheets = build_all_sheets(config)
        except Exception as e:
            st.error(f"Failed to build report: {e}")
            st.stop()

    if not sheets:
        st.error("No data could be fetched. Check API credentials and/or manual input file paths.")
        st.stop()

    st.success(f"Built {len(sheets)} sheets.")

    # -----------------------------------------------------------------------
    # Quick metrics (if available)
    # -----------------------------------------------------------------------
    metric_cols = st.columns(4)

    # Total jobs
    if "Notable Occupations" in sheets:
        occ_df = sheets["Notable Occupations"]
        jobs_col = next((c for c in occ_df.columns if "2026 Jobs" in c or "Jobs" in c), None)
        if jobs_col:
            total_jobs = int(occ_df[jobs_col].sum())
            metric_cols[0].metric("Total Jobs", f"{total_jobs:,}")

        wage_col = next((c for c in occ_df.columns if "Median Hourly Wage" in c), None)
        if wage_col:
            avg_wage = occ_df[wage_col].mean()
            metric_cols[1].metric("Avg. Median Wage", f"${avg_wage:,.2f}/hr")

    if "Did you know" in sheets:
        summary = sheets["Did you know"]
        # summary is a two-column DataFrame from dclmic_export.dict_to_df_for_xl
        if not summary.empty and len(summary.columns) >= 2:
            for _, row in summary.iterrows():
                label = str(row.iloc[0])
                val = row.iloc[1]
                if "posting" in label.lower() and isinstance(val, (int, float)):
                    metric_cols[2].metric("Monthly Postings", f"{int(val):,}")
                elif "employer" in label.lower() and isinstance(val, (int, float)):
                    metric_cols[3].metric("Employers Competing", f"{int(val):,}")

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Wage chart
    # -----------------------------------------------------------------------
    if "Notable Occupations" in sheets:
        occ_df = sheets["Notable Occupations"].copy()

        occ_label_col = next(
            (c for c in occ_df.columns if c in ("Occupation", "SOC")), occ_df.columns[0]
        )
        wage_col = next((c for c in occ_df.columns if "Median Hourly Wage" in c), None)

        if wage_col and occ_label_col:
            chart_df = occ_df[[occ_label_col, wage_col]].dropna().sort_values(wage_col)
            fig = px.bar(
                chart_df,
                x=wage_col,
                y=occ_label_col,
                orientation="h",
                title="Median Hourly Wage by Occupation",
                labels={wage_col: "Median Hourly Wage ($)", occ_label_col: ""},
                color=wage_col,
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=max(400, len(chart_df) * 35))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Sheets as expanders
    # -----------------------------------------------------------------------
    st.subheader("📋 Report Sheets")
    for sheet_name, df in sheets.items():
        with st.expander(f"{sheet_name}  ({len(df)} rows)"):
            st.dataframe(df, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # Download Excel
    # -----------------------------------------------------------------------
    st.markdown("---")
    try:
        output_path = export_workbook(sheets, config)
        with open(output_path, "rb") as f:
            st.download_button(
                label="📥 Download Excel Report",
                data=f,
                file_name=output_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    except Exception as e:
        st.error(f"Could not generate Excel download: {e}")

else:
    st.info(
        "Select a config from the sidebar and click **Generate Report from Lightcast** to begin."
    )

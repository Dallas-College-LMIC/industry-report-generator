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
# Main — tabs
# ---------------------------------------------------------------------------
st.title(f"📊 {config.name} — Industry Report Dashboard")
st.caption(f"Region: {config.msa_name}  •  MSA: {config.msa_code}")

tab_msa, tab_zip = st.tabs(["MSA-Level Report", "ZIP-Level Spatial"])

# ===========================================================================
# TAB 1: MSA-Level Report (existing functionality)
# ===========================================================================
with tab_msa:
    if st.button("🔄 Generate Report from Lightcast", type="primary", use_container_width=True):
        with st.spinner("Fetching data from Lightcast APIs..."):
            try:
                sheets = build_all_sheets(config)
            except Exception as e:
                st.error(f"Failed to build report: {e}")
                st.stop()

        if not sheets:
            st.error(
                "No data could be fetched. Check API credentials and/or manual input file paths."
            )
            st.stop()

        st.success(f"Built {len(sheets)} sheets.")

        # -------------------------------------------------------------------
        # Quick metrics (if available)
        # -------------------------------------------------------------------
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
            if not summary.empty and len(summary.columns) >= 2:
                for _, row in summary.iterrows():
                    label = str(row.iloc[0])
                    val = row.iloc[1]
                    if "posting" in label.lower() and isinstance(val, (int, float)):
                        metric_cols[2].metric("Monthly Postings", f"{int(val):,}")
                    elif "employer" in label.lower() and isinstance(val, (int, float)):
                        metric_cols[3].metric("Employers Competing", f"{int(val):,}")

        st.markdown("---")

        # -------------------------------------------------------------------
        # Wage chart
        # -------------------------------------------------------------------
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

        # -------------------------------------------------------------------
        # Job Posting Analytics
        # -------------------------------------------------------------------
        has_jpa = any(
            k in sheets
            for k in (
                "Notable Employers in DFW",
                "In-Demand Skills",
                "Top Common Skills",
                "Top Software Skills",
                "Advertised Wage Trend",
            )
        )

        if has_jpa:
            st.subheader("💼 Job Posting Analytics")

            # --- Salary trend ---
            if "Advertised Wage Trend" in sheets:
                trend_df = sheets["Advertised Wage Trend"].copy()
                if "Month" in trend_df.columns and "Advertised Salary" in trend_df.columns:
                    fig_trend = px.line(
                        trend_df,
                        x="Month",
                        y="Advertised Salary",
                        title="Advertised Salary Trend",
                        markers=True,
                        labels={"Advertised Salary": "Advertised Salary ($/hr)"},
                    )
                    fig_trend.update_traces(line_color="#1f77b4", marker_size=8)
                    fig_trend.update_layout(yaxis_tickprefix="$")

                    # Add postings as secondary axis
                    if "Job Postings" in trend_df.columns:
                        from plotly.subplots import make_subplots

                        fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
                        fig_trend.add_trace(
                            px.line(
                                trend_df,
                                x="Month",
                                y="Advertised Salary",
                                markers=True,
                            )
                            .update_traces(line_color="#1f77b4", name="Salary ($/hr)")
                            .data[0],
                            secondary_y=False,
                        )
                        fig_trend.add_trace(
                            px.bar(trend_df, x="Month", y="Job Postings")
                            .update_traces(marker_color="#aec7e8", name="Postings", opacity=0.6)
                            .data[0],
                            secondary_y=True,
                        )
                        fig_trend.update_layout(
                            title="Advertised Salary Trend & Postings Volume",
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        )
                        fig_trend.update_yaxes(title_text="Salary ($/hr)", secondary_y=False)
                        fig_trend.update_yaxes(title_text="Postings", secondary_y=True)

                    st.plotly_chart(fig_trend, use_container_width=True)

            jpa_col1, jpa_col2 = st.columns(2)

            # --- Top employers ---
            if "Notable Employers in DFW" in sheets:
                emp_df = sheets["Notable Employers in DFW"].copy()
                postings_col = next((c for c in emp_df.columns if "Unique Postings" in c), None)
                if postings_col and "Company" in emp_df.columns:
                    chart = emp_df.head(10).sort_values(postings_col)
                    fig_emp = px.bar(
                        chart,
                        x=postings_col,
                        y="Company",
                        orientation="h",
                        title="Top Employers by Unique Postings",
                        color=postings_col,
                        color_continuous_scale="Blues",
                    )
                    fig_emp.update_layout(showlegend=False, height=max(300, len(chart) * 30))
                    jpa_col1.plotly_chart(fig_emp, use_container_width=True)

            # --- In-demand skills ---
            if "In-Demand Skills" in sheets:
                skills_df = sheets["In-Demand Skills"].copy()
                postings_col = next(
                    (c for c in skills_df.columns if "% of Total Postings" in c), None
                )
                if postings_col and "Skills" in skills_df.columns:
                    chart = skills_df.head(15).sort_values(postings_col)
                    fig_skills = px.bar(
                        chart,
                        x=postings_col,
                        y="Skills",
                        orientation="h",
                        title="Top Specialized Skills",
                        color=postings_col,
                        color_continuous_scale="Blues",
                    )
                    fig_skills.update_layout(showlegend=False, height=max(300, len(chart) * 28))
                    jpa_col2.plotly_chart(fig_skills, use_container_width=True)

            # --- Common + Software skills side by side ---
            skill_col1, skill_col2 = st.columns(2)

            if "Top Common Skills" in sheets:
                cs_df = sheets["Top Common Skills"].copy()
                pct_col = next((c for c in cs_df.columns if "% of Total Postings" in c), None)
                if pct_col and "Skills" in cs_df.columns:
                    chart = cs_df.head(15).sort_values(pct_col)
                    fig_cs = px.bar(
                        chart,
                        x=pct_col,
                        y="Skills",
                        orientation="h",
                        title="Top Common (Soft) Skills",
                        color=pct_col,
                        color_continuous_scale="Blues",
                    )
                    fig_cs.update_layout(showlegend=False, height=max(300, len(chart) * 28))
                    skill_col1.plotly_chart(fig_cs, use_container_width=True)

            if "Top Software Skills" in sheets:
                sw_df = sheets["Top Software Skills"].copy()
                pct_col = next((c for c in sw_df.columns if "% of Total Postings" in c), None)
                if pct_col and "Skills" in sw_df.columns:
                    chart = sw_df.head(15).sort_values(pct_col)
                    fig_sw = px.bar(
                        chart,
                        x=pct_col,
                        y="Skills",
                        orientation="h",
                        title="Top Software Skills",
                        color=pct_col,
                        color_continuous_scale="Blues",
                    )
                    fig_sw.update_layout(showlegend=False, height=max(300, len(chart) * 28))
                    skill_col2.plotly_chart(fig_sw, use_container_width=True)

            st.markdown("---")

        # -------------------------------------------------------------------
        # Sheets as expanders
        # -------------------------------------------------------------------
        st.subheader("📋 Report Sheets")
        for sheet_name, df in sheets.items():
            with st.expander(f"{sheet_name}  ({len(df)} rows)"):
                st.dataframe(df, use_container_width=True, hide_index=True)

        # -------------------------------------------------------------------
        # Download Excel
        # -------------------------------------------------------------------
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

# ===========================================================================
# TAB 2: ZIP-Level Spatial
# ===========================================================================
with tab_zip:
    from industry_report.build_zip import build_zip_sheets  # noqa: E402

    industry_csv = config.zip_data / "industry.csv"
    has_zip_data = industry_csv.exists()

    if has_zip_data:
        st.success(f"ZIP-level data found in `{config.zip_data}`")

        # Build sheets (instant — reads CSVs only)
        zip_sheets = build_zip_sheets(config)

        if not zip_sheets:
            st.warning("ZIP data files exist but could not be parsed.")
            st.stop()

        st.write(f"Built {len(zip_sheets)} ZIP-level sheets from cached CSVs.")

        # -------------------------------------------------------------------
        # ZIP-level choropleth map
        # -------------------------------------------------------------------
        st.subheader("🗺️ ZIP-Level Map")

        # Try to build a choropleth from available data
        map_df = None
        map_value_col = None

        if "ZIP Industry Detail" in zip_sheets:
            ind = zip_sheets["ZIP Industry Detail"]
            if "ZIP Code" in ind.columns and "Industry Jobs 2026" in ind.columns:
                map_df = ind[["ZIP Code", "Industry Jobs 2026"]].copy()
                map_value_col = "Industry Jobs 2026"
        elif "ZIP Occupation Detail" in zip_sheets:
            occ = zip_sheets["ZIP Occupation Detail"]
            if "ZIP Code" in occ.columns and "Occupation Jobs 2026" in occ.columns:
                map_df = occ[["ZIP Code", "Occupation Jobs 2026"]].copy()
                map_value_col = "Occupation Jobs 2026"

        if map_df is not None and map_value_col:
            # Let user choose metric
            metric_options = {}
            for sheet_name, df in zip_sheets.items():
                if "ZIP Code" in df.columns:
                    for col in df.columns:
                        if (
                            df[col].dtype in ("float64", "int64", "Float64", "Int64")
                            and col != "ZIP Code"
                        ):
                            metric_options[f"{sheet_name}: {col}"] = (sheet_name, col)

            if metric_options:
                selected_metric = st.selectbox(
                    "Choose metric to map",
                    list(metric_options.keys()),
                    index=0,
                )
                chosen_sheet, chosen_col = metric_options[selected_metric]
                map_df = zip_sheets[chosen_sheet][["ZIP Code", chosen_col]].copy()
                map_value_col = chosen_col

            # NOTE: plotly doesn't support USA-zip locationmode natively.
            # Using a bar chart as a reliable ZIP-level visualization.
            fig = px.bar(
                map_df.nlargest(25, map_value_col).sort_values(map_value_col),
                x=map_value_col,
                y="ZIP Code",
                orientation="h",
                title=f"Top 25 ZIP Codes by {map_value_col}",
                color=map_value_col,
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=600, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # -------------------------------------------------------------------
        # Quick ZIP metrics
        # -------------------------------------------------------------------
        if "ZIP Industry Detail" in zip_sheets:
            ind = zip_sheets["ZIP Industry Detail"]
            zip_cols = st.columns(3)
            jobs_col = "Industry Jobs 2026" if "Industry Jobs 2026" in ind.columns else None
            if jobs_col:
                zip_cols[0].metric("Total ZIPs", f"{len(ind):,}")
                zip_cols[1].metric("Total Industry Jobs", f"{int(ind[jobs_col].sum()):,}")
                if "Avg Earnings per Job ($)" in ind.columns:
                    avg_earn = ind["Avg Earnings per Job ($)"].mean()
                    zip_cols[2].metric("Avg Earnings/Job", f"${avg_earn:,.0f}")

        st.markdown("---")

        # -------------------------------------------------------------------
        # ZIP data tables
        # -------------------------------------------------------------------
        st.subheader("📋 ZIP-Level Sheets")
        for sheet_name, df in zip_sheets.items():
            with st.expander(f"{sheet_name}  ({len(df)} rows)"):
                st.dataframe(df, use_container_width=True, hide_index=True)

        # -------------------------------------------------------------------
        # Download ZIP Excel
        # -------------------------------------------------------------------
        st.markdown("---")
        try:
            zip_output_path = export_workbook(zip_sheets, config)
            with open(zip_output_path, "rb") as f:
                st.download_button(
                    label="📥 Download ZIP-Level Excel",
                    data=f,
                    file_name=zip_output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f"Could not generate ZIP Excel download: {e}")

    else:
        st.warning("No ZIP-level data found for this industry.")
        st.info(
            "To generate ZIP-level data, run:\n\n"
            f"```\nindustry-report --config configs/{selected_name} --fetch-zip\n```\n\n"
            "This is a batch job that fetches data from Lightcast and Census APIs (~30-60 min). "
            "The resulting CSVs will be stored in `configs/<config_stem>/` and will appear here instantly."
        )

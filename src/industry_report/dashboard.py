"""Streamlit dashboard for the industry report generator.

Run locally:
    streamlit run src/industry_report/dashboard.py

Or via the installed console script:
    industry-report-dashboard run src/industry_report/dashboard.py
"""

import os
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
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from industry_report.build import build_all_sheets  # noqa: E402
from industry_report.config import load_config  # noqa: E402
from industry_report.export import export_workbook  # noqa: E402

# Load .env so API keys are available
from industry_report.cli import _load_env  # noqa: E402

_load_env()

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

tab_msa, tab_zip, tab_pulse = st.tabs(["MSA-Level Report", "ZIP-Level Spatial", "Pulse"])

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

# ===========================================================================
# TAB 3: Pulse — Frequently-Updated Economic Indicators
# ===========================================================================
with tab_pulse:
    import os

    from industry_report.build_pulse import build_pulse_data, compute_key_metrics  # noqa: E402
    from plotly.subplots import make_subplots  # noqa: E402
    import plotly.graph_objects as go  # noqa: E402

    has_fred = bool(os.environ.get("FRED_API_KEY"))
    has_socrata = bool(os.environ.get("SOCRATA_APP_TOKEN"))

    if not has_fred and not has_socrata:
        st.warning("No API keys configured for Pulse data sources.")
        st.info(
            "To enable the Pulse tab, set the following environment variables:\n\n"
            "| Env var | Source | Registration |\n"
            "|---|---|---|\n"
            "| `FRED_API_KEY` | UI claims, Dallas Fed, BFS, BLS | [Register](https://fredaccount.stlouisfed.org) (free, instant) |\n"
            "| `SOCRATA_APP_TOKEN` | WARN notices, TX sales tax | [Register](https://data.texas.gov/profile/app_tokens) (optional) |\n"
            "| `BLS_API_KEY` | BLS employment (direct) | [Register](https://data.bls.gov/registrationEngine/) (optional) |\n\n"
            "Add them to your `.env` file or set them as Streamlit Cloud secrets."
        )

    # --- Fetch all pulse data (cached for 1 day) ---
    @st.cache_data(ttl=86400, show_spinner=False)
    def _fetch_pulse():
        return build_pulse_data(config)

    with st.spinner("Fetching pulse data from public APIs..."):
        pulse = _fetch_pulse()

    if not pulse:
        st.info("No pulse data sources returned data. Check API keys and network connectivity.")
    else:
        metrics = compute_key_metrics(pulse)
        sources_available = len(pulse)
        st.caption(
            f"{sources_available} data source{'s' if sources_available != 1 else ''} available"
        )

        # ----------------------------------------------------------------
        # Key Metrics Bar
        # ----------------------------------------------------------------
        st.subheader("📊 Key Metrics")
        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)

        mc1.metric(
            "Initial UI Claims (TX)",
            f"{metrics.get('ui_initial_claims', '—'):,.0f}"
            if metrics.get("ui_initial_claims")
            else "—",
            f"{metrics.get('ui_initial_claims_wow'):+.1f}%"
            if metrics.get("ui_initial_claims_wow") is not None
            else None,
            delta_color="inverse",
        )
        mc2.metric(
            "WARN Notices (30d)",
            f"{metrics.get('warn_30day_count', '—')}"
            if metrics.get("warn_30day_count") is not None
            else "—",
            f"{metrics.get('warn_30day_layoffs', 0):,} workers"
            if metrics.get("warn_30day_layoffs")
            else None,
        )
        mc3.metric(
            "Dallas Fed Mfg Index",
            f"{metrics.get('dallas_fed_mfg_index', '—'):+.1f}"
            if metrics.get("dallas_fed_mfg_index") is not None
            else "—",
        )
        mc4.metric(
            "DFW Employment",
            f"{metrics.get('bls_employment_level', '—'):,.0f}"
            if metrics.get("bls_employment_level")
            else "—",
            f"{metrics.get('bls_employment_yoy'):+.1f}% YoY"
            if metrics.get("bls_employment_yoy") is not None
            else None,
        )
        mc5.metric(
            "Business Applications (TX)",
            f"{metrics.get('bfs_business_apps', '—'):,.0f}"
            if metrics.get("bfs_business_apps")
            else "—",
            f"{metrics.get('bfs_yoy'):+.1f}% YoY" if metrics.get("bfs_yoy") is not None else None,
        )
        mc6.metric(
            "Sales Tax YoY (Dallas Co.)",
            f"{metrics.get('sales_tax_yoy'):+.1f}%"
            if metrics.get("sales_tax_yoy") is not None
            else "—",
        )

        st.markdown("---")

        # ----------------------------------------------------------------
        # Labor Market Stress Panel
        # ----------------------------------------------------------------
        has_stress = "ui_claims" in pulse or "warn_notices" in pulse or "dallas_fed" in pulse
        if has_stress:
            st.subheader("🔴 Labor Market Stress")

            stress_col1, stress_col2 = st.columns(2)

            # UI Claims trend
            if "ui_claims" in pulse:
                ui = pulse["ui_claims"]
                initial = ui[ui["series_id"] == "TXICLAIMS"].sort_values("date")
                if not initial.empty:
                    fig_ui = go.Figure()
                    fig_ui.add_trace(
                        go.Scatter(
                            x=initial["date"],
                            y=initial["value"],
                            name="Initial Claims",
                            line=dict(color="#1f77b4"),
                        )
                    )
                    if "4wk_ma" in initial.columns:
                        fig_ui.add_trace(
                            go.Scatter(
                                x=initial["date"],
                                y=initial["4wk_ma"],
                                name="4-Week MA",
                                line=dict(color="#ff7f0e", width=2),
                            )
                        )
                    fig_ui.update_layout(
                        title="Texas Initial UI Claims (Weekly)",
                        yaxis_title="Claims",
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    )
                    stress_col1.plotly_chart(fig_ui, use_container_width=True)

            # WARN notices over time
            if "warn_notices" in pulse:
                warn = pulse["warn_notices"]
                if "month" in warn.columns and not warn.empty:
                    warn_monthly = (
                        warn.groupby("month")
                        .agg(
                            layoff_count=("layoff_count", "sum"), notices=("layoff_count", "count")
                        )
                        .reset_index()
                    )
                    fig_warn = px.bar(
                        warn_monthly,
                        x="month",
                        y="layoff_count",
                        title="WARN Layoffs by Month (DFW Counties)",
                        labels={"layoff_count": "Workers Affected", "month": ""},
                    )
                    fig_warn.update_layout(height=400)
                    stress_col2.plotly_chart(fig_warn, use_container_width=True)

            # Dallas Fed employment index overlay
            if "dallas_fed" in pulse:
                fed = pulse["dallas_fed"]
                emp_idx = fed[
                    (fed["survey"] == "Manufacturing") & (fed["series_name"] == "Employment")
                ].sort_values("date")
                if not emp_idx.empty:
                    fig_fed = px.line(
                        emp_idx,
                        x="date",
                        y="value",
                        title="Dallas Fed Manufacturing Employment Index",
                        labels={"value": "Index", "date": ""},
                        markers=True,
                    )
                    fig_fed.add_hline(
                        y=0,
                        line_dash="dash",
                        line_color="gray",
                        annotation_text="Expansion / Contraction",
                    )
                    fig_fed.update_layout(height=400)
                    st.plotly_chart(fig_fed, use_container_width=True)

            st.markdown("---")

        # ----------------------------------------------------------------
        # Economic Activity Panel
        # ----------------------------------------------------------------
        has_econ = "bls_employment" in pulse or "bfs" in pulse or "sales_tax" in pulse
        if has_econ:
            st.subheader("💼 Economic Activity")

            econ_col1, econ_col2 = st.columns(2)

            # BLS employment trend
            if "bls_employment" in pulse:
                bls = pulse["bls_employment"]
                total_nf = bls[bls["industry"] == "Total Nonfarm"].sort_values("date")
                if not total_nf.empty:
                    fig_bls = px.line(
                        total_nf,
                        x="date",
                        y="value",
                        title=f"DFW Nonfarm Employment (MSA {config.msa_code})",
                        labels={"value": "Jobs", "date": ""},
                        markers=True,
                    )
                    fig_bls.update_layout(height=400, yaxis_tickformat=",")
                    econ_col1.plotly_chart(fig_bls, use_container_width=True)

            # BFS business applications
            if "bfs" in pulse:
                bfs = pulse["bfs"].sort_values("date")
                if not bfs.empty:
                    fig_bfs = px.bar(
                        bfs,
                        x="date",
                        y="value",
                        title="TX Business Applications (Monthly)",
                        labels={"value": "Applications", "date": ""},
                    )
                    fig_bfs.update_layout(height=400)
                    econ_col2.plotly_chart(fig_bfs, use_container_width=True)

            # Sales tax allocations by county
            if "sales_tax" in pulse:
                stax = pulse["sales_tax"]
                if "county" in stax.columns and not stax.empty:
                    fig_st = px.line(
                        stax,
                        x="date",
                        y="value",
                        color="county",
                        title="Sales Tax Allocations by DFW County",
                        labels={"value": "Allocation ($)", "date": "", "county": "County"},
                    )
                    fig_st.update_layout(height=400, yaxis_tickprefix="$", yaxis_tickformat=",")
                    st.plotly_chart(fig_st, use_container_width=True)

            st.markdown("---")

        # ----------------------------------------------------------------
        # Employer Sentiment Panel
        # ----------------------------------------------------------------
        if "dallas_fed" in pulse:
            st.subheader("🗣️ Employer Sentiment")

            fed = pulse["dallas_fed"]

            # Multi-line chart: Mfg + Service Sector general business activity
            gba = fed[fed["series_name"] == "General Business Activity"].sort_values("date")
            if not gba.empty:
                fig_sent = px.line(
                    gba,
                    x="date",
                    y="value",
                    color="survey",
                    title="General Business Activity Index (Manufacturing vs. Services)",
                    labels={"value": "Index", "date": "", "survey": "Survey"},
                    markers=True,
                )
                fig_sent.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_sent.update_layout(height=400)
                st.plotly_chart(fig_sent, use_container_width=True)

            # Latest survey results table
            latest_month = fed["date"].max()
            latest_data = fed[fed["date"] == latest_month]
            if not latest_data.empty:
                st.caption(f"Latest survey data: {latest_month.strftime('%B %Y')}")
                display_cols = ["survey", "series_name", "value"]
                show_cols = [c for c in display_cols if c in latest_data.columns]
                st.dataframe(
                    latest_data[show_cols].rename(
                        columns={"survey": "Survey", "series_name": "Indicator", "value": "Index"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            st.markdown("---")

        # ----------------------------------------------------------------
        # Job Postings Panel (Lightcast JPA)
        # ----------------------------------------------------------------
        has_jpa = "jpa_totals" in pulse or "jpa_skills" in pulse or "jpa_employers" in pulse
        if has_jpa:
            st.subheader("💼 Job Postings (Lightcast)")

            jpa_col1, jpa_col2 = st.columns(2)

            # Key JPA metrics
            if "jpa_totals" in pulse:
                totals = pulse["jpa_totals"]
                postings_val = None
                companies_val = None
                if isinstance(totals, pd.DataFrame) and not totals.empty:
                    row = totals.iloc[0]
                    postings_val = row.get("unique_postings")
                    companies_val = row.get("unique_companies")
                elif isinstance(totals, dict):
                    postings_val = totals.get("unique_postings")
                    companies_val = totals.get("unique_companies")
                if postings_val:
                    jpa_col1.metric("Unique Postings", f"{int(postings_val):,}")
                if companies_val:
                    jpa_col2.metric("Companies Posting", f"{int(companies_val):,}")

            # Top employers
            if "jpa_employers" in pulse:
                emp_df = pulse["jpa_employers"]
                postings_col = next(
                    (
                        c
                        for c in emp_df.columns
                        if "Unique Postings" in c or "unique_postings" in c.lower()
                    ),
                    None,
                )
                name_col = next(
                    (
                        c
                        for c in emp_df.columns
                        if "Company" in c or "company" in c.lower() or "name" in c.lower()
                    ),
                    emp_df.columns[0],
                )
                if postings_col:
                    chart = emp_df.head(10).sort_values(postings_col)
                    fig_jpa_emp = px.bar(
                        chart,
                        x=postings_col,
                        y=name_col,
                        orientation="h",
                        title="Top Employers by Postings",
                        color=postings_col,
                        color_continuous_scale="Blues",
                    )
                    fig_jpa_emp.update_layout(showlegend=False, height=max(300, len(chart) * 30))
                    jpa_col1.plotly_chart(fig_jpa_emp, use_container_width=True)

            # Top skills
            if "jpa_skills" in pulse:
                skills_df = pulse["jpa_skills"]
                pct_col = next(
                    (
                        c
                        for c in skills_df.columns
                        if "% of Total Postings" in c or "postings" in c.lower()
                    ),
                    skills_df.columns[1] if len(skills_df.columns) > 1 else None,
                )
                skill_name_col = next(
                    (c for c in skills_df.columns if "Skill" in c or "skill" in c.lower()),
                    skills_df.columns[0],
                )
                if pct_col:
                    chart = skills_df.head(15).sort_values(pct_col)
                    fig_jpa_skills = px.bar(
                        chart,
                        x=pct_col,
                        y=skill_name_col,
                        orientation="h",
                        title="Top Specialized Skills",
                        color=pct_col,
                        color_continuous_scale="Blues",
                    )
                    fig_jpa_skills.update_layout(showlegend=False, height=max(300, len(chart) * 28))
                    jpa_col2.plotly_chart(fig_jpa_skills, use_container_width=True)

            st.markdown("---")

        # ----------------------------------------------------------------
        # Recent WARN Notices Table
        # ----------------------------------------------------------------
        if "warn_notices" in pulse:
            st.subheader("⚠️ Recent WARN Notices (DFW)")

            warn = pulse["warn_notices"]
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
            if "layoff_date" in warn.columns:
                recent = warn[warn["layoff_date"] >= cutoff].copy()
            elif "notice_date" in warn.columns:
                recent = warn[warn["notice_date"] >= cutoff].copy()
            else:
                recent = warn.copy()

            if not recent.empty:
                # County filter
                counties_available = (
                    sorted(recent["county"].dropna().unique()) if "county" in recent.columns else []
                )
                if counties_available:
                    selected_counties = st.multiselect(
                        "Filter by county",
                        counties_available,
                        default=counties_available,
                        key="warn_county_filter",
                    )
                    recent = recent[recent["county"].isin(selected_counties)]

                display_cols = {
                    "company": "Company",
                    "county": "County",
                    "city": "City",
                    "layoff_count": "Workers Affected",
                    "notice_date": "Notice Date",
                    "layoff_date": "Layoff Date",
                }
                show_cols = [c for c in display_cols if c in recent.columns]
                recent_display = recent[show_cols].rename(columns=display_cols)
                st.dataframe(recent_display, use_container_width=True, hide_index=True)
                st.caption(f"{len(recent)} notices in the last 90 days")
            else:
                st.info("No WARN notices filed in the last 90 days for DFW counties.")

            st.markdown("---")

        # ----------------------------------------------------------------
        # Data freshness
        # ----------------------------------------------------------------
        st.subheader("🕐 Data Freshness")
        freshness_data = []
        source_labels = {
            "ui_claims": "UI Claims (FRED)",
            "warn_notices": "WARN Notices (Socrata)",
            "dallas_fed": "Dallas Fed Surveys (FRED)",
            "sales_tax": "Sales Tax (Socrata)",
            "bfs": "Business Formation (Census/FRED)",
            "bls_employment": "BLS Employment (BLS/FRED)",
            "jpa_totals": "Job Postings (Lightcast JPA)",
            "jpa_skills": "Job Posting Skills (Lightcast JPA)",
            "jpa_employers": "Job Posting Employers (Lightcast JPA)",
        }
        for key, label in source_labels.items():
            if key in pulse:
                df = pulse[key]
                date_col = (
                    "date" if "date" in df.columns else "month" if "month" in df.columns else None
                )
                if date_col:
                    latest = pd.to_datetime(df[date_col]).max()
                    days_ago = (pd.Timestamp.now() - latest).days
                    staleness = "⚠️ Stale" if days_ago > 60 else "✅ Fresh"
                    freshness_data.append(
                        {
                            "Source": label,
                            "Latest Data": latest.strftime("%Y-%m-%d"),
                            "Days Ago": days_ago,
                            "Status": staleness,
                        }
                    )

        if freshness_data:
            st.dataframe(
                pd.DataFrame(freshness_data),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No data sources available to check freshness.")

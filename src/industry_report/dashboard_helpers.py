"""Pure helper functions for the dashboard.

These functions contain no Streamlit calls and can be tested without
a running Streamlit app.
"""

import pandas as pd


def format_code_list_expanded(
    codes: list[str],
    titles: list[str] | None = None,
) -> str:
    """Format codes as one-per-line string for a sidebar expander.

    Each line is ``code – title`` when titles are available, or just ``code``
    otherwise.  Returns an empty string for an empty list.
    """
    if not codes:
        return ""

    title_map = dict(zip(codes, titles)) if titles and len(titles) == len(codes) else {}
    lines = []
    for c in codes:
        t = title_map.get(c)
        lines.append(f"{c} – {t}" if t else str(c))
    return "\n".join(lines)


def compute_freshness_rows(pulse: dict) -> list[dict]:
    """Build freshness table rows from a pulse data dict.

    Clamps negative "days ago" to 0 for future release dates and shows
    a "📅 Upcoming" status instead of a negative number.  Uses
    source-specific staleness thresholds based on update cadence.
    """
    # source key → (display label, stale threshold in days, date column name)
    source_meta = {
        "ui_claims": ("UI Claims (FRED)", 14, None),
        "warn_notices": ("WARN Notices (Socrata)", 14, "notice_date"),
        "dallas_fed": ("Dallas Fed Surveys (FRED)", 45, None),
        "sales_tax": ("Sales Tax (Socrata)", 45, None),
        "bls_employment": ("BLS Employment (BLS/FRED)", 45, None),
        "bfs": ("Business Formation (FRED/Census)", 45, None),
        "jpa_totals": ("Job Postings (Lightcast JPA)", 45, None),
        "jpa_skills": ("Job Posting Skills (Lightcast JPA)", 45, None),
        "jpa_employers": ("Job Posting Employers (Lightcast JPA)", 45, None),
    }
    rows: list[dict] = []
    for key, (label, stale_days, date_override) in source_meta.items():
        if key not in pulse:
            continue
        df = pulse[key]
        # Use override date column, or auto-detect
        if date_override and date_override in df.columns:
            date_col = date_override
        else:
            date_col = (
                "date" if "date" in df.columns else "month" if "month" in df.columns else None
            )
        if not date_col:
            continue
        latest = pd.to_datetime(df[date_col]).max()
        delta = pd.Timestamp.now() - latest
        days_ago = max(delta.days, 0)  # clamp negatives to 0
        if delta.days < 0:
            staleness = "📅 Upcoming"
        elif days_ago > stale_days:
            staleness = "⚠️ Stale"
        else:
            staleness = "✅ Fresh"
        rows.append(
            {
                "Source": label,
                "Latest Data": latest.strftime("%Y-%m-%d"),
                "Days Ago": days_ago,
                "Status": staleness,
            }
        )
    return rows


def pick_label_column(df: pd.DataFrame) -> str:
    """Pick the best human-readable label column for chart Y-axis.

    Prefers title columns ("Occupation", "Industry") over code columns
    ("SOC", "NAICS").  Falls back to the first column if nothing matches.
    """
    preference = ["Occupation", "Industry", "SOC", "NAICS"]
    for col in preference:
        if col in df.columns:
            return col
    return df.columns[0]


def prepare_sales_tax_chart(df: pd.DataFrame) -> pd.DataFrame | None:
    """Prepare sales tax DataFrame for charting.

    * Adds a "YoY Change" column (year-over-year % change per county).
    * Returns None if the required 'county' column is missing.
    * Adds a boolean 'Dallas County' column used as the chart colour key
      so Dallas stands out from other counties.
    """
    if "county" not in df.columns or df.empty:
        return None

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["county", "date"])

    # Year-over-year % change per county
    out["YoY Change"] = out.groupby("county")["value"].pct_change(periods=12).mul(100).round(1)

    return out


# Columns that should always be plain text in Excel exports.
_TEXT_COLUMNS = {"NAICS", "SOC", "ZIP Code"}


def prepare_sheets_for_export(
    sheets: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Return a copy of *sheets* with code columns cast to string.

    NAICS codes (e.g. 2382 → "2382"), SOC codes, and ZIP codes get
    stored as text so Excel doesn't format them with thousands separators
    or drop leading zeros.  Other columns are left untouched.
    """
    out: dict[str, pd.DataFrame] = {}
    for name, df in sheets.items():
        new_df = df.copy()
        for col in _TEXT_COLUMNS:
            if col in new_df.columns:
                new_df[col] = new_df[col].astype(str).str.zfill(5 if col == "ZIP Code" else 0)
        out[name] = new_df
    return out

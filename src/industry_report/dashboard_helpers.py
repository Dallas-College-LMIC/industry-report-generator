"""Pure helper functions for the dashboard.

These functions contain no Streamlit calls and can be tested without
a running Streamlit app.
"""

import pandas as pd


def format_code_list(
    codes: list[str],
    label: str,
    titles: list[str] | None = None,
    max_inline: int = 5,
) -> str:
    """Format a list of codes (with optional titles) for sidebar display.

    Shows up to *max_inline* codes with their titles (if available), then
    summarises the rest as "… and N more".  Falls back to a simple count
    when the list is very long.
    """
    n = len(codes)
    if n == 0:
        return f"0 {label} codes"

    # Build a lookup from code → title
    title_map = dict(zip(codes, titles)) if titles and len(titles) == n else {}

    if n <= max_inline:
        parts = []
        for c in codes:
            t = title_map.get(c)
            parts.append(f"{c} – {t}" if t else str(c))
        return ", ".join(parts)

    # Long list: show first few then count
    shown = []
    for c in codes[:3]:
        t = title_map.get(c)
        shown.append(f"{c} – {t}" if t else str(c))
    remaining = n - 3
    return ", ".join(shown) + f", … and {remaining} more ({n} {label} codes total)"


def compute_freshness_rows(pulse: dict) -> list[dict]:
    """Build freshness table rows from a pulse data dict.

    Clamps negative "days ago" to 0 for future release dates and shows
    a "📅 Upcoming" status instead of a negative number.
    """
    source_labels = {
        "ui_claims": "UI Claims (FRED)",
        "dallas_fed": "Dallas Fed Surveys (FRED)",
        "warn": "WARN Notices (Socrata)",
        "sales_tax": "Sales Tax (Socrata)",
        "bls_employment": "BLS Employment (BLS/FRED)",
        "bfs": "Business Formation (FRED/Census)",
        "jpa_totals": "Job Postings (Lightcast JPA)",
        "jpa_skills": "Job Posting Skills (Lightcast JPA)",
        "jpa_employers": "Job Posting Employers (Lightcast JPA)",
    }
    rows: list[dict] = []
    for key, label in source_labels.items():
        if key not in pulse:
            continue
        df = pulse[key]
        date_col = "date" if "date" in df.columns else "month" if "month" in df.columns else None
        if not date_col:
            continue
        latest = pd.to_datetime(df[date_col]).max()
        delta = pd.Timestamp.now() - latest
        days_ago = max(delta.days, 0)  # clamp negatives to 0
        if delta.days < 0:
            staleness = "📅 Upcoming"
        elif days_ago > 90:
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

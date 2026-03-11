"""
intents/macro_indicator.py
Handler for MACRO_INDICATOR intent.

Output template (from spec):
    Headline:  [Metric] [Geography]: [Value] [Unit] ([Period])
               YoY change: [+/- X pp]
    Comparators: US, Japan
    Chart: Time series, last 5 years, monthly, plotly line chart
    Annotation: Source | Vintage | Next release
"""

import sys
import os
import pandas as pd
import plotly.graph_objects as go

# Make sure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from providers.eurostat import fetch as eurostat_fetch
from providers.imf import fetch_indicator as imf_fetch
from render import build_report


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_hicp_eurozone(years: int = 5) -> pd.DataFrame:
    """Fetch Eurozone HICP YoY % from Eurostat, last N years."""
    df = eurostat_fetch(
        "prc_hicp_manr",
        {"geo": "EA", "unit": "RCH_A", "coicop": "CP00"}
    )
    df = df[["time", "value"]].rename(columns={"time": "date", "value": "EA"})
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m")
    df = df.sort_values("date")

    cutoff = df["date"].max() - pd.DateOffset(years=years)
    return df[df["date"] >= cutoff].reset_index(drop=True)


def _get_imf_cpi(country_code: str, label: str, years: int = 5) -> pd.Series:
    """
    Fetch annual CPI % change from IMF for a country, return Series indexed by year-end date.
    Falls back gracefully.
    """
    try:
        current_year = pd.Timestamp.today().year
        df = imf_fetch("PCPIPCH", [country_code],
                       start_year=current_year - years, end_year=current_year)
        df = df[df["country"] == country_code][["year", "value"]].copy()
        df["date"] = pd.to_datetime(df["year"].astype(str) + "-12-31")
        df = df.sort_values("date").set_index("date")["value"]
        df.name = label
        return df
    except Exception as e:
        print(f"[IMF] Could not fetch {label} CPI: {e}")
        return pd.Series(name=label, dtype=float)


def _try_fred_cpi(series_id: str, label: str, years: int = 5) -> pd.Series:
    """Try FRED for monthly CPI YoY; returns empty Series if key unavailable."""
    try:
        from providers.fred import fetch_series
        cutoff = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")
        df = fetch_series(series_id, observation_start=cutoff, units="pc1")
        df = df.set_index("date")["value"]
        df.name = label
        return df
    except Exception as e:
        print(f"[FRED] {label}: {e}. Falling back to IMF annual data.")
        return pd.Series(name=label, dtype=float)


# ── Main entry point ──────────────────────────────────────────────────────────

def run(params: dict = None):
    """
    Execute the MACRO_INDICATOR query for Eurozone HICP inflation.
    params keys: geography (default "EA"), metric (default "hicp"), years (default 5)
                 _query, _intent, _reasoning injected by router
    """
    params    = params or {}
    years     = int(params.get("years", 5))
    query     = params.get("_query", "Eurozone inflation")
    intent    = params.get("_intent", "MACRO_INDICATOR")
    reasoning = params.get("_reasoning", [])

    print("\n⏳ Fetching Eurozone HICP (YoY %) from Eurostat…")
    ez_df = _get_hicp_eurozone(years)

    latest_date = ez_df["date"].max()
    latest_val  = ez_df.loc[ez_df["date"] == latest_date, "EA"].iloc[0]

    prev_month = latest_date - pd.DateOffset(months=1)
    prev_rows  = ez_df[ez_df["date"] == prev_month]
    prev_val   = prev_rows["EA"].iloc[0] if not prev_rows.empty else None
    mom_change = round(latest_val - prev_val, 2) if prev_val is not None else None

    one_year_ago = latest_date - pd.DateOffset(years=1)
    yago_rows    = ez_df[ez_df["date"] == one_year_ago]
    yago_val     = yago_rows["EA"].iloc[0] if not yago_rows.empty else None
    yoy_change   = round(latest_val - yago_val, 2) if yago_val is not None else None

    # ── Comparators ──────────────────────────────────────────────────────────
    print("⏳ Fetching US CPI (YoY %) from FRED / IMF…")
    us_monthly = _try_fred_cpi("CPIAUCSL", "US CPI", years)
    us_annual  = _get_imf_cpi("USA", "US CPI", years) if us_monthly.empty else pd.Series(name="US CPI", dtype=float)

    print("⏳ Fetching Japan CPI (YoY %) from FRED / IMF…")
    jp_monthly = _try_fred_cpi("JPNCPIALLMINMEI", "Japan CPI", years)
    jp_annual  = _get_imf_cpi("JPN", "Japan CPI", years) if jp_monthly.empty else pd.Series(name="Japan CPI", dtype=float)

    def latest_val_from(monthly, annual):
        if not monthly.empty:
            return round(monthly.iloc[-1], 2), monthly.index[-1].strftime("%b %Y"), "FRED (monthly)"
        elif not annual.empty:
            return round(annual.iloc[-1], 2), str(int(annual.index[-1].year)), "IMF WEO (annual)"
        return None, "n/a", "n/a"

    us_latest, us_period, us_src = latest_val_from(us_monthly, us_annual)
    jp_latest, jp_period, jp_src = latest_val_from(jp_monthly, jp_annual)

    vintage_str = latest_date.strftime("%B %Y")

    # ── Console summary ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  📊 EUROZONE HICP INFLATION (All Items, YoY %)")
    print(f"{'='*60}")
    print(f"  {'Eurozone HICP YoY':<30} {latest_val:>7.1f}%  {latest_date.strftime('%b %Y')}")
    if yoy_change is not None:
        print(f"  {'  vs 1 year ago':<30} {yoy_change:>+7.2f}pp")
    if mom_change is not None:
        print(f"  {'  MoM change':<30} {mom_change:>+7.2f}pp")
    print(f"  {'-'*56}")
    if us_latest is not None:
        print(f"  {'US CPI YoY':<30} {us_latest:>7.1f}%  {us_period}")
    if jp_latest is not None:
        print(f"  {'Japan CPI YoY':<30} {jp_latest:>7.1f}%  {jp_period}")
    print(f"{'='*60}")

    # ── Build Plotly figure ───────────────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=ez_df["date"], y=ez_df["EA"],
        mode="lines", name="Eurozone HICP",
        line=dict(color="#003399", width=2.5),
    ))

    if not us_monthly.empty:
        fig.add_trace(go.Scatter(x=us_monthly.index, y=us_monthly.values,
            mode="lines", name="US CPI",
            line=dict(color="#CC0001", width=1.8, dash="dash")))
    elif not us_annual.empty:
        fig.add_trace(go.Scatter(x=us_annual.index, y=us_annual.values,
            mode="lines+markers", name="US CPI (annual, IMF)",
            line=dict(color="#CC0001", width=1.8, dash="dash")))

    if not jp_monthly.empty:
        fig.add_trace(go.Scatter(x=jp_monthly.index, y=jp_monthly.values,
            mode="lines", name="Japan CPI",
            line=dict(color="#FF6600", width=1.8, dash="dot")))
    elif not jp_annual.empty:
        fig.add_trace(go.Scatter(x=jp_annual.index, y=jp_annual.values,
            mode="lines+markers", name="Japan CPI (annual, IMF)",
            line=dict(color="#FF6600", width=1.8, dash="dot")))

    fig.add_hline(y=0, line_dash="dot", line_color="grey", line_width=1)
    fig.add_hline(y=2, line_dash="dash", line_color="#003399", line_width=1,
                  annotation_text="ECB target 2%", annotation_position="bottom right",
                  annotation_font=dict(size=10, color="#003399"))

    fig.add_annotation(
        x=latest_date, y=latest_val,
        text=f"EZ: {latest_val:.1f}%<br>{latest_date.strftime('%b %Y')}",
        showarrow=True, arrowhead=2, arrowcolor="#003399",
        font=dict(size=11, color="#003399"),
        bgcolor="rgba(255,255,255,0.85)", bordercolor="#003399",
        ax=50, ay=-45,
    )

    fig.update_layout(
        title=dict(text="HICP / CPI Inflation (YoY %) — Eurozone vs US vs Japan",
                   font=dict(size=15)),
        xaxis=dict(title="", tickformat="%b %Y", showgrid=True, gridcolor="#e8eaf0"),
        yaxis=dict(title="YoY % change", showgrid=True, gridcolor="#e8eaf0", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=480, margin=dict(t=50, b=30),
    )

    # ── Build table rows for render ───────────────────────────────────────────
    table_rows = [
        {"label": "Eurozone HICP YoY",
         "value": f"{latest_val:.1f}%",
         "period": latest_date.strftime("%b %Y"),
         "change": yoy_change,
         "change_unit": " pp vs 1y ago",
         "bold": True},
        {"label": "&nbsp;&nbsp;MoM change",
         "value": f"{mom_change:+.2f} pp" if mom_change is not None else "n/a",
         "period": latest_date.strftime("%b %Y"),
         "change": None},
        {"label": "─── Comparators ───",
         "value": "", "period": "", "change": None, "separator": True},
    ]
    if us_latest is not None:
        table_rows.append({
            "label": f"US CPI YoY",
            "note": us_src,
            "value": f"{us_latest:.1f}%",
            "period": us_period,
            "change": round(us_latest - latest_val, 2),
            "change_unit": " pp vs EZ",
        })
    if jp_latest is not None:
        table_rows.append({
            "label": "Japan CPI YoY",
            "note": jp_src,
            "value": f"{jp_latest:.1f}%",
            "period": jp_period,
            "change": round(jp_latest - latest_val, 2),
            "change_unit": " pp vs EZ",
        })

    # ── Add reasoning detail about actual series used ─────────────────────────
    if reasoning:
        reasoning.append({
            "step": "Output",
            "detail": (
                f"Eurozone HICP: <strong>{latest_val:.1f}%</strong> ({latest_date.strftime('%b %Y')}) — "
                f"YoY Δ: <strong>{yoy_change:+.2f} pp</strong> &nbsp;|&nbsp; "
                f"US: <strong>{us_latest:.1f}%</strong> ({us_period}) &nbsp;|&nbsp; "
                f"Japan: <strong>{jp_latest:.1f}%</strong> ({jp_period})"
                if (us_latest and jp_latest) else
                f"Eurozone HICP: <strong>{latest_val:.1f}%</strong> ({latest_date.strftime('%b %Y')})"
            ),
        })

    # ── Render full HTML report ───────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.html")
    saved = build_report(
        query=query,
        intent=intent,
        reasoning=reasoning,
        table_rows=table_rows,
        fig=fig,
        meta={
            "source":    "Eurostat (prc_hicp_manr) + " + (us_src if us_latest else "IMF"),
            "vintage":   vintage_str,
            "series_id": "prc_hicp_manr / PCPIPCH",
            "endpoint":  "ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/",
        },
        out_path=out_path,
    )

    print(f"\n📊 Report saved → {saved}")
    import webbrowser
    webbrowser.open(f"file:///{saved.replace(os.sep, '/')}")

    print(f"\n✅ Source: Eurostat (prc_hicp_manr)")
    print(f"📅 Vintage: {vintage_str}")
    print(f"📊 Chart: output.html (opened automatically)")

    return {
        "ez_hicp_latest": latest_val,
        "ez_hicp_period": latest_date.strftime("%Y-%m"),
        "yoy_change_pp":  yoy_change,
        "us_cpi_latest":  us_latest,
        "jp_cpi_latest":  jp_latest,
    }

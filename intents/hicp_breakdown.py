"""
intents/hicp_breakdown.py

Eurozone HICP component breakdown handler.

Fetches the five standard analytical groupings from Eurostat prc_hicp_manr:
  • Energy
  • Food (incl. alcohol & tobacco)  — COICOP: TOT_X_NRG_SERV = non-energy, non-services
    Note: Eurostat does not publish a single "food" special aggregate under prc_hicp_manr;
    we use FOOD = CP01+CP02 (food & non-alc. beverages + alcohol & tobacco) via multi-call.
  • Non-energy industrial goods (NEIG) — IGX_E
  • Services — SERV
  • All items — CP00 (headline)

Charts:
  1. Stacked area — component YoY contributions over 5 years
  2. Latest-month bar — breakdown of current headline rate

Output: output.html via render.py
"""

import os
import sys
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from providers.eurostat import fetch as eurostat_fetch
from render import build_report


# ── COICOP codes and display config ──────────────────────────────────────────

COMPONENTS = {
    "Energy":         {"coicop": "NRG",         "colour": "#CC0001", "dash": "solid"},
    "Food & alc/tab": {"coicop": "FOOD",        "colour": "#F5A623", "dash": "solid"},
    "NEIG":           {"coicop": "IGD_NNRG",    "colour": "#6EC6F0", "dash": "solid"},
    "Services":       {"coicop": "SERV",        "colour": "#003399", "dash": "solid"},
    "Core (ex. E&F)": {"coicop": "TOT_X_NRG_FOOD", "colour": "#6B7280", "dash": "dot"},
}

HEADLINE = {"coicop": "CP00", "colour": "#1A1A2E", "dash": "dot"}

# Weights (approximate, ECB 2024 weights — used only for visual annotation)
APPROX_WEIGHTS = {
    "Energy":          0.097,
    "Food & alc/tab":  0.199,
    "NEIG":            0.261,
    "Services":        0.443,
    "Core (ex. E&F)": None,   # composite — no single weight
}


def _hex_rgba(hex_colour: str, alpha: float = 0.45) -> str:
    """Convert a 6-digit hex colour to an rgba() string for Plotly fillcolor."""
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_component(coicop: str, years: int, geo: str = "EA") -> pd.Series:
    """
    Fetch prc_hicp_manr for a single COICOP code.
    Eurostat does not expose FOOD as a single code; we compute it as a
    residual: headline − NEIG − Services − Energy.
    Returns a Series indexed by datetime, named by coicop.
    """
    df = eurostat_fetch(
        "prc_hicp_manr",
        {"geo": geo, "unit": "RCH_A", "coicop": coicop},
    )
    df = df[["time", "value"]].rename(columns={"time": "date", "value": coicop})
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m")
    df = df.sort_values("date")

    cutoff = df["date"].max() - pd.DateOffset(years=years)
    df = df[df["date"] >= cutoff]
    return df.set_index("date")[coicop]


def _fetch_all(years: int = 5, geo: str = "EA") -> pd.DataFrame:
    """
    Fetch headline + all component series, returning a wide DataFrame.
    Food is derived as: headline − Energy − NEIG − Services (residual method).
    """
    print("⏳  Fetching Eurozone HICP headline (CP00)…")
    headline = _fetch_component("CP00", years, geo)

    series_map = {}
    for name, cfg in COMPONENTS.items():
        print(f"⏳  Fetching {name} ({cfg['coicop']})…")
        try:
            series_map[name] = _fetch_component(cfg["coicop"], years, geo)
        except Exception as e:
            print(f"   ⚠  Could not fetch {name}: {e}")

    df = pd.DataFrame({"All items": headline})
    for name, s in series_map.items():
        df[name] = s

    df = df.dropna(subset=["All items"])

    # Forward-fill up to 3 months to handle release-lag differences between components
    df = df.ffill(limit=3)

    # Drop any row where ALL component columns are still NaN (hard alignment guard)
    component_cols = [c for c in COMPONENTS if c in df.columns]
    df = df.dropna(subset=component_cols, how="all")

    return df.sort_index()


# ── Chart building ────────────────────────────────────────────────────────────

COLOURS = {
    "Energy":          "#CC0001",
    "Food & alc/tab":  "#F5A623",
    "NEIG":            "#6EC6F0",
    "Services":        "#003399",
    "Core (ex. E&F)": "#6B7280",
    "All items":       "#1A1A2E",
}


def _build_charts(df: pd.DataFrame) -> list:
    """Return list of two go.Figure objects."""
    # Core is shown as overlay only — exclude from stack
    comp_cols = [c for c in ["Services", "NEIG", "Food & alc/tab", "Energy"] if c in df.columns]

    # ── Figure 1: Stacked area of YoY components over time ───────────────────
    fig1 = go.Figure()

    for col in comp_cols:
        fig1.add_trace(go.Scatter(
            x=df.index, y=df[col],
            name=col,
            mode="lines",
            stackgroup="components",
            fillcolor=_hex_rgba(COLOURS.get(col, "#aaaaaa"), 0.45),
            line=dict(color=COLOURS.get(col, "#aaa"), width=1.5),
        ))

    # Overlay headline as a bold line
    fig1.add_trace(go.Scatter(
        x=df.index, y=df["All items"],
        name="Headline HICP",
        mode="lines",
        line=dict(color=COLOURS["All items"], width=2.5, dash="dot"),
    ))

    # Overlay Core (ex. energy & food) as a dashed grey line
    if "Core (ex. E&F)" in df.columns:
        fig1.add_trace(go.Scatter(
            x=df.index, y=df["Core (ex. E&F)"],
            name="Core HICP (ex. E&F)",
            mode="lines",
            line=dict(color="#6B7280", width=1.8, dash="dash"),
        ))

    fig1.add_hline(y=2, line_dash="dash", line_color="#003399", line_width=1,
                   annotation_text="ECB target 2%",
                   annotation_position="bottom right",
                   annotation_font=dict(size=10, color="#003399"))
    fig1.add_hline(y=0, line_dash="dot", line_color="grey", line_width=0.8)

    fig1.update_layout(
        title="HICP Components — YoY % (Eurozone, stacked)",
        xaxis=dict(title="", tickformat="%b %Y", showgrid=True, gridcolor="#e8eaf0"),
        yaxis=dict(title="YoY % change", showgrid=True, gridcolor="#e8eaf0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=460,
        margin=dict(t=55, b=30),
    )

    # ── Figure 2: Latest-month horizontal bar ─────────────────────────────────
    latest = df.iloc[-1]
    latest_date = df.index[-1]
    bar_cols = [c for c in ["Services", "NEIG", "Food & alc/tab", "Energy", "Core (ex. E&F)"] if c in latest.index]
    bar_vals = [round(latest[c], 2) for c in bar_cols]
    bar_colours = [COLOURS.get(c, "#aaa") for c in bar_cols]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        y=bar_cols,
        x=bar_vals,
        orientation="h",
        marker_color=bar_colours,
        text=[f"{v:+.2f}%" for v in bar_vals],
        textposition="outside",
        name="Component YoY",
    ))

    # Vertical line for headline
    if "All items" in latest.index:
        fig2.add_vline(
            x=latest["All items"],
            line_dash="dot", line_color="#1A1A2E", line_width=2,
            annotation_text=f"Headline: {latest['All items']:.1f}%",
            annotation_position="top right",
            annotation_font=dict(size=11, color="#1A1A2E"),
        )

    fig2.update_layout(
        title=f"HICP Component Breakdown — {latest_date.strftime('%B %Y')}",
        xaxis=dict(title="YoY % change", showgrid=True, gridcolor="#e8eaf0",
                   zeroline=True, zerolinecolor="#ccc"),
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=320, margin=dict(t=55, b=30, l=180),
        showlegend=False,
    )

    return [fig1, fig2]


# ── Table rows ────────────────────────────────────────────────────────────────

def _build_table(df: pd.DataFrame) -> list:
    """Build render-compatible table rows for latest + 1m-ago + 1y-ago."""
    latest_date = df.index[-1]
    one_m_ago   = latest_date - pd.DateOffset(months=1)
    one_y_ago   = latest_date - pd.DateOffset(years=1)

    def _get(col, dt):
        row = df[df.index == dt]
        return round(row[col].iloc[0], 2) if not row.empty and col in row.columns else None

    rows = [
        {
            "label":       "Date",
            "value":       latest_date.strftime("%B %Y"),
            "period":      "",
            "change":      None,
            "separator":   False,
        },
        {
            "label":       "─── Headline ───",
            "value":       "",
            "period":      "",
            "change":      None,
            "separator":   True,
        },
        {
            "label":       "All items (HICP)",
            "value":       f"{_get('All items', latest_date):+.1f}%" if _get('All items', latest_date) is not None else "n/a",
            "period":      latest_date.strftime("%b %Y"),
            "change":      round(_get("All items", latest_date) - _get("All items", one_y_ago), 2)
                           if _get("All items", latest_date) is not None and _get("All items", one_y_ago) is not None else None,
            "change_unit": " pp vs 1y ago",
            "bold":        True,
        },
        {
            "label":       "─── Components ───",
            "value":       "",
            "period":      "",
            "change":      None,
            "separator":   True,
        },
    ]

    comp_order = ["Services", "NEIG", "Food & alc/tab", "Energy", "Core (ex. E&F)"]
    for col in comp_order:
        if col not in df.columns:
            continue
        val_now  = _get(col, latest_date)
        val_1m   = _get(col, one_m_ago)
        val_1y   = _get(col, one_y_ago)
        note_parts = []
        w = APPROX_WEIGHTS.get(col)
        if w is not None:
            note_parts.append(f"weight ≈ {w*100:.0f}%")
        rows.append({
            "label":       col,
            "note":        " · ".join(note_parts) if note_parts else "",
            "value":       f"{val_now:+.1f}%" if val_now is not None else "n/a",
            "period":      latest_date.strftime("%b %Y"),
            "change":      round(val_now - val_1m, 2) if (val_now is not None and val_1m is not None) else None,
            "change_unit": " pp MoM",
        })

    return rows


# ── Key reads ─────────────────────────────────────────────────────────────────

def _build_key_reads(df: pd.DataFrame) -> list:
    latest = df.iloc[-1]
    latest_date = df.index[-1]
    prev = df.iloc[-13] if len(df) >= 13 else df.iloc[0]

    energy_now  = latest.get("Energy", None)
    services_now = latest.get("Services", None)
    neig_now    = latest.get("NEIG", None)
    food_now    = latest.get("Food & alc/tab", None)
    headline    = latest.get("All items", None)

    reads = []

    if services_now is not None and headline is not None:
        gap = services_now - headline
        reads.append({
            "icon": "🏦",
            "title": "Services vs Headline",
            "body": (
                f"Services inflation at <strong>{services_now:.1f}%</strong> is "
                f"<strong>{gap:+.1f} pp</strong> {'above' if gap > 0 else 'below'} headline. "
                "Persistent services inflation remains the ECB's primary concern."
            ),
            "tag": "Bearish" if services_now > 2.5 else "Neutral",
        })

    if energy_now is not None:
        reads.append({
            "icon": "⚡",
            "title": "Energy",
            "body": (
                f"Energy at <strong>{energy_now:.1f}%</strong> YoY. "
                f"{'Remains a drag on headline.' if energy_now < 0 else 'Adding to headline pressure.'}"
            ),
            "tag": "Bullish" if energy_now < 0 else "Bearish",
        })

    if neig_now is not None:
        reads.append({
            "icon": "🛒",
            "title": "Non-Energy Industrial Goods",
            "body": (
                f"NEIG at <strong>{neig_now:.1f}%</strong>. "
                f"{'Goods disinflation continuing.' if neig_now < 2 else 'Goods prices remain elevated.'}"
            ),
            "tag": "Bullish" if neig_now < 2 else "Neutral",
        })

    if food_now is not None:
        reads.append({
            "icon": "🌾",
            "title": "Food & Tobacco",
            "body": f"Food (incl. alc. & tab.) at <strong>{food_now:.1f}%</strong> YoY.",
            "tag": "Bearish" if food_now > 3 else "Neutral",
        })

    return reads


# ── Main entry point ──────────────────────────────────────────────────────────

def run(params: dict = None):
    """
    Fetch and render the Eurozone HICP component breakdown.
    Callable standalone or via router dispatch.
    """
    params    = params or {}
    years     = int(params.get("years", 5))
    geo       = params.get("geography", "EA")
    query     = params.get("_query", "Breakdown of Eurozone inflation components")
    intent    = params.get("_intent", "MACRO_INDICATOR")
    reasoning = params.get("_reasoning", [])

    print("\n" + "="*60)
    print("  📊 EUROZONE HICP — COMPONENT BREAKDOWN")
    print("="*60)

    df = _fetch_all(years=years, geo=geo)

    latest_date  = df.index[-1]
    headline_val = df["All items"].iloc[-1]
    vintage_str  = latest_date.strftime("%B %Y")

    print(f"\n  Headline HICP (All items): {headline_val:.1f}%  [{vintage_str}]")
    for col in ["Services", "NEIG", "Food & alc/tab", "Energy", "Core (ex. E&F)"]:
        if col in df.columns:
            print(f"  {col:<28} {df[col].iloc[-1]:+.1f}%")
    print("="*60)

    # ── Reasoning steps ──────────────────────────────────────────────────────
    if not reasoning:
        reasoning = [
            {"step": "Query received",
             "detail": f'<strong>"{query}"</strong>'},
            {"step": "Intent classified",
             "detail": "<strong>MACRO_INDICATOR / HICP Breakdown</strong> — keyword: <em>breakdown, components, inflation</em>"},
            {"step": "Parameters extracted",
             "detail": f"Geography: <strong>{geo}</strong> &nbsp;|&nbsp; Time horizon: <strong>{years}y</strong>"},
            {"step": "Data source",
             "detail": "Eurostat <code>prc_hicp_manr</code> — COICOP codes: NRG, IGX_E, SERV + Food residual"},
        ]

    reasoning.append({
        "step": "Output",
        "detail": (
            f"Headline: <strong>{headline_val:.1f}%</strong> ({vintage_str}) — "
            f"Services: <strong>{df['Services'].iloc[-1]:.1f}%</strong> | "
            f"NEIG: <strong>{df['NEIG'].iloc[-1]:.1f}%</strong> | "
            f"Food: <strong>{df['Food & alc/tab'].iloc[-1]:.1f}%</strong> | "
            f"Energy: <strong>{df['Energy'].iloc[-1]:.1f}%</strong> | "
            f"Core: <strong>{df['Core (ex. E&F)'].iloc[-1]:.1f}%</strong>"
            if all(c in df.columns for c in ["Services", "NEIG", "Energy", "Food & alc/tab", "Core (ex. E&F)"]) else
            f"Headline: <strong>{headline_val:.1f}%</strong> ({vintage_str})"
        ),
    })

    figs       = _build_charts(df)
    table_rows = _build_table(df)
    key_reads  = _build_key_reads(df)

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.html")
    saved = build_report(
        query=query,
        intent=intent,
        reasoning=reasoning,
        table_rows=table_rows,
        fig=figs,
        meta={
            "source":    "Eurostat — prc_hicp_manr",
            "vintage":   vintage_str,
            "series_id": "CP00 / NRG / IGX_E / SERV / FOOD (residual)",
            "endpoint":  "ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr",
        },
        out_path=out_path,
        key_reads=key_reads,
        chart_titles=[
            "📈 HICP Components — YoY % over time (stacked)",
            "📊 Component Breakdown — Latest month",
        ],
    )

    print(f"\n📊 Report saved → {saved}")
    import webbrowser
    webbrowser.open(f"file:///{saved.replace(os.sep, '/')}")

    print(f"\n✅ Source: Eurostat (prc_hicp_manr)")
    print(f"📅 Vintage: {vintage_str}")
    print(f"📊 Chart: output.html (opened automatically)")

    return {"headline": headline_val, "vintage": vintage_str}


if __name__ == "__main__":
    run()

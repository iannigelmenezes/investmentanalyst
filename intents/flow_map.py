"""
intents/flow_map.py
Handler for FLOW_MAP intent — Global Oil Supply & Demand Sankey.

Data source: EIA International Energy Data (free API)
  - Supply nodes:  top producer countries → "Global Supply Pool"
  - Demand nodes:  "Global Supply Pool" → top consumer countries

Charts:
  1. Sankey diagram: producers → supply pool → consumers
  2. Bar chart: top 10 producers vs consumers side-by-side

Output: output.html via render.py
"""

import os
import sys
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from providers.eia import fetch_regional_production, fetch_regional_consumption, fetch_oil_supply_demand_world
from render import build_report


# ── Colour palette ────────────────────────────────────────────────────────────

_SUPPLY_COLOURS = [
    "#003399", "#1a56c4", "#3373e0", "#4d8ff5",
    "#0055aa", "#2277cc", "#1166bb", "#0044bb",
    "#0033aa", "#224499", "#336688", "#558899",
    "#226677", "#114455", "#003344", "#002233",
    "#001122", "#000011",
]

_DEMAND_COLOURS = [
    "#CC0001", "#e02020", "#f04040", "#ff6060",
    "#dd1111", "#cc2222", "#bb3333", "#aa4444",
    "#993333", "#882222", "#771111", "#660000",
    "#993300", "#882200", "#771100", "#660000",
    "#550000", "#440000", "#330000", "#220000",
]

_POOL_COLOUR = "#F5A623"   # amber — the central "supply pool" node


def _hex_to_rgba(hex_col: str, alpha: float = 0.5) -> str:
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Grouping helpers ──────────────────────────────────────────────────────────

_REGION_GROUP = {
    # OPEC Middle East
    "SAU": "OPEC Middle East", "IRQ": "OPEC Middle East", "ARE": "OPEC Middle East",
    "KWT": "OPEC Middle East", "IRN": "OPEC Middle East",
    # OPEC Africa / Others
    "NGA": "OPEC Africa/Others", "LBY": "OPEC Africa/Others",
    "VEN": "OPEC Africa/Others", "DZA": "OPEC Africa/Others", "AGO": "OPEC Africa/Others",
    # Non-OPEC
    "USA": "United States", "RUS": "Russia", "CAN": "Canada",
    "NOR": "Norway", "BRA": "Brazil", "CHN": "China",
    "MEX": "Mexico", "KAZ": "Kazakhstan",
}

_CONSUMER_GROUP = {
    "USA": "United States", "CHN": "China", "IND": "India",
    "JPN": "Japan", "KOR": "South Korea", "DEU": "Germany",
    "BRA": "Brazil", "SAU": "Saudi Arabia", "RUS": "Russia",
    "CAN": "Canada", "GBR": "United Kingdom", "FRA": "France",
    "ITA": "Italy", "MEX": "Mexico", "IDN": "Indonesia",
    "SGP": "Singapore", "THA": "Thailand", "MYS": "Malaysia",
    "ARE": "UAE", "EGY": "Egypt",
}


def _aggregate(df: pd.DataFrame, group_map: dict) -> pd.DataFrame:
    """Map region_id → group label and sum values."""
    df = df.copy()
    df["group"] = df["region_id"].map(group_map).fillna(df["region"])
    return df.groupby("group")["value_kbd"].sum().reset_index().rename(
        columns={"group": "label", "value_kbd": "value_kbd"}
    ).sort_values("value_kbd", ascending=False)


# ── Chart builders ────────────────────────────────────────────────────────────

def _build_sankey(prod_df: pd.DataFrame, cons_df: pd.DataFrame, year: int) -> go.Figure:
    """
    Build a two-tier Sankey:
      Tier 1: Producer region → Global Supply Pool
      Tier 2: Global Supply Pool → Consumer region
    """
    # Only keep top-N to keep the chart readable
    prod_top = prod_df.head(12).copy()
    cons_top = cons_df.head(12).copy()

    # Scale to mb/d (from kb/d)
    prod_top["value_mbd"] = (prod_top["value_kbd"] / 1000).round(2)
    cons_top["value_mbd"] = (cons_top["value_kbd"] / 1000).round(2)

    # Node list: producers + pool + consumers
    pool_label = "Global Supply Pool"
    producer_labels = prod_top["label"].tolist()
    consumer_labels = cons_top["label"].tolist()

    all_nodes = producer_labels + [pool_label] + consumer_labels
    node_idx  = {label: i for i, label in enumerate(all_nodes)}
    pool_idx  = node_idx[pool_label]

    # Node colours
    node_colours = (
        [_hex_to_rgba(c, 0.85) for c in _SUPPLY_COLOURS[:len(producer_labels)]]
        + [_hex_to_rgba(_POOL_COLOUR, 0.9)]
        + [_hex_to_rgba(c, 0.85) for c in _DEMAND_COLOURS[:len(consumer_labels)]]
    )

    # Links: producer → pool
    sources, targets, values, link_colours = [], [], [], []
    for i, row in prod_top.iterrows():
        if row["value_mbd"] <= 0:
            continue
        sources.append(node_idx[row["label"]])
        targets.append(pool_idx)
        values.append(row["value_mbd"])
        link_colours.append(_hex_to_rgba(_SUPPLY_COLOURS[len(sources) - 1 % len(_SUPPLY_COLOURS)], 0.35))

    # Links: pool → consumer
    for i, row in cons_top.iterrows():
        if row["value_mbd"] <= 0:
            continue
        sources.append(pool_idx)
        targets.append(node_idx[row["label"]])
        values.append(row["value_mbd"])
        link_colours.append(_hex_to_rgba(_DEMAND_COLOURS[i % len(_DEMAND_COLOURS)], 0.35))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20,
            thickness=22,
            line=dict(color="white", width=0.5),
            label=all_nodes,
            color=node_colours,
            hovertemplate="%{label}<br>Flow: %{value:.2f} mb/d<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colours,
            hovertemplate="%{source.label} → %{target.label}<br>%{value:.2f} mb/d<extra></extra>",
        ),
    ))

    total_supply = prod_top["value_mbd"].sum()
    total_demand = cons_top["value_mbd"].sum()

    fig.update_layout(
        title=dict(
            text=(
                f"Global Oil Supply & Demand — {year}  "
                f"<span style='font-size:13px;color:#6B7280'>"
                f"Supply: {total_supply:.1f} mb/d shown &nbsp;|&nbsp; "
                f"Demand: {total_demand:.1f} mb/d shown</span>"
            ),
            font=dict(size=15),
        ),
        font=dict(size=11, family="Segoe UI, sans-serif"),
        paper_bgcolor="white",
        height=620,
        margin=dict(t=60, b=20, l=10, r=10),
    )
    return fig


def _build_bar(prod_df: pd.DataFrame, cons_df: pd.DataFrame, year: int) -> go.Figure:
    """Side-by-side horizontal bar: top 10 producers & consumers."""
    p10 = prod_df.head(10).copy()
    c10 = cons_df.head(10).copy()
    p10["value_mbd"] = (p10["value_kbd"] / 1000).round(2)
    c10["value_mbd"] = (c10["value_kbd"] / 1000).round(2)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Production",
        y=p10["label"],
        x=p10["value_mbd"],
        orientation="h",
        marker_color="#003399",
        text=[f"{v:.2f}" for v in p10["value_mbd"]],
        textposition="outside",
        xaxis="x1",
    ))

    fig.add_trace(go.Bar(
        name="Consumption",
        y=c10["label"],
        x=c10["value_mbd"],
        orientation="h",
        marker_color="#CC0001",
        text=[f"{v:.2f}" for v in c10["value_mbd"]],
        textposition="outside",
        xaxis="x2",
    ))

    fig.update_layout(
        title=dict(text=f"Top 10 Oil Producers vs Consumers — {year} (mb/d)", font=dict(size=14)),
        grid=dict(rows=1, columns=2),
        xaxis=dict(title="Production (mb/d)", domain=[0, 0.48], showgrid=True, gridcolor="#e8eaf0"),
        xaxis2=dict(title="Consumption (mb/d)", domain=[0.52, 1.0], showgrid=True, gridcolor="#e8eaf0"),
        yaxis=dict(autorange="reversed"),
        yaxis2=dict(autorange="reversed", anchor="x2"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=420,
        margin=dict(t=55, b=30, l=120, r=80),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        barmode="group",
    )
    return fig


# ── Table rows ────────────────────────────────────────────────────────────────

def _build_table(prod_df: pd.DataFrame, cons_df: pd.DataFrame, year: int) -> list:
    rows = [
        {"label": f"─── Top Producers ({year}) ───", "value": "", "period": "mb/d", "separator": True, "change": None},
    ]
    for _, r in prod_df.head(10).iterrows():
        rows.append({
            "label":  r["label"],
            "value":  f"{r['value_kbd']/1000:.2f} mb/d",
            "period": str(year),
            "change": None,
            "bold":   r["label"] in ("United States", "Russia", "Saudi Arabia"),
        })
    rows.append(
        {"label": f"─── Top Consumers ({year}) ───", "value": "", "period": "mb/d", "separator": True, "change": None}
    )
    for _, r in cons_df.head(10).iterrows():
        rows.append({
            "label":  r["label"],
            "value":  f"{r['value_kbd']/1000:.2f} mb/d",
            "period": str(year),
            "change": None,
            "bold":   r["label"] in ("United States", "China", "India"),
        })
    return rows


# ── Key reads ─────────────────────────────────────────────────────────────────

def _build_key_reads(prod_df: pd.DataFrame, cons_df: pd.DataFrame,
                     world_df: pd.DataFrame, year: int) -> list:
    # prod_df and cons_df here are the AGGREGATED frames (with 'label' column)
    top_prod  = prod_df.iloc[0] if not prod_df.empty else None
    top_cons  = cons_df.iloc[0] if not cons_df.empty else None

    total_supply = prod_df["value_kbd"].sum() / 1000
    total_demand = cons_df["value_kbd"].sum() / 1000

    # Supply/demand balance from world totals
    w_row = world_df[world_df["period"] == str(year)] if not world_df.empty else pd.DataFrame()
    world_supply = float(w_row["supply"].iloc[0]) / 1000 if not w_row.empty else total_supply
    world_demand = float(w_row["demand"].iloc[0]) / 1000 if not w_row.empty else total_demand
    balance      = round(world_supply - world_demand, 2)

    reads = []

    if top_prod is not None:
        share = top_prod["value_kbd"] / prod_df["value_kbd"].sum() * 100
        reads.append({
            "icon":  "🛢️",
            "title": "Largest Producer",
            "body":  (
                f"<strong>{top_prod['label']}</strong> leads global supply at "
                f"<strong>{top_prod['value_kbd']/1000:.2f} mb/d</strong> "
                f"({share:.0f}% of shown supply)."
            ),
            "tag": "Neutral",
        })

    if top_cons is not None:
        share = top_cons["value_kbd"] / cons_df["value_kbd"].sum() * 100
        reads.append({
            "icon":  "⛽",
            "title": "Largest Consumer",
            "body":  (
                f"<strong>{top_cons['label']}</strong> leads global demand at "
                f"<strong>{top_cons['value_kbd']/1000:.2f} mb/d</strong> "
                f"({share:.0f}% of shown demand)."
            ),
            "tag": "Neutral",
        })

    reads.append({
        "icon":  "⚖️",
        "title": "Supply/Demand Balance",
        "body":  (
            f"World supply: <strong>{world_supply:.1f} mb/d</strong> &nbsp;|&nbsp; "
            f"World demand: <strong>{world_demand:.1f} mb/d</strong><br>"
            f"Balance: <strong>{balance:+.2f} mb/d</strong> "
            f"({'surplus' if balance > 0 else 'deficit'})."
        ),
        "tag": "Bullish" if balance > 0.5 else "Bearish" if balance < -0.5 else "Neutral",
    })

    # OPEC share — computed from the aggregated label names
    opec_labels = {"OPEC Middle East", "OPEC Africa/Others"}
    opec_prod = prod_df[prod_df["label"].isin(opec_labels)]["value_kbd"].sum() if "label" in prod_df.columns else 0
    if opec_prod > 0 and prod_df["value_kbd"].sum() > 0:
        opec_share = opec_prod / prod_df["value_kbd"].sum() * 100
        reads.append({
            "icon":  "🌍",
            "title": "OPEC Concentration",
            "body":  (
                f"OPEC member countries account for approximately "
                f"<strong>{opec_share:.0f}%</strong> of shown global supply."
            ),
            "tag": "Risk" if opec_share > 40 else "Neutral",
        })

    return reads


# ── Main entry point ──────────────────────────────────────────────────────────

def run(params: dict = None):
    params    = params or {}
    year      = int(params.get("year", 2023))
    query     = params.get("_query", "Global oil supply and demand Sankey")
    intent    = params.get("_intent", "FLOW_MAP")
    reasoning = params.get("_reasoning", [])

    print("\n" + "=" * 65)
    print("  🛢️  GLOBAL OIL SUPPLY & DEMAND — SANKEY DIAGRAM")
    print("=" * 65)
    print(f"  Data source: EIA International Energy Data | Year: {year}")
    print("=" * 65)

    print(f"\n⏳ Fetching oil production by country ({year})…")
    prod_raw = fetch_regional_production(year=year)

    print(f"⏳ Fetching oil consumption by country ({year})…")
    cons_raw = fetch_regional_consumption(year=year)

    print("⏳ Fetching world supply/demand totals…")
    world_df = fetch_oil_supply_demand_world(start_year=year, end_year=year)

    # Aggregate to named groups for cleaner Sankey
    prod_df = _aggregate(prod_raw, _REGION_GROUP).sort_values("value_kbd", ascending=False).reset_index(drop=True)
    cons_df = _aggregate(cons_raw, _CONSUMER_GROUP).sort_values("value_kbd", ascending=False).reset_index(drop=True)

    # Console summary
    total_s = prod_df["value_kbd"].sum() / 1000
    total_d = cons_df["value_kbd"].sum() / 1000
    print(f"\n  {'Region':<30} {'Production (mb/d)':>18}")
    print(f"  {'-'*50}")
    for _, r in prod_df.head(10).iterrows():
        print(f"  {r['label']:<30} {r['value_kbd']/1000:>18.2f}")
    print(f"\n  {'Region':<30} {'Consumption (mb/d)':>18}")
    print(f"  {'-'*50}")
    for _, r in cons_df.head(10).iterrows():
        print(f"  {r['label']:<30} {r['value_kbd']/1000:>18.2f}")
    print(f"\n  Shown supply total: {total_s:.1f} mb/d")
    print(f"  Shown demand total: {total_d:.1f} mb/d")
    print("=" * 65)

    # ── Reasoning ──────────────────────────────────────────────────────────
    if not reasoning:
        reasoning = [
            {"step": "Query received",
             "detail": f'<strong>"{query}"</strong>'},
            {"step": "Intent classified",
             "detail": "<strong>FLOW_MAP</strong> — keyword: <em>sankey, oil, supply, demand</em>"},
            {"step": "Parameters extracted",
             "detail": f"Year: <strong>{year}</strong> &nbsp;|&nbsp; Commodity: <strong>Petroleum & other liquids</strong>"},
            {"step": "Data source selected",
             "detail": "EIA International Energy Data API v2 — <code>/v2/international/data</code>"},
            {"step": "Comparators selected",
             "detail": "Top 12 producers → Global Supply Pool → Top 12 consumers"},
        ]

    reasoning.append({
        "step": "Output",
        "detail": (
            f"Year: <strong>{year}</strong> &nbsp;|&nbsp; "
            f"Supply shown: <strong>{total_s:.1f} mb/d</strong> &nbsp;|&nbsp; "
            f"Demand shown: <strong>{total_d:.1f} mb/d</strong>"
        ),
    })

    # ── Build charts ────────────────────────────────────────────────────────
    fig_sankey = _build_sankey(prod_df, cons_df, year)
    fig_bar    = _build_bar(prod_df, cons_df, year)

    table_rows = _build_table(prod_df, cons_df, year)
    key_reads  = _build_key_reads(prod_df, cons_df, world_df, year)

    tweak_hint = (
        "💡 <strong>Want to tweak?</strong> &nbsp;"
        "Change reference year by adding e.g. <em>\"2022\"</em> to your query &nbsp;|&nbsp; "
        "Add more countries in <code>providers/eia.py</code> → "
        "<code>fetch_regional_production</code> / <code>fetch_regional_consumption</code> &nbsp;|&nbsp; "
        "Adjust top-N nodes in <code>intents/flow_map.py</code> → <code>prod_df.head(N)</code>"
    )

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.html")
    saved = build_report(
        query=query,
        intent=intent,
        reasoning=reasoning,
        table_rows=table_rows,
        fig=[fig_sankey, fig_bar],
        meta={
            "source":    "U.S. Energy Information Administration (EIA) — International Energy Data",
            "vintage":   str(year),
            "series_id": "Product 57 (Petroleum & other liquids) · Activity 1 (Production) · Activity 2 (Consumption)",
            "endpoint":  "api.eia.gov/v2/international/data",
        },
        out_path=out_path,
        key_reads=key_reads,
        tweak_hint=tweak_hint,
        chart_titles=[
            f"🌊 Chart 1 — Global Oil Flow Sankey: Producers → Supply Pool → Consumers ({year})",
            f"📊 Chart 2 — Top 10 Producers vs Consumers ({year})",
        ],
    )

    print(f"\n📊 Report saved → {saved}")
    import webbrowser
    webbrowser.open(f"file:///{saved.replace(os.sep, '/')}")

    print(f"\n✅ Source: EIA International Energy Data")
    print(f"📅 Vintage: {year}")
    print(f"📊 Chart: output.html (opened automatically)")

    return {"year": year, "supply_mbd": round(total_s, 2), "demand_mbd": round(total_d, 2)}


if __name__ == "__main__":
    run()

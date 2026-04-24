"""
intents/lng_flow.py
Handler for LNG_FLOW intent — Global LNG Trade Flow Sankey.

Data source: GIIGNL Annual LNG Report 2024 / IEA Gas Market Report 2024
             (EIA international/data has significant coverage gaps for LNG;
              bilateral trade pairs are not available via EIA v2 API)

Charts:
  1. Sankey diagram:  LNG exporters → Global LNG Pool → import regions/countries
  2. Horizontal bar:  Top exporters vs top importers side-by-side (MTPA)

Output: output.html via render.py
"""

import os
import sys
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from providers.eia import fetch_lng_trade
from render import build_report


# ── Colour palette ────────────────────────────────────────────────────────────

_EXPORTER_COLOURS = [
    "#003399", "#1a56c4", "#2e6fd9", "#4285f0",
    "#0044bb", "#1155cc", "#2266dd", "#3377ee",
    "#0055aa", "#1166bb", "#2277cc", "#3388dd",
    "#004499", "#1155aa", "#2266bb",
]

_IMPORTER_COLOURS = [
    "#CC0001", "#d91a1a", "#e63333", "#f04d4d",
    "#bb1111", "#cc2222", "#dd3333", "#ee4444",
    "#aa0000", "#bb1111", "#cc2222", "#dd3333",
    "#990000", "#aa1111", "#bb2222",
]

_POOL_COLOUR = "#F5A623"   # amber — Global LNG Pool node


def _hex_to_rgba(hex_col: str, alpha: float = 0.5) -> str:
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Aggregation helpers ───────────────────────────────────────────────────────

def _agg_exporters(df: pd.DataFrame) -> pd.DataFrame:
    """Sum MTPA by exporter, sorted descending."""
    return (
        df.groupby("exporter")["mtpa"]
          .sum()
          .reset_index()
          .rename(columns={"exporter": "label", "mtpa": "mtpa"})
          .sort_values("mtpa", ascending=False)
          .reset_index(drop=True)
    )


def _agg_importers(df: pd.DataFrame) -> pd.DataFrame:
    """Sum MTPA by importer, sorted descending."""
    return (
        df.groupby("importer")["mtpa"]
          .sum()
          .reset_index()
          .rename(columns={"importer": "label", "mtpa": "mtpa"})
          .sort_values("mtpa", ascending=False)
          .reset_index(drop=True)
    )


# ── Chart 1: Sankey ───────────────────────────────────────────────────────────

def _build_sankey(df: pd.DataFrame, year: int) -> go.Figure:
    """
    Two-tier Sankey:
      Tier 1: Exporter country → Global LNG Pool
      Tier 2: Global LNG Pool  → Importer region/country
    """
    exp_df = _agg_exporters(df)
    imp_df = _agg_importers(df)

    # Keep top-N for readability
    exp_top = exp_df.head(14).copy()
    imp_top = imp_df.head(14).copy()

    pool_label   = "Global LNG Pool"
    exp_labels   = exp_top["label"].tolist()
    imp_labels   = imp_top["label"].tolist()
    all_nodes    = exp_labels + [pool_label] + imp_labels
    node_idx     = {label: i for i, label in enumerate(all_nodes)}
    pool_idx     = node_idx[pool_label]

    # Node colours
    node_colours = (
        [_hex_to_rgba(c, 0.85) for c in _EXPORTER_COLOURS[:len(exp_labels)]]
        + [_hex_to_rgba(_POOL_COLOUR, 0.9)]
        + [_hex_to_rgba(c, 0.85) for c in _IMPORTER_COLOURS[:len(imp_labels)]]
    )

    sources, targets, values, link_colours = [], [], [], []

    # Exporter → Pool
    for i, row in exp_top.iterrows():
        if row["mtpa"] <= 0:
            continue
        sources.append(node_idx[row["label"]])
        targets.append(pool_idx)
        values.append(round(row["mtpa"], 1))
        link_colours.append(_hex_to_rgba(_EXPORTER_COLOURS[i % len(_EXPORTER_COLOURS)], 0.3))

    # Pool → Importer
    for i, row in imp_top.iterrows():
        if row["mtpa"] <= 0:
            continue
        sources.append(pool_idx)
        targets.append(node_idx[row["label"]])
        values.append(round(row["mtpa"], 1))
        link_colours.append(_hex_to_rgba(_IMPORTER_COLOURS[i % len(_IMPORTER_COLOURS)], 0.3))

    total_exp = exp_top["mtpa"].sum()
    total_imp = imp_top["mtpa"].sum()

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18,
            thickness=22,
            line=dict(color="white", width=0.5),
            label=all_nodes,
            color=node_colours,
            hovertemplate="%{label}<br>Volume: %{value:.1f} MTPA<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colours,
            hovertemplate="%{source.label} → %{target.label}<br>%{value:.1f} MTPA<extra></extra>",
        ),
    ))

    fig.update_layout(
        title=dict(
            text=(
                f"Global LNG Trade Flows — {year}  "
                f"<span style='font-size:13px;color:#6B7280'>"
                f"Exports shown: {total_exp:.0f} MTPA &nbsp;|&nbsp; "
                f"Imports shown: {total_imp:.0f} MTPA</span>"
            ),
            font=dict(size=15),
        ),
        font=dict(size=11, family="Segoe UI, sans-serif"),
        paper_bgcolor="white",
        height=640,
        margin=dict(t=65, b=20, l=10, r=10),
    )
    return fig


# ── Chart 2: Side-by-side bar ─────────────────────────────────────────────────

def _build_bar(df: pd.DataFrame, year: int) -> go.Figure:
    """Horizontal bar — top 12 exporters vs top 12 importers."""
    exp_df = _agg_exporters(df).head(12)
    imp_df = _agg_importers(df).head(12)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Exports",
        y=exp_df["label"],
        x=exp_df["mtpa"],
        orientation="h",
        marker_color="#003399",
        text=[f"{v:.1f}" for v in exp_df["mtpa"]],
        textposition="outside",
        xaxis="x1",
    ))

    fig.add_trace(go.Bar(
        name="Imports",
        y=imp_df["label"],
        x=imp_df["mtpa"],
        orientation="h",
        marker_color="#CC0001",
        text=[f"{v:.1f}" for v in imp_df["mtpa"]],
        textposition="outside",
        xaxis="x2",
    ))

    fig.update_layout(
        title=dict(
            text=f"Top LNG Exporters & Importers — {year} (MTPA)",
            font=dict(size=14),
        ),
        grid=dict(rows=1, columns=2),
        xaxis=dict(
            title="Exports (MTPA)", domain=[0, 0.48],
            showgrid=True, gridcolor="#e8eaf0",
        ),
        xaxis2=dict(
            title="Imports (MTPA)", domain=[0.52, 1.0],
            showgrid=True, gridcolor="#e8eaf0",
        ),
        yaxis=dict(autorange="reversed"),
        yaxis2=dict(autorange="reversed", anchor="x2"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=440,
        margin=dict(t=55, b=30, l=160, r=80),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    return fig


# ── Table rows ────────────────────────────────────────────────────────────────

def _build_table(df: pd.DataFrame, year: int) -> list:
    exp_df = _agg_exporters(df)
    imp_df = _agg_importers(df)

    rows = [
        {"label": f"─── Top LNG Exporters ({year}) ───",
         "value": "", "period": "MTPA", "separator": True, "change": None},
    ]
    for _, r in exp_df.head(12).iterrows():
        rows.append({
            "label":  r["label"],
            "value":  f"{r['mtpa']:.1f} MTPA",
            "period": str(year),
            "change": None,
            "bold":   r["label"] in ("United States", "Qatar", "Australia"),
        })

    rows.append(
        {"label": f"─── Top LNG Importers ({year}) ───",
         "value": "", "period": "MTPA", "separator": True, "change": None}
    )
    for _, r in imp_df.head(12).iterrows():
        rows.append({
            "label":  r["label"],
            "value":  f"{r['mtpa']:.1f} MTPA",
            "period": str(year),
            "change": None,
            "bold":   r["label"] in ("Europe", "Japan", "China"),
        })
    return rows


# ── Key reads ─────────────────────────────────────────────────────────────────

def _build_key_reads(df: pd.DataFrame, year: int) -> list:
    exp_df = _agg_exporters(df)
    imp_df = _agg_importers(df)

    total_exp = exp_df["mtpa"].sum()
    top_exp   = exp_df.iloc[0] if not exp_df.empty else None
    top_imp   = imp_df.iloc[0] if not imp_df.empty else None

    reads = []

    if top_exp is not None:
        share = top_exp["mtpa"] / total_exp * 100
        reads.append({
            "icon":  "🚢",
            "title": "Largest LNG Exporter",
            "body":  (
                f"<strong>{top_exp['label']}</strong> is the world's largest LNG exporter "
                f"at <strong>{top_exp['mtpa']:.0f} MTPA</strong> "
                f"({share:.0f}% of shown global exports)."
            ),
            "tag": "Neutral",
        })

    if top_imp is not None:
        share = top_imp["mtpa"] / imp_df["mtpa"].sum() * 100
        reads.append({
            "icon":  "⛽",
            "title": "Largest LNG Import Region",
            "body":  (
                f"<strong>{top_imp['label']}</strong> is the world's largest LNG import region "
                f"at <strong>{top_imp['mtpa']:.0f} MTPA</strong> "
                f"({share:.0f}% of shown imports)."
            ),
            "tag": "Neutral",
        })

    # US dominance
    us_row = exp_df[exp_df["label"] == "United States"]
    if not us_row.empty:
        us_share = us_row["mtpa"].iloc[0] / total_exp * 100
        reads.append({
            "icon":  "🇺🇸",
            "title": "US LNG Surge",
            "body":  (
                f"The United States now accounts for <strong>{us_share:.0f}%</strong> of "
                f"global LNG exports, driven by Sabine Pass, Corpus Christi, Calcasieu Pass, "
                f"and Freeport. The US overtook Qatar and Australia as the largest LNG exporter."
            ),
            "tag": "Bullish",
        })

    # Asia concentration
    asia_importers = {"Japan", "China", "South Korea", "Taiwan", "India",
                      "Other Asia", "Asia", "Singapore", "Pakistan"}
    asia_mtpa = imp_df[imp_df["label"].isin(asia_importers)]["mtpa"].sum()
    asia_share = asia_mtpa / imp_df["mtpa"].sum() * 100 if imp_df["mtpa"].sum() > 0 else 0
    reads.append({
        "icon":  "🌏",
        "title": "Asia Dominates LNG Demand",
        "body":  (
            f"Asia-Pacific importers absorb approximately "
            f"<strong>{asia_share:.0f}%</strong> of global LNG trade, "
            f"led by Japan, China, South Korea, and India — underpinning "
            f"long-haul LNG shipping rates and destination flexibility premiums."
        ),
        "tag": "Risk" if asia_share > 65 else "Neutral",
    })

    reads.append({
        "icon":  "📊",
        "title": "Data Source",
        "body":  (
            "Figures sourced from <strong>GIIGNL Annual LNG Report 2024</strong>, "
            "<strong>IEA Gas Market Report 2024</strong>, and "
            "<strong>Shell LNG Outlook 2024</strong>. "
            "EIA International API (product 26) has coverage gaps for bilateral LNG flows."
        ),
        "tag": "Neutral",
    })

    return reads


# ── Main entry point ──────────────────────────────────────────────────────────

def run(params: dict = None):
    params    = params or {}
    year      = int(params.get("year", 2023))
    query     = params.get("_query", "Global LNG trade flows Sankey")
    intent    = params.get("_intent", "LNG_FLOW")
    reasoning = params.get("_reasoning", [])

    print("\n" + "=" * 65)
    print("  🚢  GLOBAL LNG TRADE FLOWS — SANKEY DIAGRAM")
    print("=" * 65)
    print(f"  Data source: GIIGNL 2024 / IEA Gas Market Report 2024 | Year: {year}")
    print("=" * 65)

    print(f"\n⏳ Loading LNG trade flow data ({year})…")
    df = fetch_lng_trade(year=year)

    exp_df = _agg_exporters(df)
    imp_df = _agg_importers(df)

    total_exp = exp_df["mtpa"].sum()
    total_imp = imp_df["mtpa"].sum()

    # Console summary
    print(f"\n  {'Exporter':<30} {'MTPA':>10}")
    print(f"  {'-'*42}")
    for _, r in exp_df.head(12).iterrows():
        print(f"  {r['label']:<30} {r['mtpa']:>10.1f}")

    print(f"\n  {'Importer':<30} {'MTPA':>10}")
    print(f"  {'-'*42}")
    for _, r in imp_df.head(12).iterrows():
        print(f"  {r['label']:<30} {r['mtpa']:>10.1f}")

    print(f"\n  Total exports shown : {total_exp:.1f} MTPA")
    print(f"  Total imports shown : {total_imp:.1f} MTPA")
    print("=" * 65)

    # ── Reasoning chain ─────────────────────────────────────────────────────
    if not reasoning:
        reasoning = [
            {"step": "Query received",
             "detail": f'<strong>"{query}"</strong>'},
            {"step": "Intent classified",
             "detail": "<strong>LNG_FLOW</strong> — keyword: <em>lng, lng flows, gas flows</em>"},
            {"step": "Parameters extracted",
             "detail": f"Year: <strong>{year}</strong> &nbsp;|&nbsp; Commodity: <strong>Liquefied Natural Gas</strong>"},
            {"step": "Data source selected",
             "detail": (
                 "GIIGNL Annual LNG Report 2024 &nbsp;|&nbsp; "
                 "IEA Gas Market Report 2024 &nbsp;|&nbsp; "
                 "Shell LNG Outlook 2024 "
                 "<em>(EIA API lacks bilateral LNG trade coverage)</em>"
             )},
            {"step": "Comparators selected",
             "detail": "Top 14 exporters → Global LNG Pool → Top 14 import regions"},
        ]

    reasoning.append({
        "step": "Output",
        "detail": (
            f"Year: <strong>{year}</strong> &nbsp;|&nbsp; "
            f"Exports shown: <strong>{total_exp:.0f} MTPA</strong> &nbsp;|&nbsp; "
            f"Imports shown: <strong>{total_imp:.0f} MTPA</strong>"
        ),
    })

    # ── Build charts ─────────────────────────────────────────────────────────
    fig_sankey = _build_sankey(df, year)
    fig_bar    = _build_bar(df, year)
    table_rows = _build_table(df, year)
    key_reads  = _build_key_reads(df, year)

    tweak_hint = (
        "💡 <strong>Want to tweak?</strong> &nbsp;"
        "LNG flow volumes are from <strong>GIIGNL 2024 / IEA Gas Market Report 2024</strong>. "
        "Update bilateral flows directly in <code>providers/eia.py</code> → "
        "<code>fetch_lng_trade()</code> &nbsp;|&nbsp; "
        "Add more nodes by editing <code>intents/lng_flow.py</code> → "
        "<code>exp_top = exp_df.head(N)</code>"
    )

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.html")
    saved = build_report(
        query=query,
        intent=intent,
        reasoning=reasoning,
        table_rows=table_rows,
        fig=[fig_sankey, fig_bar],
        meta={
            "source":    "GIIGNL Annual LNG Report 2024 · IEA Gas Market Report 2024 · Shell LNG Outlook 2024",
            "vintage":   str(year),
            "series_id": "Bilateral LNG trade flows (MTPA) — exporter × importer",
            "endpoint":  "Curated dataset (EIA API bilateral LNG gaps; see providers/eia.py)",
        },
        out_path=out_path,
        key_reads=key_reads,
        tweak_hint=tweak_hint,
        chart_titles=[
            f"🌊 Chart 1 — Global LNG Trade Flow Sankey: Exporters → LNG Pool → Importers ({year})",
            f"📊 Chart 2 — Top LNG Exporters & Importers ({year})",
        ],
    )

    print(f"\n📊 Report saved → {saved}")
    import webbrowser
    webbrowser.open(f"file:///{saved.replace(os.sep, '/')}")

    print(f"\n✅ Source: GIIGNL Annual LNG Report 2024 / IEA Gas Market Report 2024")
    print(f"📅 Vintage: {year}")
    print(f"📊 Chart: output.html (opened automatically)")

    return {
        "year":       year,
        "exports_mtpa": round(total_exp, 1),
        "imports_mtpa": round(total_imp, 1),
    }


if __name__ == "__main__":
    run()

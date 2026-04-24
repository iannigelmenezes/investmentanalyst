"""
intents/rates_curve.py
Handler for RATES_CURVE intent.

Output (3 charts + key reads + table):
  Chart 1: Curve snapshot — current vs 1m ago vs 1y ago
  Chart 2: 10Y yield time series (10y history), with dropdown to flip tenor
  Chart 3: Current curve vs France (OAT) vs Italy (BTP) cross-country comparison
  Key reads: auto-generated analyst bullets
  Table: Tenor | Current | 1m ago | 1y ago | Δ1m | Δ1y
"""

import sys
import os
import urllib3
import pandas as pd
import plotly.graph_objects as go
import webbrowser
from datetime import date, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from providers.ecb_sdw import fetch_yield_curve_snapshot, fetch_yield_timeseries, TENOR_MAP
from render import build_report

# Ordered list of tenors
TENORS = ["SR_3M", "SR_6M", "SR_1Y", "SR_2Y", "SR_3Y", "SR_5Y", "SR_7Y", "SR_10Y", "SR_20Y", "SR_30Y"]

# Country curve keys for chart 3
# ECB SDW AAA curve is for Euro Area aggregate (U2). Per-country sovereign curves
# use a different flow: IRS/B.<country>.EUR...  but the cleanest available per-country
# spot rates come from the ECB's country-specific yield curve dataset.
# Key pattern: YC/B.<geo>.EUR.4F.G_N_A.SV_C_YM.<tenor>
COUNTRY_CURVES = [
    {"label": "Euro Area AAA",  "geo": "U2", "color": "#003399"},
    {"label": "France (OAT)",   "geo": "FR", "color": "#CC0001"},
    {"label": "Italy (BTP)",    "geo": "IT", "color": "#FF6600"},
]


def _bd_ago(n: int) -> str:
    return (pd.Timestamp.today() - pd.DateOffset(days=n)).strftime("%Y-%m-%d")


def _fetch_country_curve(geo: str, tenors: list, as_of: str) -> dict:
    """Fetch one snapshot for a given country geo code."""
    import requests
    results = {}
    window_start = (pd.to_datetime(as_of) - pd.DateOffset(days=10)).strftime("%Y-%m-%d")
    for tenor in tenors:
        key = f"YC/B.{geo}.EUR.4F.G_N_A.SV_C_YM.{tenor}"
        url = f"https://data-api.ecb.europa.eu/service/data/{key}"
        try:
            r = requests.get(url, params={
                "format": "jsondata", "startPeriod": window_start, "endPeriod": as_of
            }, timeout=60, verify=False)
            if r.status_code != 200:
                results[tenor] = None
                continue
            d = r.json()
            series = d.get("dataSets", [{}])[0].get("series", {})
            if not series:
                results[tenor] = None
                continue
            obs   = list(series.values())[0].get("observations", {})
            times = d["structure"]["dimensions"]["observation"][0]["values"]
            vals  = [(pd.to_datetime(times[int(k)]["id"]), v[0]) for k, v in obs.items() if v[0] is not None]
            if vals:
                results[tenor] = round(sorted(vals)[-1][1], 4)
            else:
                results[tenor] = None
        except Exception:
            results[tenor] = None
    return results


def run(params: dict = None):
    params    = params or {}
    query     = params.get("_query", "German Bund curve")
    intent    = params.get("_intent", "RATES_CURVE")
    reasoning = params.get("_reasoning", [])
    years     = int(params.get("years", 10))

    today_str = date.today().isoformat()
    m1_str    = _bd_ago(35)
    y1_str    = _bd_ago(370)
    hist_start = (pd.Timestamp.today() - pd.DateOffset(years=years)).strftime("%Y-%m-%d")

    # ── Fetch curve snapshots ─────────────────────────────────────────────────
    print("\n⏳ Fetching ECB AAA curve — current…")
    snap_now = fetch_yield_curve_snapshot(TENORS, as_of_date=today_str)
    print("⏳ Fetching ECB AAA curve — 1 month ago…")
    snap_1m  = fetch_yield_curve_snapshot(TENORS, as_of_date=m1_str)
    print("⏳ Fetching ECB AAA curve — 1 year ago…")
    snap_1y  = fetch_yield_curve_snapshot(TENORS, as_of_date=y1_str)

    # ── Fetch 10y time series for all tenors (for chart 2 toggle) ────────────
    print(f"⏳ Fetching {years}y time series for all tenors (chart 2)…")
    ts_data = {}
    for tenor in TENORS:
        try:
            df = fetch_yield_timeseries(tenor, start_period=hist_start, end_period=today_str)
            if not df.empty:
                ts_data[tenor] = df
        except Exception as e:
            print(f"  [skip] {tenor}: {e}")

    # ── Fetch country curves for chart 3 ─────────────────────────────────────
    print("⏳ Fetching country curves — France & Italy (chart 3)…")
    country_snaps = {}
    for cc in COUNTRY_CURVES:
        geo = cc["geo"]
        print(f"  → {cc['label']} ({geo})…")
        country_snaps[geo] = _fetch_country_curve(geo, TENORS, today_str)

    # ── Build table rows ──────────────────────────────────────────────────────
    rows_data = []
    for t in TENORS:
        label, yrs = TENOR_MAP[t]
        cur = snap_now.get(t)
        m1  = snap_1m.get(t)
        y1  = snap_1y.get(t)
        d1m = round((cur - m1) * 100, 1) if (cur and m1) else None   # in bps
        d1y = round((cur - y1) * 100, 1) if (cur and y1) else None
        rows_data.append({"tenor": label, "code": t, "years": yrs,
                          "cur": cur, "m1": m1, "y1": y1, "d1m": d1m, "d1y": d1y})

    # ── Console print ─────────────────────────────────────────────────────────
    def _fmt_pct(v):  return f"{v:.3f}%" if v is not None else "n/a"
    def _fmt_bp(v):   return f"{v:+.1f}bp" if v is not None else "n/a"

    print(f"\n{'='*72}")
    print(f"  📊 EURO AREA AAA YIELD CURVE  —  {today_str}")
    print(f"{'='*72}")
    print(f"  {'Tenor':<6}  {'Current':>8}  {'1m ago':>8}  {'1y ago':>8}  {'Δ 1m':>8}  {'Δ 1y':>8}")
    print(f"  {'-'*66}")
    for r in rows_data:
        print(f"  {r['tenor']:<6}  "
              f"{_fmt_pct(r['cur']):>8}  "
              f"{_fmt_pct(r['m1']):>8}  "
              f"{_fmt_pct(r['y1']):>8}  "
              f"{_fmt_bp(r['d1m']):>8}  "
              f"{_fmt_bp(r['d1y']):>8}")
    print(f"{'='*72}")

    # ── Detect inversions ─────────────────────────────────────────────────────
    valid = [(r["years"], r["cur"]) for r in rows_data if r["cur"] is not None]
    inversions = []
    for i in range(1, len(valid)):
        if valid[i][1] < valid[i-1][1]:
            inversions.append((valid[i-1][0], valid[i][0]))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHART 1: Curve snapshot — current / 1m ago / 1y ago
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    fig1 = go.Figure()

    def _curve_trace(snap, name, color, dash, width, opacity=1.0):
        x = [TENOR_MAP[t][1] for t in TENORS if snap.get(t) is not None]
        y = [snap[t]          for t in TENORS if snap.get(t) is not None]
        return go.Scatter(x=x, y=y, mode="lines+markers", name=name,
                          line=dict(color=color, width=width, dash=dash),
                          marker=dict(size=6), opacity=opacity,
                          hovertemplate=f"%{{y:.3f}}%<extra>{name}</extra>")

    fig1.add_trace(_curve_trace(snap_1y,  f"1y ago ({y1_str[:7]})",  "#AAAAAA", "dot",  1.5, 0.7))
    fig1.add_trace(_curve_trace(snap_1m,  f"1m ago ({m1_str[:7]})",  "#F5A623", "dash", 2.0))
    fig1.add_trace(_curve_trace(snap_now, f"Current ({today_str})",  "#003399", "solid",2.8))

    for inv_s, inv_e in inversions:
        fig1.add_vrect(x0=inv_s, x1=inv_e, fillcolor="rgba(204,0,1,0.08)",
                       line_width=0, annotation_text="Inverted",
                       annotation_font=dict(size=9, color="#CC0001"))

    ten_y = snap_now.get("SR_10Y")
    if ten_y:
        fig1.add_annotation(x=10, y=ten_y, text=f"10Y: {ten_y:.2f}%",
                            showarrow=True, arrowhead=2, arrowcolor="#003399",
                            font=dict(size=11, color="#003399"),
                            bgcolor="rgba(255,255,255,0.85)", bordercolor="#003399",
                            ax=35, ay=-35)

    fig1.update_layout(
        title=dict(text=f"Euro Area AAA Yield Curve — {today_str}", font=dict(size=14)),
        xaxis=dict(title="Maturity (years)", tickvals=[r["years"] for r in rows_data],
                   ticktext=[r["tenor"] for r in rows_data], showgrid=True, gridcolor="#e8eaf0"),
        yaxis=dict(title="Yield (%)", showgrid=True, gridcolor="#e8eaf0"),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=440, margin=dict(t=50, b=30),
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHART 2: Time series with tenor toggle dropdown
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    fig2 = go.Figure()

    default_tenor = "SR_10Y"
    tenor_colors = {
        "SR_3M": "#AAAAAA", "SR_6M": "#888888", "SR_1Y": "#9B59B6",
        "SR_2Y": "#3498DB", "SR_3Y": "#2ECC71", "SR_5Y": "#F39C12",
        "SR_7Y": "#E67E22", "SR_10Y": "#003399", "SR_20Y": "#CC0001", "SR_30Y": "#922B21",
    }

    for t in TENORS:
        df_t = ts_data.get(t)
        if df_t is None or df_t.empty:
            continue
        label, _ = TENOR_MAP[t]
        visible = True if t == default_tenor else "legendonly"
        fig2.add_trace(go.Scatter(
            x=df_t["date"], y=df_t["value"],
            mode="lines", name=f"{label} yield",
            line=dict(color=tenor_colors.get(t, "#003399"), width=2),
            visible=visible,
            hovertemplate=f"%{{y:.3f}}%<extra>{label}</extra>",
        ))

    # Dropdown buttons — show one tenor at a time
    buttons = []
    for i, t in enumerate([t for t in TENORS if t in ts_data]):
        label, _ = TENOR_MAP[t]
        visibility = [t2 == t for t2 in [t3 for t3 in TENORS if t3 in ts_data]]
        buttons.append(dict(
            label=label,
            method="update",
            args=[
                {"visible": visibility},
                {"title": f"Euro Area AAA — {label} Yield ({years}y history)"},
            ],
        ))

    fig2.update_layout(
        title=dict(text=f"Euro Area AAA — 10Y Yield ({years}y history)", font=dict(size=14)),
        updatemenus=[dict(
            active=[t for t in TENORS if t in ts_data].index(default_tenor) if default_tenor in ts_data else 0,
            buttons=buttons,
            direction="down", showactive=True,
            x=0.0, xanchor="left", y=1.15, yanchor="top",
            bgcolor="white", bordercolor="#DDE1E9",
            font=dict(size=12),
        )],
        xaxis=dict(title="", tickformat="%b %Y", showgrid=True, gridcolor="#e8eaf0",
                   rangeslider=dict(visible=True, thickness=0.06)),
        yaxis=dict(title="Yield (%)", showgrid=True, gridcolor="#e8eaf0"),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=480, margin=dict(t=80, b=50),
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CHART 3: Cross-country curve comparison
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    fig3 = go.Figure()

    for cc in COUNTRY_CURVES:
        geo   = cc["geo"]
        snap  = country_snaps.get(geo, {})
        x = [TENOR_MAP[t][1] for t in TENORS if snap.get(t) is not None]
        y = [snap[t]          for t in TENORS if snap.get(t) is not None]
        if not x:
            continue
        fig3.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=cc["label"],
            line=dict(color=cc["color"], width=2.5),
            marker=dict(size=7),
            hovertemplate=f"%{{y:.3f}}%<extra>{cc['label']}</extra>",
        ))

    fig3.update_layout(
        title=dict(text=f"Sovereign Yield Curves — Euro Area vs France vs Italy ({today_str})",
                   font=dict(size=14)),
        xaxis=dict(title="Maturity (years)", tickvals=[r["years"] for r in rows_data],
                   ticktext=[r["tenor"] for r in rows_data], showgrid=True, gridcolor="#e8eaf0"),
        yaxis=dict(title="Yield (%)", showgrid=True, gridcolor="#e8eaf0"),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", yanchor="bottom"),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=440, margin=dict(t=50, b=30),
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # KEY READS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    r_3m  = snap_now.get("SR_3M")
    r_2y  = snap_now.get("SR_2Y")
    r_10y = snap_now.get("SR_10Y")
    r_30y = snap_now.get("SR_30Y")

    slope_2_10  = round((r_10y - r_2y) * 100,  1) if (r_10y and r_2y)  else None
    slope_3m_10 = round((r_10y - r_3m) * 100,  1) if (r_10y and r_3m)  else None
    slope_2_30  = round((r_30y - r_2y) * 100,  1) if (r_30y and r_2y)  else None

    d10_1m = rows_data[7]["d1m"] if len(rows_data) > 7 else None
    d10_1y = rows_data[7]["d1y"] if len(rows_data) > 7 else None

    # IT vs EZ 10Y spread
    it_10y = country_snaps.get("IT", {}).get("SR_10Y")
    fr_10y = country_snaps.get("FR", {}).get("SR_10Y")
    it_spread = round((it_10y - r_10y) * 100, 1) if (it_10y and r_10y) else None
    fr_spread = round((fr_10y - r_10y) * 100, 1) if (fr_10y and r_10y) else None

    inv_note = (
        f"Inversion detected at {', '.join(f'{s:.0f}–{e:.0f}Y' for s,e in inversions)}" 
        if inversions else "No inversion — curve is upward sloping"
    )
    inv_tag = "Risk" if inversions else "Neutral"

    key_reads = [
        {
            "icon": "📐",
            "title": "Curve shape",
            "body": (
                f"<strong>2s10s: {slope_2_10:+.0f}bp</strong> &nbsp;|&nbsp; "
                f"3m10s: {slope_3m_10:+.0f}bp &nbsp;|&nbsp; "
                f"2s30s: {slope_2_30:+.0f}bp<br>{inv_note}."
            ) if slope_2_10 is not None else "Insufficient data.",
            "tag": inv_tag,
        },
        {
            "icon": "📉",
            "title": "10Y direction (1m / 1y)",
            "body": (
                f"10Y yield is <strong>{r_10y:.3f}%</strong> today. "
                f"<strong>{f'{d10_1m:+.1f}bp' if d10_1m is not None else 'n/a'} over 1 month</strong>, "
                f"{f'{d10_1y:+.1f}bp' if d10_1y is not None else 'n/a'} over 1 year. "
                + ("Rates have been rising recently." if d10_1m and d10_1m > 5 else
                   "Rates have been falling recently." if d10_1m and d10_1m < -5 else
                   "10Y has been broadly stable over the last month.")
            ) if r_10y else "10Y data unavailable.",
            "tag": "Bearish" if (d10_1m and d10_1m > 10) else "Bullish" if (d10_1m and d10_1m < -10) else "Neutral",
        },
        {
            "icon": "🌍",
            "title": "Peripheral spreads vs EZ AAA",
            "body": (
                (f"Italy (BTP) 10Y vs EZ AAA: <strong>{it_spread:+.0f}bp</strong><br>" if it_spread is not None else "") +
                (f"France (OAT) 10Y vs EZ AAA: <strong>{fr_spread:+.0f}bp</strong><br>" if fr_spread is not None else "") +
                ("Peripheral data unavailable." if it_spread is None and fr_spread is None else "")
            ),
            "tag": "Risk" if (it_spread and it_spread > 150) else "Neutral",
        },
        {
            "icon": "⚙️",
            "title": "ECB policy read",
            "body": (
                f"Front-end (3M) at <strong>{r_3m:.2f}%</strong> — close to ECB deposit rate. "
                f"2Y at <strong>{r_2y:.2f}%</strong> implies "
                + ("further easing priced in." if r_2y and r_3m and r_2y < r_3m else
                   "no additional cuts priced at the 2Y point.")
            ) if (r_3m and r_2y) else "Front-end data unavailable.",
            "tag": "Bullish" if (r_2y and r_3m and r_2y < r_3m - 0.10) else "Neutral",
        },
    ]

    # ── Reasoning chain final step ────────────────────────────────────────────
    if reasoning:
        reasoning.append({
            "step": "Output",
            "detail": (
                f"10Y: <strong>{r_10y:.3f}%</strong> ({today_str}) | "
                f"2s10s: <strong>{slope_2_10:+.0f}bp</strong> | "
                f"IT spread: <strong>{it_spread:+.0f}bp</strong>"
                if (r_10y and slope_2_10 is not None and it_spread is not None)
                else f"10Y: <strong>{r_10y:.3f}%</strong> ({today_str})" if r_10y else "Data fetched."
            ),
        })

    # ── Render table rows ─────────────────────────────────────────────────────
    table_rows = []
    for r in rows_data:
        cur_s = f"{r['cur']:.3f}%" if r["cur"] is not None else "n/a"
        m1_s  = f"{r['m1']:.3f}%"  if r["m1"]  is not None else "n/a"
        y1_s  = f"{r['y1']:.3f}%"  if r["y1"]  is not None else "n/a"

        def _bp_html(val):
            if val is None: return ""
            col = "#CC0001" if val > 0 else "#003399"
            arr = "▲" if val > 0 else "▼"
            return f"<span style='color:{col};font-weight:600'>{arr} {abs(val):.1f}bp</span>"

        raw = f"Δ1m: {_bp_html(r['d1m'])} &nbsp; Δ1y: {_bp_html(r['d1y'])}"
        table_rows.append({
            "label":  r["tenor"],
            "value":  cur_s,
            "period": f"1m: {m1_s} &nbsp;|&nbsp; 1y: {y1_s}",
            "bold":   r["tenor"] == "10Y",
            "_raw_change": raw,
        })

    # ── Tweak hint ────────────────────────────────────────────────────────────
    tweak_hint = (
        "💡 <strong>Want to tweak?</strong> &nbsp;"
        "Change comparator countries in <code>config/output_config.yaml</code> → "
        "<code>rates_curve.comparator_countries</code> &nbsp;|&nbsp; "
        "Change history window by adding e.g. <em>\"last 5 years\"</em> to your query &nbsp;|&nbsp; "
        "Change default tenor shown in chart 2 via "
        "<code>rates_curve.timeseries_default_tenor</code>"
    )

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output.html")
    saved = build_report(
        query=query,
        intent=intent,
        reasoning=reasoning,
        table_rows=table_rows,
        fig=[fig1, fig2, fig3],
        meta={
            "source":    "ECB Statistical Data Warehouse (SDW)",
            "vintage":   today_str,
            "series_id": "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.*",
            "endpoint":  "data-api.ecb.europa.eu/service/data/YC/",
        },
        out_path=out_path,
        key_reads=key_reads,
        tweak_hint=tweak_hint,
        chart_titles=[
            "📈 Chart 1 — Yield Curve Snapshot: Current vs 1M ago vs 1Y ago",
            f"📈 Chart 2 — Yield Time Series ({years}Y history) — use dropdown to switch tenor",
            "📈 Chart 3 — Cross-Country Curve Comparison: Euro Area vs France vs Italy",
        ],
    )

    print(f"\n📊 Report saved → {saved}")
    import webbrowser
    webbrowser.open(f"file:///{saved.replace(os.sep, '/')}")
    print(f"\n✅ Source: ECB SDW")
    print(f"📅 Vintage: {today_str}")
    print(f"📊 Chart: output.html (opened automatically)")

    return {"curve": {r["tenor"]: r["cur"] for r in rows_data}}


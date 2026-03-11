"""
render.py
Generates a single-page HTML report combining:
  - Reasoning chain (query → intent → data sources → params)
  - Key analyst reads (bullet cards)
  - Summary table
  - One or more embedded interactive Plotly charts
  - Footer with source / vintage / series metadata
"""

import os
from datetime import datetime
import plotly.graph_objects as go


_PGGM_BLUE  = "#003399"
_PGGM_RED   = "#CC0001"
_ACCENT     = "#F5A623"
_LIGHT_GREY = "#F7F8FA"
_BORDER     = "#DDE1E9"
_TEXT       = "#1A1A2E"
_SUBTLE     = "#6B7280"


def _arrow(val, unit="pp", positive_good=False):
    """Return an HTML-coloured arrow + value string."""
    if val is None:
        return "<span style='color:#aaa'>n/a</span>"
    colour = (_PGGM_BLUE if val < 0 else _PGGM_RED) if not positive_good else \
             (_PGGM_BLUE if val > 0 else _PGGM_RED)
    arrow = "▲" if val > 0 else ("▼" if val < 0 else "—")
    return f"<span style='color:{colour};font-weight:600'>{arrow} {abs(val):+.2f}{unit}</span>"


def _embed_fig(fig: go.Figure) -> str:
    """Return a Plotly figure as an embeddable HTML div (no full-page wrapper)."""
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,   # loaded once in <head>
        config={
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "displaylogo": False,
        },
    )


def build_report(
    query: str,
    intent: str,
    reasoning: list,        # [{"step": str, "detail": str}, ...]
    table_rows: list,       # [{"label","value","period","change","change_unit","note","bold","separator"}, ...]
    fig,                    # go.Figure OR list of go.Figure
    meta: dict,             # {"source","vintage","series_id","endpoint"}
    out_path: str = None,
    key_reads: list = None, # [{"icon","title","body","tag"}, ...]
    tweak_hint: str = None, # override the default tweak hint HTML
    chart_titles: list = None,  # titles for each chart section
) -> str:
    """
    Build a rich HTML report and write it to out_path.
    Returns the absolute path of the saved file.
    fig can be a single go.Figure or a list of go.Figure objects.
    """
    if out_path is None:
        out_path = os.path.join(os.path.dirname(__file__), "output.html")

    figs = fig if isinstance(fig, list) else [fig]
    if chart_titles is None:
        chart_titles = [f"📈 Chart {i+1}" if len(figs) > 1 else "📈 Chart"
                        for i in range(len(figs))]

    # ── Reasoning chain ──────────────────────────────────────────────────────
    step_icons = ["🔍", "🗺️", "📡", "🔧", "📊", "✅", "💡", "📌"]
    reasoning_rows = ""
    for i, step in enumerate(reasoning):
        icon = step_icons[i] if i < len(step_icons) else "•"
        reasoning_rows += (
            f"<tr>"
            f"<td class='step-num'>{icon}</td>"
            f"<td class='step-label'>{step['step']}</td>"
            f"<td class='step-detail'>{step['detail']}</td>"
            f"</tr>"
        )

    default_tweak = (
        "💡 <strong>Want to tweak?</strong> &nbsp;"
        "Edit comparators in <code>config/providers.yaml</code> &nbsp;|&nbsp; "
        "Edit chart defaults in <code>config/output_config.yaml</code> &nbsp;|&nbsp; "
        "Add time horizon to your query, e.g. <em>\"last 10 years\"</em>"
    )
    tweak_html = tweak_hint if tweak_hint else default_tweak

    # ── Key reads section ────────────────────────────────────────────────────
    key_reads_section = ""
    if key_reads:
        cards_html = ""
        for kr in key_reads:
            icon  = kr.get("icon", "📌")
            title = kr.get("title", "")
            body  = kr.get("body", "")
            tag   = kr.get("tag", "")
            tag_colour = {
                "Bullish": "#003399", "Bearish": "#CC0001",
                "Risk": "#FF6600",    "Neutral": "#6B7280",
            }.get(tag, "#6B7280")
            tag_html = (
                f"<span class='kr-tag' style='background:{tag_colour}20;"
                f"color:{tag_colour};border:1px solid {tag_colour}40'>{tag}</span>"
            ) if tag else ""
            cards_html += (
                f"<div class='kr-card'>"
                f"<div class='kr-header'>"
                f"<span class='kr-icon'>{icon}</span>"
                f"<span class='kr-title'>{title}</span>"
                f"{tag_html}"
                f"</div>"
                f"<div class='kr-body'>{body}</div>"
                f"</div>"
            )
        key_reads_section = (
            f"<div class='section'>"
            f"<div class='section-title'>🔑 Key Reads</div>"
            f"<div class='kr-grid'>{cards_html}</div>"
            f"</div>"
        )

    # ── Summary table ────────────────────────────────────────────────────────
    table_html = ""
    for row in table_rows:
        raw_change = row.get("_raw_change", "")
        if not raw_change and row.get("change") is not None:
            raw_change = _arrow(row["change"], row.get("change_unit", "pp"))
        sep_class  = " separator" if row.get("separator") else ""
        bold_class = " bold-row"  if row.get("bold")      else ""
        note_html  = f"<span class='row-note'>{row['note']}</span>" if row.get("note") else ""
        table_html += (
            f"<tr class='{sep_class}{bold_class}'>"
            f"<td class='tbl-label'>{row['label']}{note_html}</td>"
            f"<td class='tbl-value'>{row['value']}</td>"
            f"<td class='tbl-period'>{row.get('period', '')}</td>"
            f"<td class='tbl-change'>{raw_change}</td>"
            f"</tr>"
        )

    # ── Chart sections ───────────────────────────────────────────────────────
    chart_sections = ""
    for chart_fig, chart_title in zip(figs, chart_titles):
        chart_div = _embed_fig(chart_fig)
        chart_sections += (
            f"<div class='section'>"
            f"<div class='section-title'>{chart_title}</div>"
            f"<div class='chart-wrap'>{chart_div}</div>"
            f"</div>"
        )

    # ── Footer ───────────────────────────────────────────────────────────────
    now      = datetime.now().strftime("%d %b %Y %H:%M")
    source   = meta.get("source", "—")
    vintage  = meta.get("vintage", "—")
    series   = meta.get("series_id", "—")
    endpoint = meta.get("endpoint", "—")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Analyst Report — {intent}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: {_LIGHT_GREY}; color: {_TEXT};
    padding: 32px 40px; max-width: 1200px; margin: 0 auto;
  }}
  .header {{ display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 28px; }}
  .header-left h1 {{ font-size: 1.55rem; font-weight: 700; color: {_PGGM_BLUE}; line-height: 1.2; }}
  .header-left .query-badge {{
    display: inline-block; margin-top: 8px;
    background: #EEF1FB; border: 1px solid #C5CDE8;
    color: {_PGGM_BLUE}; font-size: 0.88rem;
    padding: 5px 12px; border-radius: 20px; font-style: italic;
  }}
  .header-right {{ text-align: right; font-size: 0.8rem; color: {_SUBTLE}; line-height: 1.6; }}
  .intent-pill {{
    display: inline-block; background: {_PGGM_BLUE}; color: white;
    font-size: 0.75rem; font-weight: 600; letter-spacing: .05em;
    padding: 3px 10px; border-radius: 12px; text-transform: uppercase;
  }}
  .section {{
    background: white; border: 1px solid {_BORDER};
    border-radius: 10px; padding: 22px 26px; margin-bottom: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
  }}
  .section-title {{
    font-size: 0.72rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: {_SUBTLE}; margin-bottom: 14px;
    padding-bottom: 8px; border-bottom: 1px solid {_BORDER};
  }}
  /* Reasoning */
  .reasoning-table {{ width: 100%; border-collapse: collapse; }}
  .reasoning-table td {{ padding: 7px 10px; vertical-align: top; }}
  .step-num {{ width: 32px; font-size: 1.1rem; text-align: center; }}
  .step-label {{ width: 200px; font-weight: 600; font-size: 0.85rem; color: {_PGGM_BLUE}; }}
  .step-detail {{ font-size: 0.85rem; color: {_TEXT}; line-height: 1.5; }}
  .reasoning-table tr:not(:last-child) td {{ border-bottom: 1px solid {_LIGHT_GREY}; }}
  .tweak-hint {{
    margin-top: 12px; font-size: 0.78rem; color: {_SUBTLE};
    background: #FFFBEA; border: 1px solid #F5E4A0; border-radius: 6px; padding: 8px 12px;
  }}
  .tweak-hint code {{ background: #F5E4A0; border-radius: 3px; padding: 1px 5px; font-size: 0.75rem; }}
  /* Key reads */
  .kr-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }}
  .kr-card {{
    background: {_LIGHT_GREY}; border: 1px solid {_BORDER};
    border-radius: 8px; padding: 14px 16px; border-left: 4px solid {_PGGM_BLUE};
  }}
  .kr-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
  .kr-icon {{ font-size: 1.1rem; }}
  .kr-title {{ font-weight: 700; font-size: 0.88rem; color: {_TEXT}; flex: 1; }}
  .kr-tag {{
    font-size: 0.68rem; font-weight: 700; padding: 2px 7px;
    border-radius: 10px; text-transform: uppercase; letter-spacing: .04em;
  }}
  .kr-body {{ font-size: 0.83rem; color: {_SUBTLE}; line-height: 1.55; }}
  .kr-body strong {{ color: {_TEXT}; }}
  /* Table */
  .summary-table {{ width: 100%; border-collapse: collapse; }}
  .summary-table th {{
    text-align: left; font-size: 0.73rem; font-weight: 700; color: {_SUBTLE};
    letter-spacing: .06em; text-transform: uppercase;
    padding: 6px 12px; border-bottom: 2px solid {_BORDER};
  }}
  .summary-table td {{ padding: 9px 12px; font-size: 0.88rem; }}
  .summary-table tr:not(:last-child) td {{ border-bottom: 1px solid {_LIGHT_GREY}; }}
  .summary-table tr.separator td {{ border-top: 2px solid {_BORDER}; padding-top: 14px; }}
  .summary-table tr.bold-row td {{ font-weight: 700; }}
  .tbl-value  {{ font-weight: 600; font-size: 1.05rem; color: {_PGGM_BLUE}; }}
  .tbl-period {{ color: {_SUBTLE}; font-size: 0.8rem; }}
  .tbl-change {{ white-space: nowrap; }}
  .row-note   {{ display: block; font-size: 0.73rem; color: {_SUBTLE}; font-weight: 400; }}
  /* Charts */
  .chart-wrap {{ margin-top: 4px; }}
  /* Footer */
  .footer {{
    font-size: 0.75rem; color: {_SUBTLE}; margin-top: 20px;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  }}
  .footer-item strong {{ display: block; color: {_TEXT}; font-size: 0.78rem; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>Investment Analyst Report</h1>
    <span class="query-badge">"{query}"</span>
  </div>
  <div class="header-right">
    <span class="intent-pill">{intent}</span><br/>Generated {now}
  </div>
</div>

<div class="section">
  <div class="section-title">🧠 Reasoning Chain</div>
  <table class="reasoning-table">{reasoning_rows}</table>
  <div class="tweak-hint">{tweak_html}</div>
</div>

{key_reads_section}

<div class="section">
  <div class="section-title">📋 Summary Table</div>
  <table class="summary-table">
    <thead><tr><th>Tenor / Metric</th><th>Value</th><th>Period / comparisons</th><th>Change</th></tr></thead>
    <tbody>{table_html}</tbody>
  </table>
</div>

{chart_sections}

<div class="footer">
  <div class="footer-item"><strong>✅ Source</strong>{source}</div>
  <div class="footer-item"><strong>📅 Vintage</strong>{vintage}</div>
  <div class="footer-item"><strong>🔑 Series ID</strong>{series}</div>
  <div class="footer-item"><strong>🌐 Endpoint</strong><span style="word-break:break-all">{endpoint}</span></div>
</div>

</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(out_path)


"""
ecb_hawkometer/dashboard.py
---------------------------
Reads analyzer JSON output, generates a self-contained HTML dashboard,
and opens it in the default browser.
"""

from __future__ import annotations

import html as _html_escape
import os
import webbrowser
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
_OUTPUT_FILE = os.path.join(_OUTPUT_DIR, "ecb_dashboard.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: object) -> str:
    """HTML-escape a value for safe insertion into HTML."""
    return _html_escape.escape(str(text) if text is not None else "")


def _days_until(date_str: str) -> str:
    """Return human-readable days-until string for an ISO date."""
    try:
        target = date.fromisoformat(date_str)
        delta = (target - date.today()).days
        if delta == 0:
            return "today"
        elif delta == 1:
            return "1 day away"
        elif delta > 0:
            return f"{delta} days away"
        else:
            return f"{abs(delta)} days ago"
    except (ValueError, TypeError):
        return ""


def _score_colour(score: float) -> str:
    """Return a hex colour based on hawkishness score (1–10)."""
    if score < 4:
        return "#58a6ff"   # blue  — dovish
    elif score < 6:
        return "#8b949e"   # grey  — neutral
    else:
        return "#f85149"   # red   — hawkish


def _trend_arrow(trend: str) -> str:
    """Return an HTML arrow span for a trend string."""
    trend_l = (trend or "").lower()
    if trend_l in ("increasing", "hawkish", "up"):
        return '<span style="color:#f85149" title="Increasing">&#8593;</span>'
    elif trend_l in ("decreasing", "dovish", "down"):
        return '<span style="color:#3fb950" title="Decreasing">&#8595;</span>'
    else:
        return '<span style="color:#8b949e" title="Stable">&#8594;</span>'


def _direction_colour(direction: str) -> str:
    d = (direction or "").lower()
    if d == "hawkish":
        return "#f85149"
    elif d == "dovish":
        return "#3fb950"
    else:
        return "#8b949e"


def _verdict_colours(prediction: str) -> tuple[str, str]:
    """Return (background, foreground) for a prediction verdict."""
    p = (prediction or "").upper()
    if p == "HIKE":
        return "#6e2020", "#f85149"
    elif p == "CUT":
        return "#1a3d2b", "#3fb950"
    else:
        return "#1c2333", "#8b949e"


def _confidence_badge(confidence: str) -> str:
    c = (confidence or "").upper()
    colour_map = {
        "HIGH":   ("#3fb950", "#0d1117"),
        "MEDIUM": ("#e3b341", "#0d1117"),
        "LOW":    ("#f85149", "#ffffff"),
    }
    bg, fg = colour_map.get(c, ("#8b949e", "#0d1117"))
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 10px;'
        f'border-radius:4px;font-size:0.8em;font-weight:bold;'
        f'letter-spacing:0.08em;">{_esc(c or confidence)}</span>'
    )


def _score_gauge(score: float) -> str:
    """Return an inline HTML gauge bar for a score 0–10."""
    pct = min(max(score / 10.0, 0.0), 1.0) * 100
    colour = _score_colour(score)
    return (
        f'<div style="display:inline-block;vertical-align:middle;'
        f'width:80px;height:10px;background:#21262d;border-radius:4px;'
        f'overflow:hidden;margin-left:6px;">'
        f'<div style="width:{pct:.1f}%;height:100%;background:{colour};"></div>'
        f'</div>'
    )


def _weighted_gauge(score: float) -> str:
    """Wider gauge for the policy prediction section."""
    pct = min(max(score / 10.0, 0.0), 1.0) * 100
    colour = _score_colour(score)
    return (
        f'<div style="width:100%;height:18px;background:#21262d;border-radius:6px;'
        f'overflow:hidden;margin:8px 0;position:relative;">'
        f'<div style="width:{pct:.1f}%;height:100%;background:{colour};'
        f'transition:width 0.3s;"></div>'
        f'<div style="position:absolute;top:0;left:50%;width:2px;height:100%;'
        f'background:#30363d;"></div>'
        f'</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:0.7em;'
        f'color:#8b949e;"><span>0 (Dovish)</span><span>5 (Neutral)</span>'
        f'<span>10 (Hawkish)</span></div>'
    )


def _theme_chips(themes: list) -> str:
    chips = ""
    for t in (themes or []):
        chips += (
            f'<span style="background:#21262d;color:#8b949e;padding:2px 8px;'
            f'border-radius:12px;font-size:0.75em;margin:2px;'
            f'display:inline-block;border:1px solid #30363d;">'
            f'{_esc(t)}</span>'
        )
    return chips


def _sparkline_svg(scores: list[float]) -> str:
    """Generate a simple SVG polyline sparkline from a list of scores (0–10)."""
    if len(scores) < 2:
        return ""
    w, h, pad = 200, 40, 4
    min_s, max_s = min(scores), max(scores)
    rng = max_s - min_s or 1.0
    n = len(scores)
    points = []
    for i, s in enumerate(scores):
        x = pad + (i / (n - 1)) * (w - 2 * pad)
        y = (h - pad) - ((s - min_s) / rng) * (h - 2 * pad)
        points.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(points)
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'style="display:block;margin:6px 0;">'
        f'<polyline points="{pts_str}" fill="none" stroke="#58a6ff" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# CSS / JS
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: #0d1117;
    color: #e6edf3;
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    padding: 16px;
}
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-family: 'Courier New', Consolas, monospace; font-size: 1.4em; color: #58a6ff; }
h2 { font-size: 1.05em; color: #e6edf3; margin-bottom: 10px;
     border-bottom: 1px solid #30363d; padding-bottom: 6px; }
h3 { font-size: 0.95em; color: #8b949e; margin-bottom: 6px; }
header { margin-bottom: 20px; }
.meta { font-family: 'Courier New', Consolas, monospace; font-size: 0.78em;
        color: #8b949e; margin-top: 4px; }
.card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
}
.verdict-box {
    display: inline-flex; align-items: center; gap: 14px;
    padding: 12px 24px; border-radius: 8px; margin-bottom: 12px;
}
.verdict-text {
    font-family: 'Courier New', Consolas, monospace;
    font-size: 2.4em; font-weight: bold; letter-spacing: 0.1em;
}
.score-num {
    font-family: 'Courier New', Consolas, monospace;
    font-weight: bold;
}
table {
    width: 100%; border-collapse: collapse;
    font-family: 'Courier New', Consolas, monospace;
    font-size: 0.82em;
}
th {
    background: #21262d; color: #8b949e; font-weight: 600;
    padding: 8px 10px; text-align: left; border-bottom: 2px solid #30363d;
    cursor: pointer; user-select: none; white-space: nowrap;
}
th:hover { color: #58a6ff; }
th.sort-asc::after  { content: " ↑"; color: #58a6ff; }
th.sort-desc::after { content: " ↓"; color: #58a6ff; }
td {
    padding: 7px 10px; border-bottom: 1px solid #21262d;
    vertical-align: middle;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #1c2333; }
details { margin-bottom: 8px; }
summary {
    cursor: pointer; padding: 10px 12px;
    background: #21262d; border: 1px solid #30363d;
    border-radius: 6px; font-weight: 600; color: #e6edf3;
    list-style: none; display: flex; align-items: center; gap: 8px;
}
summary:hover { background: #2d333b; }
details[open] summary { border-radius: 6px 6px 0 0; border-bottom-color: #161b22; }
.detail-body {
    background: #161b22; border: 1px solid #30363d; border-top: none;
    border-radius: 0 0 6px 6px; padding: 14px 16px;
}
blockquote {
    border-left: 3px solid #58a6ff; padding: 8px 14px;
    background: #0d1117; border-radius: 0 6px 6px 0;
    margin: 10px 0; font-style: italic; color: #8b949e;
}
.rubric-table th { background: #161b22; }
"""

_JS = """
(function() {
    function sortTable(table, colIdx, asc) {
        var tbody = table.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {
            var ta = a.cells[colIdx] ? a.cells[colIdx].innerText.trim() : '';
            var tb = b.cells[colIdx] ? b.cells[colIdx].innerText.trim() : '';
            var na = parseFloat(ta), nb = parseFloat(tb);
            if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
            return asc ? ta.localeCompare(tb) : tb.localeCompare(ta);
        });
        rows.forEach(function(r) { tbody.appendChild(r); });
    }

    document.querySelectorAll('th[data-col]').forEach(function(th) {
        th.addEventListener('click', function() {
            var table = th.closest('table');
            var col   = parseInt(th.dataset.col);
            var asc   = th.classList.contains('sort-desc');
            table.querySelectorAll('th').forEach(function(h) {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            th.classList.add(asc ? 'sort-asc' : 'sort-desc');
            sortTable(table, col, asc);
        });
    });
})();
"""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_header(next_meeting_date: str, speech_count: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    days_str = _days_until(next_meeting_date)
    days_part = f" ({days_str})" if days_str else ""
    return (
        f'<header class="card">'
        f'<h1>ECB Policy Monitor</h1>'
        f'<div class="meta">'
        f'Generated: {_esc(ts)} | '
        f'Next meeting: {_esc(next_meeting_date)}{_esc(days_part)} | '
        f'Speeches analysed: {speech_count}'
        f'</div>'
        f'</header>'
    )


def _build_header_simple(speech_count: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f'<header class="card">'
        f'<h1>ECB Policy Monitor</h1>'
        f'<div class="meta">'
        f'Generated: {_esc(ts)} | '
        f'Speeches analysed (12-week window): {speech_count}'
        f'</div>'
        f'</header>'
    )


def _shift_badge(shift_label: str) -> str:
    """Return a coloured badge for the hawk/dove shift."""
    s = (shift_label or "").lower()
    if "more hawkish" in s:
        bg, fg = "#6e2020", "#f85149"
    elif "more dovish" in s:
        bg, fg = "#1a3d2b", "#3fb950"
    else:
        bg, fg = "#21262d", "#8b949e"
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:4px;font-size:0.78em;font-weight:bold;'
        f'letter-spacing:0.06em;white-space:nowrap;">'
        f'{_esc(shift_label or "Stable")}</span>'
    )


def _keyword_chips(keywords: list, colour: str = "#8b949e", border: str = "#30363d") -> str:
    """Render a list of keywords as small chips."""
    chips = ""
    for kw in (keywords or []):
        chips += (
            f'<span style="background:#21262d;color:{colour};padding:2px 8px;'
            f'border-radius:10px;font-size:0.74em;margin:2px 2px 2px 0;'
            f'display:inline-block;border:1px solid {border};'
            f'font-family:\'Courier New\',Consolas,monospace;white-space:nowrap;">'
            f'{_esc(kw)}</span>'
        )
    return chips


def _policy_relevance_bar(score: int) -> str:
    """Render a compact relevance indicator (1–10) as dots."""
    filled = max(0, min(10, score))
    dots = ""
    for i in range(1, 11):
        col = "#58a6ff" if i <= filled else "#21262d"
        dots += f'<span style="color:{col};font-size:0.7em;">&#9679;</span>'
    return f'<span title="Policy relevance {filled}/10">{dots}</span>'


def _build_last_week_section(last_week_speeches: list[dict]) -> str:
    """Build the top section showing speeches from the last 7 days.

    Ranking: primary = speaker weight (higher = first), secondary = policy
    relevance score (monetary policy content ranked higher).
    """
    from ecb_hawkometer.weights import get_weight

    if not last_week_speeches:
        return (
            '<section class="card">'
            '<h2>Speeches This Week</h2>'
            '<p style="color:#8b949e;">No speeches in the last 7 days.</p>'
            '</section>'
        )

    def _sort_key(item: dict) -> tuple:
        weight = get_weight(item.get("speaker", ""))
        relevance = int(item.get("policy_relevance_score") or 0)
        return (-weight, -relevance)

    items_sorted = sorted(last_week_speeches, key=_sort_key)

    cards_html = ""
    for rank, item in enumerate(items_sorted):
        speaker       = item.get("speaker", "Unknown")
        date_str      = item.get("date", "")
        title         = item.get("title", "")
        url           = item.get("url", "")
        topic_kws     = item.get("topic_keywords") or []
        content_kws   = item.get("content_keywords") or []
        tone_comp     = item.get("tone_comparison", "")
        score         = float(item.get("hawkishness_score") or 0)
        prior_score   = float(item.get("prior_12w_score") or 0)
        shift_label   = item.get("shift_label", "Stable")
        relevance     = int(item.get("policy_relevance_score") or 0)
        is_mp         = item.get("is_monetary_policy", False)

        score_col  = _score_colour(score)
        prior_col  = _score_colour(prior_score)
        badge      = _shift_badge(shift_label)
        gauge      = _score_gauge(score)
        rel_bar    = _policy_relevance_bar(relevance)
        weight     = get_weight(speaker)

        # Dim non-monetary-policy cards slightly
        card_opacity = "1.0" if is_mp else "0.72"
        mp_label = (
            '<span style="background:#1c2b20;color:#3fb950;padding:1px 7px;'
            'border-radius:3px;font-size:0.7em;font-weight:600;margin-left:6px;">monetary policy</span>'
            if is_mp else
            '<span style="background:#21262d;color:#8b949e;padding:1px 7px;'
            'border-radius:3px;font-size:0.7em;margin-left:6px;">off-mandate</span>'
        )

        title_link = (
            f'<a href="{_esc(url)}" target="_blank" style="color:#8b949e;font-size:0.8em;">'
            f'{_esc(title)}</a>'
            if url else
            f'<span style="color:#8b949e;font-size:0.8em;">{_esc(title)}</span>'
        )

        # Topic chips (slightly brighter)
        topic_html = _keyword_chips(topic_kws, colour="#c9d1d9", border="#444c56")
        # Content chips (dimmer, smaller)
        content_html = _keyword_chips(content_kws, colour="#8b949e", border="#30363d")

        cards_html += f"""
        <div style="border:1px solid #30363d;border-radius:6px;padding:12px 14px;
                    margin-bottom:10px;background:#0d1117;opacity:{card_opacity};">

          <!-- Header row: speaker / date / badge / scores -->
          <div style="display:flex;justify-content:space-between;align-items:center;
                      flex-wrap:wrap;gap:6px;margin-bottom:6px;">
            <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
              <span style="font-weight:700;color:#e6edf3;">{_esc(speaker)}</span>
              <span style="color:#8b949e;font-size:0.78em;">w={weight:.1f}</span>
              <span style="color:#8b949e;font-size:0.78em;margin-left:4px;">{_esc(date_str)}</span>
              {mp_label}
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              {badge}
              <span style="font-size:0.78em;color:#8b949e;">
                <span class="score-num" style="color:{score_col};">{score:.1f}</span>
                {gauge}
                <span style="color:#555;">vs</span>
                <span class="score-num" style="color:{prior_col};">{prior_score:.1f}</span>
                <span style="color:#555;font-size:0.85em;">12w</span>
              </span>
            </div>
          </div>

          <!-- Title link + policy relevance -->
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
            {title_link}
            <span style="margin-left:auto;white-space:nowrap;">{rel_bar}</span>
          </div>

          <!-- Topic keywords -->
          <div style="margin-bottom:4px;">
            <span style="font-size:0.7em;color:#555;text-transform:uppercase;
                         letter-spacing:0.06em;margin-right:6px;">topic</span>
            {topic_html}
          </div>

          <!-- Content keywords -->
          <div style="margin-bottom:10px;">
            <span style="font-size:0.7em;color:#555;text-transform:uppercase;
                         letter-spacing:0.06em;margin-right:6px;">content</span>
            {content_html}
          </div>

          <!-- Tone comparison (semantic) -->
          <div style="border-top:1px solid #21262d;padding-top:8px;
                      font-size:0.8em;color:#8b949e;line-height:1.55;">
            <span style="font-size:0.7em;text-transform:uppercase;letter-spacing:0.06em;
                         color:#555;margin-right:6px;">tone vs prior</span>
            {_esc(tone_comp)}
          </div>

        </div>"""

    return f"""
    <section class="card">
      <h2>Speeches This Week</h2>
      {cards_html}
    </section>"""


def _stance_badge(stance: str) -> str:
    """Return a coloured inline badge for a stance_signal string."""
    s = (stance or "").lower()
    if "hawkish" in s and "neutral" not in s:
        bg, fg = "#6e2020", "#f85149"
    elif "neutral-hawkish" in s or ("neutral" in s and "hawk" in s):
        bg, fg = "#3d2a0a", "#e3b341"
    elif "dovish" in s:
        bg, fg = "#1a3d2b", "#3fb950"
    elif "off-mandate" in s:
        bg, fg = "#1c2333", "#8b949e"
    else:
        bg, fg = "#21262d", "#8b949e"
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:4px;font-size:0.72em;font-weight:600;'
        f'letter-spacing:0.05em;white-space:nowrap;margin-left:6px;">'
        f'{_esc(stance or "neutral")}</span>'
    )


def _build_speaker_board(speaker_scores: list[dict]) -> str:
    from ecb_hawkometer.weights import get_tier

    rows = ""
    for s in speaker_scores:
        speaker    = s.get("speaker", "")
        score      = float(s.get("hawkishness_score") or 0)
        trend      = s.get("trend", "stable")
        themes     = s.get("key_themes") or []
        tone_kws   = s.get("tone_keywords") or []
        stance     = s.get("stance_signal", "")
        tier       = get_tier(speaker)

        colour     = _score_colour(score)
        gauge      = _score_gauge(score)
        arrow      = _trend_arrow(trend)
        theme_chips = _keyword_chips(themes, colour="#c9d1d9", border="#444c56")
        tone_chips  = _keyword_chips(tone_kws, colour="#8b949e", border="#30363d")
        badge       = _stance_badge(stance)

        # Speaker cell: name + stance badge
        speaker_cell = (
            f'<span style="font-weight:600;">{_esc(speaker)}</span>'
            f'{badge}'
        )

        # Themes cell: two chip rows with labels
        themes_cell = (
            f'<div style="margin-bottom:3px;">'
            f'<span style="font-size:0.68em;color:#555;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-right:4px;">themes</span>'
            f'{theme_chips}</div>'
            f'<div>'
            f'<span style="font-size:0.68em;color:#555;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-right:4px;">tone</span>'
            f'{tone_chips}</div>'
        )

        rows += (
            f'<tr>'
            f'<td style="white-space:nowrap;">{speaker_cell}</td>'
            f'<td style="color:#8b949e;text-align:center;">{tier}</td>'
            f'<td style="white-space:nowrap;">'
            f'  <span class="score-num" style="color:{colour};">{score:.1f}</span>'
            f'  {gauge}'
            f'</td>'
            f'<td style="text-align:center;">{arrow}</td>'
            f'<td>{themes_cell}</td>'
            f'</tr>'
        )

    return f"""
    <section class="card">
      <h2>Speaker Hawkishness Board</h2>
      <table id="speaker-table">
        <thead><tr>
          <th data-col="0">Speaker</th>
          <th data-col="1" style="text-align:center;">Tier</th>
          <th data-col="2">Score</th>
          <th data-col="3" style="text-align:center;">Trend</th>
          <th data-col="4">Themes / Tone</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""


def _build_deep_dive(speaker_scores: list[dict], db_speeches: list[dict]) -> str:
    # Group db_speeches by speaker
    from collections import defaultdict
    speeches_by_speaker: dict[str, list[dict]] = defaultdict(list)
    for sp in (db_speeches or []):
        name = sp.get("speaker", "")
        speeches_by_speaker[name].append(sp)

    items = ""
    for s in speaker_scores:
        speaker   = s.get("speaker", "")
        themes    = s.get("key_themes") or []
        tone_kws  = s.get("tone_keywords") or []
        stance    = s.get("stance_signal", "")
        score     = float(s.get("hawkishness_score") or 0)
        colour    = _score_colour(score)

        spch_list = sorted(
            speeches_by_speaker.get(speaker, []),
            key=lambda x: x.get("date", ""),
            reverse=True,
        )

        # Sparkline if 3+ speeches
        sparkline_html = ""
        if len(spch_list) >= 3:
            scores_over_time = [
                float(sp.get("score", score))
                for sp in sorted(spch_list, key=lambda x: x.get("date", ""))
            ]
            sparkline_html = (
                '<div style="margin-top:10px;">'
                '<h3>Hawkishness over time</h3>'
                + _sparkline_svg(scores_over_time)
                + '</div>'
            )

        speech_links = ""
        for sp in spch_list:
            d     = _esc(sp.get("date", ""))
            title = _esc(sp.get("title", ""))
            url   = sp.get("url", "")
            speech_links += (
                f'<li style="margin:4px 0;">'
                f'<span style="color:#8b949e;font-size:0.8em;">{d}</span> '
                f'<a href="{_esc(url)}" target="_blank">{title}</a>'
                f'</li>'
            )

        speeches_html = ""
        if speech_links:
            speeches_html = (
                f'<h3 style="margin-top:12px;">Recent Speeches</h3>'
                f'<ul style="list-style:none;padding:0;margin-top:6px;">'
                f'{speech_links}</ul>'
            )

        # Keyword chip rows
        theme_chips = _keyword_chips(themes, colour="#c9d1d9", border="#444c56")
        tone_chips  = _keyword_chips(tone_kws, colour="#8b949e", border="#30363d")
        stance_badge = _stance_badge(stance)

        keyword_block = (
            f'<div style="margin-bottom:6px;">'
            f'<span style="font-size:0.68em;color:#555;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-right:4px;">themes</span>'
            f'{theme_chips}</div>'
            f'<div style="margin-bottom:8px;">'
            f'<span style="font-size:0.68em;color:#555;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-right:4px;">tone</span>'
            f'{tone_chips}</div>'
            f'<div style="margin-bottom:10px;">'
            f'<span style="font-size:0.68em;color:#555;text-transform:uppercase;'
            f'letter-spacing:0.05em;margin-right:4px;">stance</span>'
            f'{stance_badge}</div>'
        )

        items += f"""
        <details>
          <summary>
            <span style="font-family:'Courier New',Consolas,monospace;
                         color:{colour};">{_esc(f"{score:.1f}")}</span>
            &nbsp;{_esc(speaker)}
          </summary>
          <div class="detail-body">
            {keyword_block}
            {speeches_html}
            {sparkline_html}
          </div>
        </details>"""

    return f"""
    <section class="card">
      <h2>Per-Speaker Deep Dive</h2>
      {items}
    </section>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dashboard(
    speaker_scores: list[dict],
    policy_prediction: dict,
    db_speeches: list[dict],
    last_week_speeches: Optional[list[dict]] = None,
) -> str:
    """
    Generate the ECB dashboard HTML file.

    Args:
        speaker_scores: list of dicts from analyzer.get_speaker_scores()
        policy_prediction: dict from analyzer.get_policy_prediction() (unused, kept for compat)
        db_speeches: list of speech dicts from db.get_speeches()
        last_week_speeches: list of per-speech analysis dicts for the last 7 days

    Returns:
        Absolute path to the generated HTML file.

    Side effect: opens the file in the default browser via webbrowser.open()
    """
    speech_count = len(db_speeches) if db_speeches else 0

    header_html    = _build_header_simple(speech_count)
    last_week_html = _build_last_week_section(last_week_speeches or [])
    board_html     = _build_speaker_board(speaker_scores)
    deepdive_html  = _build_deep_dive(speaker_scores, db_speeches)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ECB Policy Monitor</title>
  <style>
{_CSS}
  </style>
</head>
<body>
  {header_html}
  {last_week_html}
  {board_html}
  {deepdive_html}
  <script>
{_JS}
  </script>
</body>
</html>"""

    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    output_path = _OUTPUT_FILE
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(full_html)

    webbrowser.open("file://" + os.path.abspath(output_path))
    return os.path.abspath(output_path)

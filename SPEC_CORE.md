> **Load this every session. Contains intent taxonomy, output templates, and agent query flow.**

---

# Investment Analyst Copilot — Core Spec

---

## Purpose

You are an investment analyst assistant for a senior rates portfolio manager at a large
European pension fund. When given a natural language query, you will:

1. Classify the query into a known intent
2. Route to the correct data provider
3. Fetch live data via the provider's public API
4. Render a standardised output (chart + table + annotations)

Python 3.10+, VS Code, with `pandas`, `matplotlib`, `plotly`, and `requests` available.

---

## Project Structure

```
investment-analyst/
├── INVESTMENT_ANALYST_SPEC.md   ← original spec (kept for reference)
├── SPEC_CORE.md                 ← this file: load every session
├── SPEC_PROVIDERS.md            ← load on demand for provider/API work
├── providers/
│   ├── eurostat.py              ← Eurostat API client
│   ├── ecb_sdw.py               ← ECB Statistical Data Warehouse client
│   ├── fred.py                  ← FRED API client
│   ├── imf.py                   ← IMF WEO/IFS client
│   └── iea.py                   ← IEA data client
├── intents/
│   ├── macro_indicator.py       ← MACRO_INDICATOR handler
│   ├── cross_section.py         ← CROSS_SECTION handler
│   ├── issuance.py              ← ISSUANCE handler
│   ├── flow_map.py              ← FLOW_MAP handler
│   ├── rates_curve.py           ← RATES_CURVE handler
│   └── relative_value.py        ← RELATIVE_VALUE handler
├── router.py                    ← Intent classifier + dispatcher
├── render.py                    ← Output rendering (charts, tables)
├── config/
│   ├── providers.yaml           ← API endpoints, series IDs
│   ├── taxonomy.yaml            ← Keyword → Intent mapping
│   └── output_config.yaml       ← Chart styles, units, comparators
├── setup/
│   └── bootstrap.md             ← API setup walkthrough (see SPEC_PROVIDERS.md)
└── main.py                      ← Entry point: accepts natural language query
```

---

## Layer 1 — Query Taxonomy

Every query maps to one of these intents:

| Intent ID        | Description                          | Example Query                              |
|------------------|--------------------------------------|--------------------------------------------|
| MACRO_INDICATOR  | Single macro metric, point-in-time   | "Where is Eurozone inflation now?"         |
| CROSS_SECTION    | Metric across a set of entities      | "Debt-to-GDP across all EU member states"  |
| ISSUANCE         | Sovereign debt supply / calendar     | "How much will Germany issue this year?"   |
| FLOW_MAP         | Physical or financial flow diagram   | "Show me a Sankey of global oil flows"     |
| RATES_CURVE      | Yield curve or rate term structure   | "Show me the German Bund curve"            |
| RELATIVE_VALUE   | Spread or ratio between two things   | "10y BTP-Bund spread over 5 years"         |

**Classification rules for Copilot:**
- A query containing country/region names + a macro variable → `MACRO_INDICATOR`
- A query asking for a list, ranking, or comparison across entities → `CROSS_SECTION`
- A query about "issuance", "supply", "DMO", or "auction" → `ISSUANCE`
- A query containing "Sankey", "flows", "pipeline", or "barrels" → `FLOW_MAP`
- A query about "curve", "yields", "tenor", or "term structure" → `RATES_CURVE`
- A query containing "spread", "vs", "relative to", or "differential" → `RELATIVE_VALUE`

---

## Layer 3 — Output Templates

Each intent has a fixed output structure. Always follow this exactly.

### MACRO_INDICATOR
```
Headline:  [Metric] [Geography]: [Value] [Unit] ([Period])
           YoY change: [+/- X pp]

Comparators:
  [Geography 1]: [Value]
  [Geography 2]: [Value]   ← default comparators: US, Japan

Chart: Time series, last 5 years, monthly, plotly line chart
       x-axis: date | y-axis: metric value | title: "{Metric} — {Geography}"
       Overlay comparator lines if available

Annotation: Source: [Provider] | Vintage: [Date] | Next release: [Date if known]
```

**Transform rule:** For price indices (HICP, CPI, PCE), always report **YoY % change**,
not the index level. For fiscal metrics, report the **ratio** (e.g. % of GDP), not the
absolute value.

### CROSS_SECTION
```
Headline: [Metric] across [Entity set] — [Period]

Table: Ranked descending, all entities, columns: [Entity | Value | YoY change]
       Highlight in bold: top 3 and bottom 3

Chart: Horizontal bar chart, sorted descending, plotly
       Annotate EU/EZ average as vertical reference line if applicable

Footnote: Source: [Provider] | Vintage year: [Year]
```

### ISSUANCE
```
Headline: [Country] gross issuance [Year]: EUR [X]bn

Breakdown table:
  Instrument | Planned (EURbn) | Prior Year (EURbn) | YoY change
  Bills      | ...
  2y         | ...
  5y         | ...
  10y        | ...
  30y+       | ...
  Total      | ...

Chart: Stacked bar chart by instrument, current year vs prior year
       plotly bar chart

Source: [DMO name] | Publication date: [Date]
```

### FLOW_MAP
```
Chart: Sankey diagram (use plotly go.Sankey)
  Nodes: Origin country/region → Transit/hub → Destination country/region
  Link values: [Unit — mtoe for oil/gas, bcm for gas pipelines, mb/d for crude]
  Color: by origin region

Headline: [Commodity] flows — [Year]
Table: Top 10 bilateral flows, sorted by volume

Source: [IEA / Eurostat] | Reference year: [Year]
```

### RATES_CURVE
```
Headline: [Country/Region] yield curve as of [Date]

Chart: Line chart, tenors on x-axis (3m, 6m, 1y, 2y, 5y, 10y, 20y, 30y)
  Line 1: Current (solid)
  Line 2: 1 month ago (dashed)
  Line 3: 1 year ago (dotted)
  Highlight inversion points (where short > long) with shaded region

Table: Tenor | Current | 1m ago | 1y ago | Δ 1m | Δ 1y

Source: ECB SDW | Date: [Date]
```

### RELATIVE_VALUE
```
Headline: [Spread name]: [X] bps (as of [Date])
          [X]-year percentile: [P]th percentile

Chart: Time series, 5 years, weekly, plotly area chart
  Shade: above/below long-run average
  Annotate: current level, average, min, max

Table: Current | 1w ago | 1m ago | 1y ago | 5y avg | 5y min | 5y max

Source: ECB SDW | Date: [Date]
```

---

## router.py — Intent Classification Logic

```python
# router.py
# Copilot: implement this module

INTENT_KEYWORDS = {
    "MACRO_INDICATOR": ["inflation", "cpi", "hicp", "gdp", "unemployment",
                        "growth", "pmi", "current account", "trade balance"],
    "CROSS_SECTION":   ["all eu", "all member states", "eu countries", "compare",
                        "ranking", "ranked", "across countries", "debt-to-gdp"],
    "ISSUANCE":        ["issuance", "issue", "supply", "dmo", "auction",
                        "gross issuance", "net issuance", "borrow"],
    "FLOW_MAP":        ["sankey", "flows", "pipeline", "oil flows", "gas flows",
                        "lng", "barrels", "mtoe", "bcm", "energy flows"],
    "RATES_CURVE":     ["curve", "yields", "yield curve", "term structure",
                        "bund curve", "oat curve", "inversion"],
    "RELATIVE_VALUE":  ["spread", "vs", "versus", "relative to", "differential",
                        "btp-bund", "oat-bund", "basis"],
}

def classify(query: str) -> str:
    """Return the intent ID for a natural language query."""
    query_lower = query.lower()
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "UNKNOWN"
    return best

def extract_params(query: str, intent: str) -> dict:
    """Extract geography, metric, time horizon from query. Use NLP or regex."""
    # Copilot: implement parameter extraction per intent
    pass

def dispatch(query: str):
    """Classify, extract params, call the right intent handler."""
    intent = classify(query)
    params = extract_params(query, intent)
    handler_map = {
        "MACRO_INDICATOR": "intents.macro_indicator.run",
        "CROSS_SECTION":   "intents.cross_section.run",
        "ISSUANCE":        "intents.issuance.run",
        "FLOW_MAP":        "intents.flow_map.run",
        "RATES_CURVE":     "intents.rates_curve.run",
        "RELATIVE_VALUE":  "intents.relative_value.run",
    }
    # Copilot: import and call the correct handler with params
    pass
```

---

## Agent Mode — How Queries Flow

When you type a query into Copilot Chat (Agent mode), this is the exact sequence
Copilot should follow **without waiting for confirmation at each step**:

```
1. READ   SPEC_CORE.md for intent taxonomy, templates, and query flow
2. READ   SPEC_PROVIDERS.md (or config/providers.yaml) for series IDs
3. CLASSIFY the query → intent ID
4. CHECK  if the required provider module exists in providers/
           → if not, CREATE it following the reference pattern in SPEC_PROVIDERS.md
5. CHECK  if the intent handler exists in intents/
           → if not, CREATE it
6. RUN    the handler via python main.py "<query>" in the terminal
7. IF error → read the traceback, fix the file, re-run (max 3 retries)
8. OUTPUT the result: print table to chat + open the plotly chart as HTML
```

**Agent must never ask "should I create this file?" — just create it.**
**Agent must never hardcode data values — always fetch from the live API.**

---

## Copilot Instructions (read this before generating any code)

1. **Always use live API calls** — never hardcode or simulate data values
2. **Always follow the output template** for the detected intent exactly
3. **Always cite source and vintage** in every output
4. **Transform data before display** — YoY % for price indices, ratios for fiscal metrics
5. **Default comparators** for MACRO_INDICATOR: US (FRED) + Japan (FRED or IMF)
6. **Default time horizon**: 5 years for time series unless query specifies otherwise
7. **Chart library**: Use `plotly` for all charts (interactive HTML output)
8. **Error handling**: If an API call fails, print the URL attempted + HTTP status, then raise
9. **Series IDs**: Always look up in `config/providers.yaml` before hardcoding
10. **New intents**: If a query doesn't match any intent, ask for clarification — do not guess

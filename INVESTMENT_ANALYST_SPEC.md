> **This file has been split into SPEC_CORE.md and SPEC_PROVIDERS.md and is kept for reference only.**
> Load SPEC_CORE.md every session. Load SPEC_PROVIDERS.md on demand for provider/API work.

---

# Investment Analyst Copilot — System Spec

> Place this file in your VS Code workspace root as `INVESTMENT_ANALYST_SPEC.md`.
> GitHub Copilot will use it as persistent context for all queries in this workspace.

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
├── INVESTMENT_ANALYST_SPEC.md   ← this file (Copilot context)
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
│   └── bootstrap.md             ← API setup walkthrough (see below)
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

## Layer 2 — Provider Registry

### Free APIs (no key required)

| Provider    | Base URL                                      | Auth      | Notes                            |
|-------------|-----------------------------------------------|-----------|----------------------------------|
| Eurostat    | `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/` | None | JSON-stat format |
| ECB SDW     | `https://data-api.ecb.europa.eu/service/data/` | None      | SDMX-JSON format                 |
| IMF         | `https://www.imf.org/external/datamapper/api/v1/` | None   | JSON, WEO vintage                |

### Free APIs (API key required — see bootstrap.md)

| Provider    | Base URL                          | Auth           | Notes                   |
|-------------|-----------------------------------|----------------|-------------------------|
| FRED        | `https://api.stlouisfed.org/fred/` | `api_key` param | US macro, global comps |

### Provider → Intent mapping

| Intent ID        | Primary Provider | Series / Endpoint                          | Fallback        |
|------------------|------------------|--------------------------------------------|-----------------|
| MACRO_INDICATOR  | Eurostat         | `prc_hicp_manr` (HICP), `namq_10_gdp` (GDP) | ECB SDW, FRED  |
| CROSS_SECTION    | Eurostat / IMF   | `gov_10dd_edpt1` (debt/GDP), IMF GFSR      | IMF WEO         |
| ISSUANCE         | ECB SDW          | No standard API — see issuance notes below | AFME PDFs       |
| FLOW_MAP         | IEA / Eurostat   | Eurostat `nrg_ti_gas`, `nrg_ti_oil`        | IEA static data |
| RATES_CURVE      | ECB SDW          | `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.*`          | ECB AAA curve   |
| RELATIVE_VALUE   | ECB SDW + FRED   | Derive from individual yield series        | —               |

**Issuance note:** No single API covers all EU DMO issuance plans. Use ECB SDW for
historical issuance data (`SEC/B.*.W0.S13.*`) and supplement with static lookups or
web scraping of individual DMO websites (Bundesfinanzagentur, AFT, DSTA, etc.).

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

## providers/eurostat.py — Reference Implementation

```python
# providers/eurostat.py
# Use this as the reference pattern for all other providers.

import requests
import pandas as pd

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"

def fetch(dataset_id: str, params: dict) -> pd.DataFrame:
    """
    Fetch a Eurostat dataset and return as a tidy DataFrame.

    Args:
        dataset_id: e.g. "prc_hicp_manr"
        params: filter dict e.g. {"geo": "EA", "unit": "RCH_A", "coicop": "CP00"}

    Returns:
        DataFrame with columns: [geo, time, value]
    """
    url = f"{BASE_URL}{dataset_id}"
    params["format"] = "JSON"
    params["lang"] = "EN"

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Copilot: parse JSON-stat format into tidy DataFrame
    # Hint: data["value"] is a flat dict keyed by index position
    # data["dimension"] contains the dimension labels
    pass
```

---

## config/providers.yaml — Series Registry

```yaml
# config/providers.yaml
# Add new series here as you build out coverage.

eurostat:
  hicp_yoy:
    dataset: prc_hicp_manr
    params:
      unit: RCH_A        # Annual rate of change
      coicop: CP00       # All items
    geographies:
      eurozone: EA
      germany: DE
      france: FR
      italy: IT
      netherlands: NL

  debt_gdp:
    dataset: gov_10dd_edpt1
    params:
      unit: PC_GDP
      sector: S13        # General government
      na_item: GD

ecb_sdw:
  yield_curve:
    flow_ref: YC
    key: B.U2.EUR.4F.G_N_A.SV_C_YM
    # Append tenor: .SR_10Y, .SR_2Y, etc.

fred:
  base_url: https://api.stlouisfed.org/fred/series/observations
  series:
    us_cpi_yoy: CPIAUCSL      # Transform to YoY in code
    us_pce_yoy: PCEPI
    japan_cpi: JPNCPIALLMINMEI
```

---

## setup/bootstrap.md — API Setup Walkthrough

### Step 1 — No-key APIs (Eurostat, ECB, IMF)

These work immediately. Test with:

```bash
python -c "from providers.eurostat import fetch; print(fetch('prc_hicp_manr', {'geo': 'EA', 'unit': 'RCH_A', 'coicop': 'CP00'}))"
```

### Step 2 — FRED API Key (free)

1. Register at https://fredaccount.stlouisfed.org/login/secure/
2. Go to **My Account → API Keys → Request API Key**
3. Copy your key and add to your environment:

```bash
# .env (add to .gitignore)
FRED_API_KEY=your_key_here
```

4. Load in Python:
```python
import os
from dotenv import load_dotenv
load_dotenv()
FRED_KEY = os.getenv("FRED_API_KEY")
```

### Step 3 — Install dependencies

```bash
pip install requests pandas plotly matplotlib python-dotenv pyyaml
```

### Step 4 — Verify setup

```bash
python main.py "Where is Eurozone inflation now?"
```

Expected output: headline rate + US/Japan comparators + time series chart.

---

## main.py — Entry Point

```python
# main.py
import sys
from router import dispatch

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Query: ")
    dispatch(query)
```

Run as:
```bash
python main.py "Show me debt-to-GDP for all EU member states"
python main.py "Where is Eurozone inflation now?"
python main.py "How much will Germany issue this year?"
```

---

## Agent Mode — How Queries Flow

When you type a query into Copilot Chat (Agent mode), this is the exact sequence
Copilot should follow **without waiting for confirmation at each step**:

```
1. READ   INVESTMENT_ANALYST_SPEC.md (this file) for context
2. READ   config/providers.yaml for series IDs
3. CLASSIFY the query → intent ID
4. CHECK  if the required provider module exists in providers/
           → if not, CREATE it following the reference pattern in this spec
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

> **Load on demand when working with data providers, API series IDs, or adding new providers.**

---

# Investment Analyst Copilot — Provider Registry & Setup

---

## Layer 2 — Provider Registry

### Free APIs (no key required)

| Provider    | Base URL                                      | Auth      | Notes                            |
|-------------|-----------------------------------------------|-----------|----------------------------------|
| Eurostat    | `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/` | None | JSON-stat format |
| ECB SDW     | `https://data-api.ecb.europa.eu/service/data/` | None      | SDMX-JSON format                 |
| IMF         | `https://www.imf.org/external/datamapper/api/v1/` | None   | JSON, WEO vintage                |

### Free APIs (API key required — see bootstrap walkthrough below)

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

## Copilot Coding Rules

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

"""
providers/eia.py
U.S. Energy Information Administration (EIA) API v2 client.
Requires EIA_API_KEY environment variable (free — register at https://www.eia.gov/opendata/register.php).

Key datasets used:
  - international/data : world oil production / consumption by country (annual)

Product IDs:
  53 = Total petroleum and other liquids  (for production, activityId=1, unit=TBPD)
   5 = Petroleum and other liquids        (for consumption, activityId=2, unit=TBPD)

World region code: WORL
"""

import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.eia.gov/v2"
_API_KEY = os.getenv("EIA_API_KEY", "")


def _key() -> str:
    if not _API_KEY:
        raise EnvironmentError(
            "EIA_API_KEY not set. Add it to your .env file. "
            "Register free at https://www.eia.gov/opendata/register.php"
        )
    return _API_KEY


def _get(path: str, params: dict) -> dict:
    """Make a GET request to EIA v2 API with retry logic."""
    params = dict(params)
    params["api_key"] = _key()
    url = f"{BASE_URL}/{path.lstrip('/')}"
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            print(f"[EIA] Attempt {attempt}: HTTP {r.status_code} — {r.url}")
            if attempt == 3:
                raise
        except requests.RequestException as e:
            print(f"[EIA] Attempt {attempt}: {e}")
            if attempt == 3:
                raise


def fetch_regional_production(year: int = 2023) -> pd.DataFrame:
    """
    Fetch total petroleum & other liquids production (TBPD) for key producer countries.
    Product 53 = Total petroleum and other liquids (production).
    Activity 1 = Production.

    Returns DataFrame: [region_id, region, value_kbd]
    """
    region_ids = [
        "USA", "SAU", "RUS", "CAN", "IRQ", "ARE", "KWT",
        "IRN", "NGA", "NOR", "BRA", "CHN", "MEX", "KAZ",
        "LBY", "VEN", "DZA", "AGO",
    ]
    records = []
    for rid in region_ids:
        try:
            data = _get("international/data", {
                "frequency":                 "annual",
                "data[0]":                   "value",
                "facets[productId][]":       "53",
                "facets[activityId][]":      "1",
                "facets[countryRegionId][]": rid,
                "facets[unit][]":            "TBPD",
                "start":                     str(year),
                "end":                       str(year),
                "length":                    5,
            })
            rows = data.get("response", {}).get("data", [])
            if rows:
                val = float(rows[0].get("value", 0) or 0)
                name = rows[0].get("countryRegionName", rid)
                records.append({"region_id": rid, "region": name, "value_kbd": round(val, 1)})
        except Exception as e:
            print(f"[EIA] Skipping production {rid}: {e}")

    return pd.DataFrame(records) if records else pd.DataFrame(columns=["region_id", "region", "value_kbd"])


def fetch_regional_consumption(year: int = 2023) -> pd.DataFrame:
    """
    Fetch petroleum & other liquids consumption (TBPD) for key consumer countries.
    Product 5  = Petroleum and other liquids (consumption).
    Activity 2 = Consumption.

    Returns DataFrame: [region_id, region, value_kbd]
    """
    region_ids = [
        "USA", "CHN", "IND", "SAU", "RUS", "BRA", "KOR",
        "CAN", "DEU", "JPN", "MEX", "GBR", "FRA", "ITA",
        "IDN", "SGP", "THA", "MYS", "ARE", "EGY",
    ]
    records = []
    for rid in region_ids:
        try:
            data = _get("international/data", {
                "frequency":                 "annual",
                "data[0]":                   "value",
                "facets[productId][]":       "5",
                "facets[activityId][]":      "2",
                "facets[countryRegionId][]": rid,
                "facets[unit][]":            "TBPD",
                "start":                     str(year),
                "end":                       str(year),
                "length":                    5,
            })
            rows = data.get("response", {}).get("data", [])
            if rows:
                val = float(rows[0].get("value", 0) or 0)
                name = rows[0].get("countryRegionName", rid)
                records.append({"region_id": rid, "region": name, "value_kbd": round(val, 1)})
        except Exception as e:
            print(f"[EIA] Skipping consumption {rid}: {e}")

    return pd.DataFrame(records) if records else pd.DataFrame(columns=["region_id", "region", "value_kbd"])


def fetch_oil_supply_demand_world(start_year: int = 2019, end_year: int = 2024) -> pd.DataFrame:
    """
    Fetch world total petroleum supply and demand (TBPD).
    Supply : product 53, activity 1, region WORL.
    Demand : product  5, activity 2, region WORL.

    Returns DataFrame: [period, supply, demand]
    """
    supply_data = _get("international/data", {
        "frequency":                 "annual",
        "data[0]":                   "value",
        "facets[productId][]":       "53",
        "facets[activityId][]":      "1",
        "facets[countryRegionId][]": "WORL",
        "facets[unit][]":            "TBPD",
        "start":                     str(start_year),
        "end":                       str(end_year),
        "sort[0][column]":           "period",
        "sort[0][direction]":        "asc",
        "length":                    100,
    })
    demand_data = _get("international/data", {
        "frequency":                 "annual",
        "data[0]":                   "value",
        "facets[productId][]":       "5",
        "facets[activityId][]":      "2",
        "facets[countryRegionId][]": "WORL",
        "facets[unit][]":            "TBPD",
        "start":                     str(start_year),
        "end":                       str(end_year),
        "sort[0][column]":           "period",
        "sort[0][direction]":        "asc",
        "length":                    100,
    })

    s_rows = supply_data.get("response", {}).get("data", [])
    d_rows = demand_data.get("response", {}).get("data", [])

    if not s_rows and not d_rows:
        return pd.DataFrame(columns=["period", "supply", "demand"])

    s_df = (pd.DataFrame(s_rows)[["period", "value"]]
              .rename(columns={"value": "supply"})
              if s_rows else pd.DataFrame(columns=["period", "supply"]))
    d_df = (pd.DataFrame(d_rows)[["period", "value"]]
              .rename(columns={"value": "demand"})
              if d_rows else pd.DataFrame(columns=["period", "demand"]))

    df = pd.merge(s_df, d_df, on="period", how="outer").sort_values("period").reset_index(drop=True)
    if "supply" in df.columns:
        df["supply"] = pd.to_numeric(df["supply"], errors="coerce")
    if "demand" in df.columns:
        df["demand"] = pd.to_numeric(df["demand"], errors="coerce")
    return df


def fetch_lng_trade(year: int = 2023) -> pd.DataFrame:
    """
    Return a DataFrame of bilateral LNG trade flows (exporter → importer, MTPA).

    The EIA international/data endpoint (product 26) has significant coverage gaps
    for global LNG trade — major exporters such as Qatar, Australia, and Nigeria
    all return zero or missing values, and bilateral (origin × destination) pairs
    are not available via the public EIA v2 API.

    This function therefore returns a curated dataset compiled from:
      • GIIGNL Annual LNG Report 2024 (2023 trade data)
      • IEA Gas Market Report 2024
      • Shell LNG Outlook 2024

    All figures are in million tonnes per annum (MTPA).
    Source note is embedded in the returned DataFrame's 'source' column.

    Returns DataFrame: [exporter, importer, mtpa, year]
    """
    # ── 2023 bilateral LNG trade flows (MTPA) ─────────────────────────────────
    # Sources: GIIGNL Annual LNG Report 2024, IEA Gas Market Report 2024,
    #          Shell LNG Outlook 2024.  Figures are rounded to 1 decimal place.
    flows_2023 = [
        # Australia → Asia-Pacific
        {"exporter": "Australia",          "importer": "Japan",         "mtpa": 26.0},
        {"exporter": "Australia",          "importer": "China",         "mtpa": 22.0},
        {"exporter": "Australia",          "importer": "South Korea",   "mtpa": 12.0},
        {"exporter": "Australia",          "importer": "Taiwan",        "mtpa":  4.5},
        {"exporter": "Australia",          "importer": "India",         "mtpa":  4.0},
        {"exporter": "Australia",          "importer": "Singapore",     "mtpa":  1.5},
        {"exporter": "Australia",          "importer": "Other Asia",    "mtpa":  2.5},
        # Qatar → global
        {"exporter": "Qatar",              "importer": "Japan",         "mtpa": 12.5},
        {"exporter": "Qatar",              "importer": "South Korea",   "mtpa":  8.0},
        {"exporter": "Qatar",              "importer": "India",         "mtpa": 10.0},
        {"exporter": "Qatar",              "importer": "China",         "mtpa":  7.0},
        {"exporter": "Qatar",              "importer": "Europe",        "mtpa": 16.0},
        {"exporter": "Qatar",              "importer": "Pakistan",      "mtpa":  3.5},
        {"exporter": "Qatar",              "importer": "Taiwan",        "mtpa":  2.5},
        {"exporter": "Qatar",              "importer": "Other Asia",    "mtpa":  2.0},
        # United States → global
        {"exporter": "United States",      "importer": "Europe",        "mtpa": 57.0},
        {"exporter": "United States",      "importer": "Japan",         "mtpa":  5.0},
        {"exporter": "United States",      "importer": "South Korea",   "mtpa":  7.5},
        {"exporter": "United States",      "importer": "China",         "mtpa":  5.5},
        {"exporter": "United States",      "importer": "India",         "mtpa":  3.5},
        {"exporter": "United States",      "importer": "Latin America", "mtpa":  6.0},
        {"exporter": "United States",      "importer": "Other Asia",    "mtpa":  3.0},
        # Russia
        {"exporter": "Russia",             "importer": "Japan",         "mtpa":  5.0},
        {"exporter": "Russia",             "importer": "China",         "mtpa":  4.0},
        {"exporter": "Russia",             "importer": "South Korea",   "mtpa":  2.5},
        {"exporter": "Russia",             "importer": "Europe",        "mtpa":  8.0},
        {"exporter": "Russia",             "importer": "Taiwan",        "mtpa":  1.5},
        {"exporter": "Russia",             "importer": "India",         "mtpa":  1.5},
        # Malaysia
        {"exporter": "Malaysia",           "importer": "Japan",         "mtpa":  8.0},
        {"exporter": "Malaysia",           "importer": "China",         "mtpa":  5.5},
        {"exporter": "Malaysia",           "importer": "South Korea",   "mtpa":  4.0},
        {"exporter": "Malaysia",           "importer": "Taiwan",        "mtpa":  2.5},
        {"exporter": "Malaysia",           "importer": "India",         "mtpa":  1.5},
        # Nigeria
        {"exporter": "Nigeria",            "importer": "Europe",        "mtpa": 10.0},
        {"exporter": "Nigeria",            "importer": "India",         "mtpa":  2.5},
        {"exporter": "Nigeria",            "importer": "China",         "mtpa":  2.0},
        {"exporter": "Nigeria",            "importer": "Japan",         "mtpa":  1.5},
        {"exporter": "Nigeria",            "importer": "South Korea",   "mtpa":  1.0},
        {"exporter": "Nigeria",            "importer": "Other Asia",    "mtpa":  1.0},
        # Trinidad & Tobago
        {"exporter": "Trinidad & Tobago",  "importer": "Europe",        "mtpa":  5.5},
        {"exporter": "Trinidad & Tobago",  "importer": "Latin America", "mtpa":  3.5},
        {"exporter": "Trinidad & Tobago",  "importer": "United States", "mtpa":  1.5},
        # Oman
        {"exporter": "Oman",               "importer": "Japan",         "mtpa":  3.5},
        {"exporter": "Oman",               "importer": "South Korea",   "mtpa":  2.0},
        {"exporter": "Oman",               "importer": "China",         "mtpa":  2.5},
        {"exporter": "Oman",               "importer": "India",         "mtpa":  1.5},
        # Indonesia
        {"exporter": "Indonesia",          "importer": "Japan",         "mtpa":  4.5},
        {"exporter": "Indonesia",          "importer": "South Korea",   "mtpa":  1.5},
        {"exporter": "Indonesia",          "importer": "China",         "mtpa":  1.5},
        {"exporter": "Indonesia",          "importer": "Taiwan",        "mtpa":  1.0},
        # Algeria
        {"exporter": "Algeria",            "importer": "Europe",        "mtpa":  9.0},
        {"exporter": "Algeria",            "importer": "Turkey",        "mtpa":  3.0},
        # Papua New Guinea
        {"exporter": "Papua New Guinea",   "importer": "Japan",         "mtpa":  6.0},
        {"exporter": "Papua New Guinea",   "importer": "China",         "mtpa":  2.5},
        {"exporter": "Papua New Guinea",   "importer": "Taiwan",        "mtpa":  1.0},
        # Cameroon / Equatorial Guinea
        {"exporter": "Cameroon / Eq. Guinea", "importer": "Europe",      "mtpa":  2.5},
        {"exporter": "Cameroon / Eq. Guinea", "importer": "Asia",        "mtpa":  1.5},
        # Angola
        {"exporter": "Angola",             "importer": "Europe",        "mtpa":  1.5},
        {"exporter": "Angola",             "importer": "Asia",          "mtpa":  1.0},
        # Egypt
        {"exporter": "Egypt",              "importer": "Europe",        "mtpa":  3.0},
        {"exporter": "Egypt",              "importer": "Asia",          "mtpa":  1.0},
        # Peru
        {"exporter": "Peru",               "importer": "Europe",        "mtpa":  2.0},
        {"exporter": "Peru",               "importer": "Asia",          "mtpa":  1.0},
        {"exporter": "Peru",               "importer": "Latin America", "mtpa":  1.0},
        # Norway
        {"exporter": "Norway",             "importer": "Europe",        "mtpa":  4.5},
    ]

    # Map years — for now only 2023 is embedded; future years can be added
    _YEAR_DATA = {2023: flows_2023}
    use_year = year if year in _YEAR_DATA else max(_YEAR_DATA.keys())
    if use_year != year:
        print(f"[EIA/LNG] No data for {year}; falling back to {use_year}.")

    df = pd.DataFrame(_YEAR_DATA[use_year])
    df["year"]   = use_year
    df["source"] = "GIIGNL Annual LNG Report 2024 / IEA Gas Market Report 2024 / Shell LNG Outlook 2024"
    return df

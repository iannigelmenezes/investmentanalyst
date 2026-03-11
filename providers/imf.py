"""
providers/imf.py
IMF DataMapper API client — used for Japan CPI and other WEO series.
No API key required.
"""

import requests
import pandas as pd

BASE_URL = "https://www.imf.org/external/datamapper/api/v1/"


def fetch_indicator(indicator: str, countries: list, start_year: int = None, end_year: int = None) -> pd.DataFrame:
    """
    Fetch an IMF WEO indicator for a list of ISO country codes.

    Args:
        indicator   : e.g. "PCPIPCH" (CPI inflation, average consumer prices, % change)
        countries   : list of ISO2/ISO3 codes, e.g. ["JPN", "USA"]
        start_year  : optional
        end_year    : optional

    Returns:
        DataFrame with columns: [country, year, value]
    """
    # IMF DataMapper: countries go in the URL path; periods param is not supported
    country_path = "/".join(countries) if countries else ""
    url = f"{BASE_URL}{indicator}/{country_path}" if country_path else f"{BASE_URL}{indicator}"
    params = {}  # no query params needed

    for attempt in range(1, 4):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            break
        except requests.HTTPError as e:
            print(f"[IMF] Attempt {attempt}: {e} — URL: {response.url} — Status: {response.status_code}")
            if attempt == 3:
                raise
        except requests.RequestException as e:
            print(f"[IMF] Attempt {attempt}: {e}")
            if attempt == 3:
                raise

    data = response.json()
    values_block = data.get("values", {}).get(indicator, {})

    records = []
    for country, year_dict in values_block.items():
        for year, val in year_dict.items():
            records.append({"country": country, "year": int(year), "value": float(val) if val is not None else None})

    df = pd.DataFrame(records)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # Filter by year range in Python (API doesn't support periods param)
    if start_year:
        df = df[df["year"] >= start_year]
    if end_year:
        df = df[df["year"] <= end_year]

    return df

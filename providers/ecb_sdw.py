"""
providers/ecb_sdw.py
ECB Statistical Data Warehouse (SDW) client — SDMX-JSON format.
No API key required.
"""

import requests
import pandas as pd
from datetime import date, timedelta

BASE_URL = "https://data-api.ecb.europa.eu/service/data/"

# Tenor code → human-readable label and approximate years
TENOR_MAP = {
    "SR_3M":  ("3M",   0.25),
    "SR_6M":  ("6M",   0.5),
    "SR_1Y":  ("1Y",   1.0),
    "SR_2Y":  ("2Y",   2.0),
    "SR_3Y":  ("3Y",   3.0),
    "SR_5Y":  ("5Y",   5.0),
    "SR_7Y":  ("7Y",   7.0),
    "SR_10Y": ("10Y", 10.0),
    "SR_15Y": ("15Y", 15.0),
    "SR_20Y": ("20Y", 20.0),
    "SR_30Y": ("30Y", 30.0),
}


def _fetch_series(flow_key: str, last_n: int = None,
                  start_period: str = None, end_period: str = None) -> pd.DataFrame:
    """
    Fetch a single ECB SDW series and return a tidy DataFrame [date, value].

    Args:
        flow_key     : e.g. "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
        last_n       : return only the last N observations
        start_period : "YYYY-MM-DD"
        end_period   : "YYYY-MM-DD"

    Returns:
        DataFrame with columns: [date, value]
    """
    url = f"{BASE_URL}{flow_key}"
    params = {"format": "jsondata"}
    if last_n:
        params["lastNObservations"] = last_n
    if start_period:
        params["startPeriod"] = start_period
    if end_period:
        params["endPeriod"] = end_period

    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            break
        except requests.HTTPError as e:
            print(f"[ECB SDW] Attempt {attempt}: HTTP {r.status_code} — {url}")
            if attempt == 3:
                raise
        except requests.RequestException as e:
            print(f"[ECB SDW] Attempt {attempt}: {e}")
            if attempt == 3:
                raise

    data = r.json()
    datasets = data.get("dataSets", [])
    if not datasets:
        return pd.DataFrame(columns=["date", "value"])

    series_data = datasets[0].get("series", {})
    if not series_data:
        return pd.DataFrame(columns=["date", "value"])

    # Only one series key expected (0:0:0:...)
    series_key = list(series_data.keys())[0]
    observations = series_data[series_key].get("observations", {})

    # Time dimension
    time_vals = data["structure"]["dimensions"]["observation"][0]["values"]

    records = []
    for idx_str, obs in observations.items():
        idx = int(idx_str)
        date_str = time_vals[idx]["id"]
        value    = obs[0] if obs[0] is not None else None
        records.append({"date": pd.to_datetime(date_str), "value": value})

    df = pd.DataFrame(records).dropna(subset=["value"]).sort_values("date").reset_index(drop=True)
    return df


def fetch_yield_curve_snapshot(tenor_codes: list, as_of_date: str = None) -> dict:
    """
    Fetch a yield curve snapshot — one value per tenor — for a given date.
    Falls back to closest prior business day if exact date has no data.

    Args:
        tenor_codes : list of tenor codes, e.g. ["SR_3M","SR_2Y","SR_10Y"]
        as_of_date  : "YYYY-MM-DD" (default: today)

    Returns:
        dict: { tenor_code: float }  e.g. {"SR_10Y": 2.897}
    """
    if as_of_date is None:
        as_of_date = date.today().isoformat()

    # Fetch a small window around the target date to handle weekends/holidays
    target = pd.to_datetime(as_of_date)
    window_start = (target - pd.DateOffset(days=10)).strftime("%Y-%m-%d")

    results = {}
    for tenor in tenor_codes:
        key = f"YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{tenor}"
        try:
            df = _fetch_series(key, start_period=window_start, end_period=as_of_date)
            if not df.empty:
                results[tenor] = round(df.iloc[-1]["value"], 4)
            else:
                results[tenor] = None
        except Exception as e:
            print(f"[ECB SDW] Could not fetch {tenor}: {e}")
            results[tenor] = None

    return results


def fetch_yield_timeseries(tenor_code: str, start_period: str, end_period: str = None) -> pd.DataFrame:
    """
    Fetch a full time series for one tenor between two dates.

    Returns:
        DataFrame with columns: [date, value]
    """
    key = f"YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{tenor_code}"
    return _fetch_series(key, start_period=start_period, end_period=end_period)

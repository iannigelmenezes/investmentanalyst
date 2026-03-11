"""
providers/fred.py
FRED (Federal Reserve Bank of St. Louis) API client.
Requires FRED_API_KEY environment variable (optional — degraded gracefully).
"""

import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_KEY = os.getenv("FRED_API_KEY", "")


def fetch_series(series_id: str, observation_start: str = None,
                 observation_end: str = None, units: str = "lin") -> pd.DataFrame:
    """
    Fetch a FRED series and return a tidy DataFrame.

    Args:
        series_id         : e.g. "CPIAUCSL"
        observation_start : "YYYY-MM-DD" (optional)
        observation_end   : "YYYY-MM-DD" (optional)
        units             : "lin" (levels) | "pc1" (YoY % change) | "pch" (MoM % change)

    Returns:
        DataFrame with columns: [date, value]
    """
    if not FRED_KEY:
        raise EnvironmentError(
            "FRED_API_KEY not set. Add it to a .env file or environment variables. "
            "Register free at https://fredaccount.stlouisfed.org/"
        )

    params = {
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "units": units,
    }
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end

    for attempt in range(1, 4):
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            break
        except requests.HTTPError as e:
            print(f"[FRED] Attempt {attempt}: {e} — URL: {response.url} — Status: {response.status_code}")
            if attempt == 3:
                raise
        except requests.RequestException as e:
            print(f"[FRED] Attempt {attempt}: {e}")
            if attempt == 3:
                raise

    obs = response.json().get("observations", [])
    df = pd.DataFrame(obs)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    return df

"""
providers/eurostat.py
Eurostat REST API client — JSON-stat format parser.
"""

import requests
import pandas as pd
from itertools import product

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


def fetch(dataset_id: str, params: dict) -> pd.DataFrame:
    """
    Fetch a Eurostat dataset and return as a tidy DataFrame.

    Args:
        dataset_id : e.g. "prc_hicp_manr"
        params     : filter dict e.g. {"geo": "EA", "unit": "RCH_A", "coicop": "CP00"}

    Returns:
        DataFrame with columns derived from dimensions, last column is 'value'
    """
    url = f"{BASE_URL}{dataset_id}"
    req_params = dict(params)
    req_params["format"] = "JSON"
    req_params["lang"] = "EN"

    for attempt in range(1, 4):
        try:
            response = requests.get(url, params=req_params, timeout=30)
            response.raise_for_status()
            break
        except requests.HTTPError as e:
            print(f"[Eurostat] Attempt {attempt}: {e} — URL: {response.url}")
            if attempt == 3:
                raise
        except requests.RequestException as e:
            print(f"[Eurostat] Attempt {attempt}: {e}")
            if attempt == 3:
                raise

    data = response.json()

    # --- Parse JSON-stat ---
    # dimensions: ordered list of dimension names
    dimension_ids = data["id"]          # e.g. ["freq","unit","coicop","geo","time"]
    dimension_sizes = data["size"]      # e.g. [1, 1, 1, 3, 60]
    dimensions = data["dimension"]

    # Build label lists for each dimension
    dim_labels = []
    for dim_id in dimension_ids:
        category = dimensions[dim_id]["category"]
        # "index" may be a dict {label: position} or list; normalise to ordered list
        index_map = category.get("index", {})
        label_map = category.get("label", {})
        if isinstance(index_map, dict):
            ordered_keys = sorted(index_map, key=lambda k: index_map[k])
        else:
            ordered_keys = list(label_map.keys())
        # Use human-readable labels where available
        ordered_labels = [label_map.get(k, k) for k in ordered_keys]
        dim_labels.append(ordered_labels)

    # Cartesian product of all dimension labels → row index
    rows = list(product(*dim_labels))
    flat_values = data.get("value", {})

    records = []
    for i, row in enumerate(rows):
        val = flat_values.get(str(i), flat_values.get(i, None))
        records.append((*row, val))

    col_names = dimension_ids + ["value"]
    df = pd.DataFrame(records, columns=col_names)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    return df

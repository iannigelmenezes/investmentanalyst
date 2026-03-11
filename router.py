"""
router.py
Intent classifier and dispatcher.
"""

import importlib
import re

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

HANDLER_MAP = {
    "MACRO_INDICATOR": "intents.macro_indicator",
    "CROSS_SECTION":   "intents.cross_section",
    "ISSUANCE":        "intents.issuance",
    "FLOW_MAP":        "intents.flow_map",
    "RATES_CURVE":     "intents.rates_curve",
    "RELATIVE_VALUE":  "intents.relative_value",
}

GEOGRAPHY_ALIASES = {
    "eurozone": "EA", "euro area": "EA", "euro zone": "EA", "ez": "EA",
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
    "netherlands": "NL", "usa": "US", "united states": "US", "japan": "JP",
}

METRIC_ALIASES = {
    "inflation": "hicp", "cpi": "cpi", "hicp": "hicp",
    "gdp": "gdp", "growth": "gdp",
    "unemployment": "unemployment",
    "debt": "debt_gdp", "debt-to-gdp": "debt_gdp",
}


def classify(query: str) -> str:
    """Return the best-matching intent ID for a natural language query."""
    q = query.lower()
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                scores[intent] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "UNKNOWN"


def extract_params(query: str, intent: str) -> dict:
    """Extract geography, metric, time horizon from the query string."""
    q = query.lower()
    params = {}

    # Geography
    for alias, code in GEOGRAPHY_ALIASES.items():
        if alias in q:
            params["geography"] = code
            break

    # Metric
    for alias, canonical in METRIC_ALIASES.items():
        if alias in q:
            params["metric"] = canonical
            break

    # Time horizon (e.g. "last 10 years", "5y", "3 years")
    m = re.search(r"(\d+)\s*(?:y(?:ear)?s?|yr)", q)
    if m:
        params["years"] = int(m.group(1))

    return params


def dispatch(query: str):
    """Classify query, extract params, build reasoning trace, call correct handler."""
    intent = classify(query)
    print(f"[Router] Intent: {intent} | Query: \"{query}\"")

    if intent == "UNKNOWN":
        print("❓ Could not classify this query. Please rephrase using one of these intents:")
        for k in INTENT_KEYWORDS:
            print(f"   • {k}")
        return

    params = extract_params(query, intent)
    print(f"[Router] Params: {params}")

    # ── Build reasoning trace for the report ────────────────────────────────
    # Which keywords triggered the intent?
    matched_kws = [kw for kw in INTENT_KEYWORDS[intent] if kw in query.lower()]

    # Which provider will be used (primary)?
    provider_map = {
        "MACRO_INDICATOR": "Eurostat (primary) → FRED / IMF (comparators)",
        "CROSS_SECTION":   "Eurostat / IMF WEO",
        "ISSUANCE":        "ECB SDW + individual DMO websites",
        "FLOW_MAP":        "IEA / Eurostat energy datasets",
        "RATES_CURVE":     "ECB Statistical Data Warehouse (SDW)",
        "RELATIVE_VALUE":  "ECB SDW + FRED",
    }
    geo_detected  = params.get("geography", "EA (default)")
    metric_detect = params.get("metric", "hicp (default)")
    years_detect  = params.get("years", 5)

    reasoning = [
        {
            "step": "Query received",
            "detail": f'<strong>"{query}"</strong>',
        },
        {
            "step": "Intent classified",
            "detail": (
                f"<strong>{intent}</strong> — "
                f"matched keyword(s): <em>{', '.join(matched_kws) if matched_kws else 'best match'}</em>"
            ),
        },
        {
            "step": "Parameters extracted",
            "detail": (
                f"Geography: <strong>{geo_detected}</strong> &nbsp;|&nbsp; "
                f"Metric: <strong>{metric_detect}</strong> &nbsp;|&nbsp; "
                f"Time horizon: <strong>{years_detect}y</strong>"
            ),
        },
        {
            "step": "Data source selected",
            "detail": provider_map.get(intent, "—"),
        },
        {
            "step": "Comparators selected",
            "detail": "United States (FRED → IMF fallback) &nbsp;&amp;&nbsp; Japan (FRED → IMF fallback)",
        },
    ]

    params["_query"]     = query
    params["_intent"]    = intent
    params["_reasoning"] = reasoning

    module_path = HANDLER_MAP.get(intent)
    if not module_path:
        print(f"[Router] No handler registered for intent: {intent}")
        return

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        print(f"[Router] Handler module '{module_path}' not found. Creating it is required.")
        raise

    if not hasattr(module, "run"):
        print(f"[Router] Handler module '{module_path}' has no run() function.")
        return

    return module.run(params)

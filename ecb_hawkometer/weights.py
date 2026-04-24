"""
ecb_hawkometer/weights.py
-------------------------
Static speaker weight registry for ECB policy prediction.
Higher weight = more influential for rate decision forecasting.
"""

# Tier weights for policy prediction (higher = more influential)
SPEAKER_WEIGHTS = {
    # Tier 1 — President / Chief Economist (weight 1.0)
    "Christine Lagarde": 1.0,
    "Philip Lane": 1.0,
    # Tier 2 — Executive Board (weight 0.8)
    "Isabel Schnabel": 0.8,
    "Luis de Guindos": 0.8,
    "Piero Cipollone": 0.8,
    "Frank Elderson": 0.8,
    # Tier 3 — Major NCB Governors (weight 0.6)
    "Joachim Nagel": 0.6,
    "François Villeroy de Galhau": 0.6,
    "Klaas Knot": 0.6,
    "Pierre Wunsch": 0.6,
    "Mario Centeno": 0.6,
    "Yannis Stournaras": 0.6,
}

DEFAULT_WEIGHT = 0.4  # Tier 4 — all other NCB governors

# Map tier boundaries by weight
_TIER_THRESHOLDS = [
    (1.0, 1),
    (0.8, 2),
    (0.6, 3),
]


def get_weight(speaker_name: str) -> float:
    """Return the influence weight for a speaker. Defaults to 0.4 if unknown.

    Tries exact match first, then case-insensitive partial match.
    """
    # Exact match
    if speaker_name in SPEAKER_WEIGHTS:
        return SPEAKER_WEIGHTS[speaker_name]

    # Reject empty or whitespace-only names before partial matching
    stripped = speaker_name.strip()
    if not stripped:
        return DEFAULT_WEIGHT

    # Case-insensitive partial match (substring in either direction)
    lower_query = stripped.lower()
    for known_name, weight in SPEAKER_WEIGHTS.items():
        if lower_query in known_name.lower() or known_name.lower() in lower_query:
            return weight

    return DEFAULT_WEIGHT


def get_tier(speaker_name: str) -> int:
    """Return tier 1-4 for a speaker.

    Tier 1 = President / Chief Economist (weight 1.0)
    Tier 2 = Executive Board (weight 0.8)
    Tier 3 = Major NCB Governors (weight 0.6)
    Tier 4 = All other NCB governors (weight 0.4)
    """
    weight = get_weight(speaker_name)
    for threshold, tier in _TIER_THRESHOLDS:
        if weight >= threshold:
            return tier
    return 4

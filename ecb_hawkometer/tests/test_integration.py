"""
ecb_hawkometer/tests/test_integration.py
Integration tests for the ECB Hawkometer router wiring (F6).
"""

import sys
import os
from unittest.mock import patch, MagicMock

# Ensure workspace root is on the path so router and intents are importable
_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)

import pytest


# ---------------------------------------------------------------------------
# Tests 1–3: Router classification
# ---------------------------------------------------------------------------

def test_router_classifies_trigger_phrase():
    from router import classify
    assert classify("show me the ECB speaker dashboard") == "ECB_HAWKOMETER"


def test_router_classifies_hawkometer():
    from router import classify
    assert classify("hawkometer") == "ECB_HAWKOMETER"


def test_router_classifies_ecb_speakers():
    from router import classify
    assert classify("ecb speakers hawkishness") == "ECB_HAWKOMETER"


# ---------------------------------------------------------------------------
# Tests 4–5: Importability
# ---------------------------------------------------------------------------

def test_intent_handler_importable():
    from intents.ecb_hawkometer import run  # noqa: F401


def test_pipeline_module_importable():
    from ecb_hawkometer.main import run_pipeline  # noqa: F401


# ---------------------------------------------------------------------------
# Test 6: Pipeline with mocked empty DB exits gracefully
# ---------------------------------------------------------------------------

def test_pipeline_runs_with_empty_db(capsys):
    """run_pipeline() should print a warning and return without crashing when
    no recent speeches are found in the database."""

    with patch("ecb_hawkometer.main.db") as mock_db, \
         patch("ecb_hawkometer.main.scraper") as mock_scraper, \
         patch("ecb_hawkometer.main.analyzer") as mock_analyzer, \
         patch("ecb_hawkometer.main.dashboard") as mock_dashboard:

        # Stub out DB / scraper so no real I/O happens
        mock_db.init_db.return_value = None
        mock_db.get_existing_urls.return_value = set()
        mock_scraper.scrape_speeches.return_value = []
        mock_db.get_speeches.return_value = []   # empty — triggers early exit

        from ecb_hawkometer.main import run_pipeline
        # Must not raise
        run_pipeline()

    captured = capsys.readouterr()
    # The warning message should appear in stdout
    assert "No recent speeches found" in captured.out

    # analyzer and dashboard must NOT have been called (early return)
    mock_analyzer.get_speaker_scores.assert_not_called()
    mock_analyzer.get_policy_prediction.assert_not_called()
    mock_dashboard.generate_dashboard.assert_not_called()

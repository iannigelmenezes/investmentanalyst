"""
ecb_hawkometer/tests/test_dashboard.py
---------------------------------------
Tests for F5: dashboard.py

All tests use mock data — no real DB or analyzer calls needed.
webbrowser.open is always patched to prevent browser launches.
"""

from __future__ import annotations

import os
import re
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_SCORES = [
    {
        "speaker": "Christine Lagarde",
        "hawkishness_score": 4.5,
        "trend": "stable",
        "key_themes": ["data dependency", "inflation"],
        "tone_summary": "Cautious tone.",
        "representative_quote": "We remain data dependent.",
    },
    {
        "speaker": "Isabel Schnabel",
        "hawkishness_score": 7.2,
        "trend": "increasing",
        "key_themes": ["wage growth", "services inflation"],
        "tone_summary": "Hawkish shift.",
        "representative_quote": "Inflation risks remain to the upside.",
    },
]

MOCK_PREDICTION = {
    "prediction": "hold",
    "confidence": "medium",
    "next_meeting_date": "2025-06-05",
    "weighted_score": 5.8,
    "rationale": "Mixed signals from the Governing Council.",
    "rubric": [
        {
            "factor": "Schnabel tone",
            "direction": "hawkish",
            "weight_applied": 0.8,
            "evidence": "Quote cited",
        }
    ],
}

MOCK_SPEECHES = [
    {
        "speaker": "Christine Lagarde",
        "date": "2025-03-01",
        "title": "Opening remarks",
        "url": "https://ecb.europa.eu/1",
    },
    {
        "speaker": "Isabel Schnabel",
        "date": "2025-03-10",
        "title": "Inflation dynamics",
        "url": "https://ecb.europa.eu/2",
    },
]


# ---------------------------------------------------------------------------
# Fixture: generate once per test module, with webbrowser patched
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dashboard_path():
    """Call generate_dashboard() with mocked webbrowser; return output path."""
    with patch("webbrowser.open") as _mock_wb:
        from ecb_hawkometer.dashboard import generate_dashboard
        path = generate_dashboard(MOCK_SCORES, MOCK_PREDICTION, MOCK_SPEECHES)
    return path


@pytest.fixture(scope="module")
def dashboard_html(dashboard_path):
    """Read the generated HTML content."""
    with open(dashboard_path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Test 1 — File exists
# ---------------------------------------------------------------------------

class TestGeneratesHtmlFile:
    def test_generates_html_file(self, dashboard_path):
        """generate_dashboard() must return a path to an existing file."""
        assert os.path.isabs(dashboard_path), "Returned path should be absolute"
        assert os.path.isfile(dashboard_path), f"File not found: {dashboard_path}"
        assert dashboard_path.endswith(".html"), "File must have .html extension"


# ---------------------------------------------------------------------------
# Test 2 — Self-contained (no external resources)
# ---------------------------------------------------------------------------

class TestHtmlIsSelfContained:
    def test_html_is_self_contained(self, dashboard_html):
        """HTML must not reference external resources via link, script src, or img src."""
        # Patterns that indicate external resource loading
        bad_patterns = [
            r'<link[^>]+href=["\']https?://',
            r'<script[^>]+src=["\']https?://',
            r'<img[^>]+src=["\']https?://',
        ]
        for pattern in bad_patterns:
            match = re.search(pattern, dashboard_html, re.IGNORECASE)
            assert match is None, (
                f"External resource reference found: {match.group() if match else ''}"
            )


# ---------------------------------------------------------------------------
# Test 3 — Verdict present
# ---------------------------------------------------------------------------

class TestContainsVerdict:
    def test_contains_verdict(self, dashboard_html):
        """HTML must contain the prediction verdict in uppercase."""
        verdict = MOCK_PREDICTION["prediction"].upper()
        assert verdict in dashboard_html, (
            f"Expected verdict '{verdict}' not found in dashboard HTML"
        )


# ---------------------------------------------------------------------------
# Test 4 — Speaker names present
# ---------------------------------------------------------------------------

class TestContainsSpeakerNames:
    def test_contains_all_speaker_names(self, dashboard_html):
        """HTML must contain every speaker name from the input data."""
        for speaker_data in MOCK_SCORES:
            name = speaker_data["speaker"]
            assert name in dashboard_html, (
                f"Speaker '{name}' not found in dashboard HTML"
            )


# ---------------------------------------------------------------------------
# Test 5 — Key themes present
# ---------------------------------------------------------------------------

class TestContainsKeyThemes:
    def test_contains_key_themes(self, dashboard_html):
        """HTML must contain key themes from the input data."""
        assert "data dependency" in dashboard_html, (
            "Expected theme 'data dependency' not found in dashboard HTML"
        )


# ---------------------------------------------------------------------------
# Test 6 — webbrowser.open called once
# ---------------------------------------------------------------------------

class TestNoBrowserOpenInTest:
    def test_no_browser_open_in_test(self):
        """webbrowser.open must be called exactly once during generate_dashboard()."""
        with patch("webbrowser.open") as mock_wb:
            from ecb_hawkometer.dashboard import generate_dashboard
            generate_dashboard(MOCK_SCORES, MOCK_PREDICTION, MOCK_SPEECHES)
        mock_wb.assert_called_once()

    def test_browser_open_uses_file_protocol(self):
        """webbrowser.open must be called with a file:// URL."""
        with patch("webbrowser.open") as mock_wb:
            from ecb_hawkometer.dashboard import generate_dashboard
            generate_dashboard(MOCK_SCORES, MOCK_PREDICTION, MOCK_SPEECHES)
        call_arg = mock_wb.call_args[0][0]
        assert call_arg.startswith("file://"), (
            f"Expected file:// URL, got: {call_arg}"
        )

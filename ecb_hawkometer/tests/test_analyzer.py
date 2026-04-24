"""
ecb_hawkometer/tests/test_analyzer.py
--------------------------------------
Tests for weights.py and analyzer.py (F4).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Weights tests
# ---------------------------------------------------------------------------

from ecb_hawkometer.weights import get_weight, get_tier, DEFAULT_WEIGHT


class TestGetWeight:
    def test_get_weight_known_speaker_lagarde(self):
        assert get_weight("Christine Lagarde") == 1.0

    def test_get_weight_known_speaker_schnabel(self):
        assert get_weight("Isabel Schnabel") == 0.8

    def test_get_weight_known_speaker_nagel(self):
        assert get_weight("Joachim Nagel") == 0.6

    def test_get_weight_unknown_speaker(self):
        assert get_weight("Mario Draghi") == DEFAULT_WEIGHT
        assert get_weight("") == DEFAULT_WEIGHT
        assert get_weight("Some Random NCB Governor") == DEFAULT_WEIGHT

    def test_get_weight_case_insensitive_partial_match(self):
        # "lagarde" should match "Christine Lagarde"
        assert get_weight("lagarde") == 1.0

    def test_get_weight_philip_lane(self):
        assert get_weight("Philip Lane") == 1.0

    def test_get_weight_luis_de_guindos(self):
        assert get_weight("Luis de Guindos") == 0.8


class TestGetTier:
    def test_lagarde_tier_1(self):
        assert get_tier("Christine Lagarde") == 1

    def test_lane_tier_1(self):
        assert get_tier("Philip Lane") == 1

    def test_schnabel_tier_2(self):
        assert get_tier("Isabel Schnabel") == 2

    def test_guindos_tier_2(self):
        assert get_tier("Luis de Guindos") == 2

    def test_nagel_tier_3(self):
        assert get_tier("Joachim Nagel") == 3

    def test_villeroy_tier_3(self):
        assert get_tier("François Villeroy de Galhau") == 3

    def test_unknown_tier_4(self):
        assert get_tier("Mario Draghi") == 4
        assert get_tier("Unknown Person") == 4


# ---------------------------------------------------------------------------
# Helpers for analyzer tests
# ---------------------------------------------------------------------------

def _make_recent_speech(speaker: str, days_ago: int = 7, index: int = 0) -> dict:
    """Return a mock speech dict dated `days_ago` days before today."""
    date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {
        "speaker": speaker,
        "date": date_str,
        "title": f"Test Speech {index} by {speaker}",
        "url": f"https://ecb.europa.eu/test/{speaker.replace(' ', '_')}_{index}",
        "full_text": (
            f"This is a test speech by {speaker}. " * 50  # ~50-word repetition
        ),
    }


def _make_old_speech(speaker: str) -> dict:
    """Return a speech older than 8 weeks (should be filtered out)."""
    date_str = (datetime.now() - timedelta(weeks=10)).strftime("%Y-%m-%d")
    return {
        "speaker": speaker,
        "date": date_str,
        "title": "Old Speech",
        "url": f"https://ecb.europa.eu/old/{speaker.replace(' ', '_')}",
        "full_text": "Old speech content.",
    }


# ---------------------------------------------------------------------------
# Analyzer tests
# ---------------------------------------------------------------------------

from ecb_hawkometer import analyzer


class TestBuildSpeakerPrompts:
    def test_build_speaker_prompts_writes_files(self, tmp_path):
        """Prompt files are created and contain the speaker name."""
        speeches = [
            _make_recent_speech("Christine Lagarde", days_ago=3, index=0),
            _make_recent_speech("Christine Lagarde", days_ago=10, index=1),
            _make_recent_speech("Isabel Schnabel", days_ago=5, index=0),
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        result_paths = analyzer.build_speaker_prompts(
            speeches,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        # Should produce one result path per unique speaker
        assert len(result_paths) == 2

        # All result paths should be inside results_dir
        for rp in result_paths:
            assert rp.startswith(results_dir)

        # Prompt files should exist in prompts_dir
        prompt_files = os.listdir(prompts_dir)
        assert len(prompt_files) == 2

        # Each prompt file should contain its speaker name
        for prompt_file in prompt_files:
            content = open(os.path.join(prompts_dir, prompt_file), encoding="utf-8").read()
            assert "TASK: ECB_SPEAKER_ANALYSIS" in content
            assert "SPEAKER:" in content

        # .pending marker files should exist in results_dir
        result_files = os.listdir(results_dir)
        pending_files = [f for f in result_files if f.endswith(".pending")]
        assert len(pending_files) == 2

    def test_build_speaker_prompts_filters_old_speeches(self, tmp_path):
        """Speeches older than 8 weeks are excluded."""
        speeches = [
            _make_recent_speech("Christine Lagarde", days_ago=3),
            _make_old_speech("Christine Lagarde"),
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        result_paths = analyzer.build_speaker_prompts(
            speeches,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        # Only the speaker with recent speeches should appear
        assert len(result_paths) == 1

    def test_build_speaker_prompts_no_recent_speeches(self, tmp_path):
        """Returns empty list when all speeches are older than 8 weeks."""
        speeches = [_make_old_speech("Christine Lagarde")]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        result_paths = analyzer.build_speaker_prompts(
            speeches,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )
        assert result_paths == []

    def test_build_speaker_prompts_truncates_to_5_speeches(self, tmp_path):
        """Only up to 5 most recent speeches per speaker are included."""
        speeches = [
            _make_recent_speech("Philip Lane", days_ago=i, index=i)
            for i in range(1, 8)  # 7 speeches
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        result_paths = analyzer.build_speaker_prompts(
            speeches,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        assert len(result_paths) == 1
        prompt_files = os.listdir(prompts_dir)
        content = open(os.path.join(prompts_dir, prompt_files[0]), encoding="utf-8").read()
        # SPEECH_COUNT should be 5, not 7
        assert "SPEECH_COUNT: 5" in content


class TestBuildPolicyPrompt:
    def test_build_policy_prompt_writes_file(self, tmp_path):
        """Policy prompt file is created with correct content."""
        speaker_scores = [
            {
                "speaker": "Christine Lagarde",
                "hawkishness_score": 7.5,
                "trend": "increasing",
                "key_themes": ["inflation", "rates"],
                "tone_summary": "Hawkish tone.",
                "representative_quote": "We must act.",
            },
            {
                "speaker": "Philip Lane",
                "hawkishness_score": 6.0,
                "trend": "stable",
                "key_themes": ["data-dependence"],
                "tone_summary": "Neutral tone.",
                "representative_quote": "Data will guide us.",
            },
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        result_path = analyzer.build_policy_prompt(
            speaker_scores,
            last_rate=4.25,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        # Result path is inside results_dir
        assert result_path.startswith(results_dir)
        assert result_path.endswith(".json")

        # Prompt file exists
        prompt_files = os.listdir(prompts_dir)
        assert len(prompt_files) == 1
        content = open(os.path.join(prompts_dir, prompt_files[0]), encoding="utf-8").read()

        assert "TASK: ECB_POLICY_PREDICTION" in content
        assert "LAST_KNOWN_RATE: 4.25" in content
        assert "Christine Lagarde" in content
        assert "Philip Lane" in content

        # Pending marker exists
        result_files = os.listdir(results_dir)
        pending_files = [f for f in result_files if f.endswith(".pending")]
        assert len(pending_files) == 1

    def test_build_policy_prompt_includes_weights(self, tmp_path):
        """Policy prompt includes speaker weights."""
        speaker_scores = [
            {"speaker": "Isabel Schnabel", "hawkishness_score": 8.0, "trend": "increasing"},
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        analyzer.build_policy_prompt(
            speaker_scores,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        prompt_files = os.listdir(prompts_dir)
        content = open(os.path.join(prompts_dir, prompt_files[0]), encoding="utf-8").read()
        # Weight for Schnabel is 0.8
        assert "weight=0.8" in content


class TestGetSpeakerScores:
    def test_get_speaker_scores_reads_result(self, tmp_path, capsys):
        """Pre-writing the result JSON bypasses polling; get_speaker_scores returns it."""
        speeches = [_make_recent_speech("Christine Lagarde", days_ago=5)]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")
        os.makedirs(prompts_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # First, build prompts to find out what result path will be used
        result_paths = analyzer.build_speaker_prompts(
            speeches,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )
        assert len(result_paths) == 1
        result_path = result_paths[0]

        # Pre-write the result JSON before polling starts
        expected_result = {
            "speaker": "Christine Lagarde",
            "hawkishness_score": 8.5,
            "trend": "increasing",
            "key_themes": ["inflation", "tightening", "data"],
            "tone_summary": "Very hawkish.",
            "representative_quote": "Inflation must be tamed.",
        }
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(expected_result, f)

        # Now call the high-level function with a short poll interval
        # We monkey-patch build_speaker_prompts so it returns the already-written paths
        original_build = analyzer.build_speaker_prompts

        def mock_build(db_speeches, **kwargs):
            return result_paths  # return already-known paths

        analyzer.build_speaker_prompts = mock_build
        try:
            scores = analyzer.get_speaker_scores(
                speeches,
                poll_interval=0.1,
                timeout=5.0,
                prompts_dir=prompts_dir,
                results_dir=results_dir,
            )
        finally:
            analyzer.build_speaker_prompts = original_build

        assert len(scores) == 1
        assert scores[0]["speaker"] == "Christine Lagarde"
        assert scores[0]["hawkishness_score"] == 8.5
        assert scores[0]["trend"] == "increasing"

        captured = capsys.readouterr()
        assert "[Analyzer]" in captured.out

    def test_get_speaker_scores_timeout(self, tmp_path, capsys):
        """If no result file appears within timeout, returns empty list with warning."""
        speeches = [_make_recent_speech("Philip Lane", days_ago=3)]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")

        # Use very short timeout so the test completes quickly
        scores = analyzer.get_speaker_scores(
            speeches,
            poll_interval=0.05,
            timeout=0.2,  # 200ms — result will never appear
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        assert scores == []

        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_get_speaker_scores_empty_speeches(self, tmp_path, capsys):
        """Empty speech list returns empty scores immediately."""
        scores = analyzer.get_speaker_scores(
            [],
            poll_interval=0.05,
            timeout=1.0,
            prompts_dir=str(tmp_path / "prompts"),
            results_dir=str(tmp_path / "results"),
        )
        assert scores == []


class TestGetPolicyPrediction:
    def test_get_policy_prediction_reads_result(self, tmp_path, capsys):
        """Pre-writing policy result JSON; get_policy_prediction returns it."""
        speaker_scores = [
            {"speaker": "Christine Lagarde", "hawkishness_score": 7.0, "trend": "stable"},
        ]

        prompts_dir = str(tmp_path / "prompts")
        results_dir = str(tmp_path / "results")
        os.makedirs(prompts_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)

        # Get the result path first
        result_path = analyzer.build_policy_prompt(
            speaker_scores,
            prompts_dir=prompts_dir,
            results_dir=results_dir,
        )

        expected = {
            "prediction": "hold",
            "confidence": "high",
            "next_meeting_date": "2026-04-17",
            "weighted_score": 7.0,
            "rationale": "Weighted scores suggest hold.",
            "rubric": [],
        }
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(expected, f)

        original_build = analyzer.build_policy_prompt

        def mock_build(scores, last_rate=4.25, **kwargs):
            return result_path

        analyzer.build_policy_prompt = mock_build
        try:
            prediction = analyzer.get_policy_prediction(
                speaker_scores,
                poll_interval=0.1,
                timeout=5.0,
                prompts_dir=prompts_dir,
                results_dir=results_dir,
            )
        finally:
            analyzer.build_policy_prompt = original_build

        assert prediction["prediction"] == "hold"
        assert prediction["confidence"] == "high"
        assert prediction["weighted_score"] == 7.0

    def test_get_policy_prediction_timeout(self, tmp_path, capsys):
        """Returns empty dict if no result appears within timeout."""
        speaker_scores = [
            {"speaker": "Philip Lane", "hawkishness_score": 5.0, "trend": "stable"},
        ]

        result = analyzer.get_policy_prediction(
            speaker_scores,
            poll_interval=0.05,
            timeout=0.2,
            prompts_dir=str(tmp_path / "prompts"),
            results_dir=str(tmp_path / "results"),
        )

        assert result == {}
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

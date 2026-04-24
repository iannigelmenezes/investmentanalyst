"""
ecb_hawkometer/tests/test_db.py
--------------------------------
Pytest tests for ecb_hawkometer/db.py.

All tests use a temporary SQLite database so the production DB is never touched.
The sentence-transformer model is mocked for tests 1-6 to avoid slow downloads;
test 7 uses the real model to verify the full embedding pipeline.
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# We import the module so we can patch its internals cleanly.
import ecb_hawkometer.db as db_module


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """
    Redirect all DB operations to a fresh temporary file for the duration of
    each test.  Resets the module-level connection between tests.
    """
    db_file = str(tmp_path / "test_speeches.db")
    with patch.object(db_module, "get_db_path", return_value=db_file):
        # Also reset lazy model singleton so tests are independent
        original_model = db_module._model
        db_module.init_db()
        yield db_file
        db_module._model = original_model


def _fake_encode(text, convert_to_numpy=True):
    """Return a deterministic 384-dim float32 array (all 0.5)."""
    return np.full(384, 0.5, dtype=np.float32)


def _mock_model():
    """Return a MagicMock SentenceTransformer that uses _fake_encode."""
    m = MagicMock()
    m.encode.side_effect = _fake_encode
    return m


SPEECH_A = {
    "speaker": "Christine Lagarde",
    "date": "2024-01-15",
    "title": "Monetary Policy in Uncertain Times",
    "url": "https://ecb.europa.eu/speeches/2024/speech_a.html",
    "full_text": "Inflation remains above target. The ECB will act decisively.",
}

SPEECH_B = {
    "speaker": "Philip Lane",
    "date": "2024-03-20",
    "title": "The Path to Price Stability",
    "url": "https://ecb.europa.eu/speeches/2024/speech_b.html",
    "full_text": "Wage growth has moderated. Rate cuts may be appropriate.",
}

SPEECH_C = {
    "speaker": "Christine Lagarde",
    "date": "2023-11-05",
    "title": "Annual ECB Forum",
    "url": "https://ecb.europa.eu/speeches/2023/speech_c.html",
    "full_text": "Structural shifts require vigilance.",
}


# ---------------------------------------------------------------------------
# Test 1 – init_db creates the speeches table
# ---------------------------------------------------------------------------

def test_init_creates_table(tmp_db):
    conn = sqlite3.connect(tmp_db)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='speeches'"
    )
    assert cur.fetchone() is not None, "speeches table should exist after init_db()"
    conn.close()


# ---------------------------------------------------------------------------
# Test 2 – upsert_and_retrieve
# ---------------------------------------------------------------------------

def test_upsert_and_retrieve(tmp_db):
    with patch.object(db_module, "_get_model", return_value=_mock_model()):
        with patch.object(db_module, "get_db_path", return_value=tmp_db):
            db_module.upsert_speech(SPEECH_A)
            results = db_module.get_speeches()

    assert len(results) == 1
    row = results[0]
    assert row["speaker"] == SPEECH_A["speaker"]
    assert row["title"] == SPEECH_A["title"]
    assert row["url"] == SPEECH_A["url"]
    assert row["date"] == SPEECH_A["date"]
    # embedding column must NOT be present in results
    assert "embedding" not in row


# ---------------------------------------------------------------------------
# Test 3 – duplicate upsert is ignored
# ---------------------------------------------------------------------------

def test_duplicate_upsert_ignored(tmp_db):
    with patch.object(db_module, "_get_model", return_value=_mock_model()):
        with patch.object(db_module, "get_db_path", return_value=tmp_db):
            db_module.upsert_speech(SPEECH_A)
            db_module.upsert_speech(SPEECH_A)  # same URL → should be ignored
            results = db_module.get_speeches()

    assert len(results) == 1, "Duplicate URL should not create a second row"


# ---------------------------------------------------------------------------
# Test 4 – speech_exists
# ---------------------------------------------------------------------------

def test_speech_exists(tmp_db):
    with patch.object(db_module, "get_db_path", return_value=tmp_db):
        assert db_module.speech_exists(SPEECH_A["url"]) is False

    with patch.object(db_module, "_get_model", return_value=_mock_model()):
        with patch.object(db_module, "get_db_path", return_value=tmp_db):
            db_module.upsert_speech(SPEECH_A)
            assert db_module.speech_exists(SPEECH_A["url"]) is True


# ---------------------------------------------------------------------------
# Test 5 – filter by speaker
# ---------------------------------------------------------------------------

def test_get_speeches_filter_by_speaker(tmp_db):
    with patch.object(db_module, "_get_model", return_value=_mock_model()):
        with patch.object(db_module, "get_db_path", return_value=tmp_db):
            db_module.upsert_speech(SPEECH_A)  # Lagarde
            db_module.upsert_speech(SPEECH_B)  # Lane

            lagarde_results = db_module.get_speeches(speaker="Christine Lagarde")
            lane_results = db_module.get_speeches(speaker="Philip Lane")

    assert len(lagarde_results) == 1
    assert lagarde_results[0]["speaker"] == "Christine Lagarde"

    assert len(lane_results) == 1
    assert lane_results[0]["speaker"] == "Philip Lane"


# ---------------------------------------------------------------------------
# Test 6 – filter by date
# ---------------------------------------------------------------------------

def test_get_speeches_filter_by_date(tmp_db):
    with patch.object(db_module, "_get_model", return_value=_mock_model()):
        with patch.object(db_module, "get_db_path", return_value=tmp_db):
            db_module.upsert_speech(SPEECH_A)  # 2024-01-15
            db_module.upsert_speech(SPEECH_B)  # 2024-03-20
            db_module.upsert_speech(SPEECH_C)  # 2023-11-05

            # Only 2024 speeches
            results_2024 = db_module.get_speeches(date_from="2024-01-01", date_to="2024-12-31")
            # Only speeches on/after 2024-02-01
            results_after_feb = db_module.get_speeches(date_from="2024-02-01")
            # Only speeches before 2024-01-01 (just speech_c)
            results_2023 = db_module.get_speeches(date_to="2023-12-31")

    assert len(results_2024) == 2
    assert len(results_after_feb) == 1
    assert results_after_feb[0]["url"] == SPEECH_B["url"]
    assert len(results_2023) == 1
    assert results_2023[0]["url"] == SPEECH_C["url"]


# ---------------------------------------------------------------------------
# Test 7 – embedding stored with correct dtype (uses real model)
# ---------------------------------------------------------------------------

def test_embedding_stored(tmp_db):
    """
    Upsert a speech using the real SentenceTransformer model and verify that
    the raw BLOB can be deserialised to a float32 numpy array with positive
    dimension count.
    """
    with patch.object(db_module, "get_db_path", return_value=tmp_db):
        # Reset the singleton so the real model loads fresh
        db_module._model = None
        db_module.upsert_speech(SPEECH_A)

    # Read raw BLOB directly from the DB
    conn = sqlite3.connect(tmp_db)
    cur = conn.execute("SELECT embedding FROM speeches WHERE url = ?", (SPEECH_A["url"],))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    blob = row[0]
    assert blob is not None, "Embedding BLOB should not be NULL"

    arr = db_module._deserialise(blob)
    assert arr.dtype == np.float32
    assert arr.ndim == 1
    assert arr.shape[0] > 0, "Embedding should have at least one dimension"

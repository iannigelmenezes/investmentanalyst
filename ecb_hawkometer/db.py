"""
ecb_hawkometer/db.py
--------------------
Manages a SQLite database for ECB speeches with sentence-transformer embeddings.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.dirname(__file__), "data")
_DB_FILENAME = "ecb_speeches.db"


def get_db_path() -> str:
    """Return the absolute path to the SQLite DB file."""
    return os.path.join(_DB_DIR, _DB_FILENAME)


# ---------------------------------------------------------------------------
# Lazy embedding model singleton
# ---------------------------------------------------------------------------

_model = None


def _get_model():
    """Load (once) and return the SentenceTransformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_id(url: str) -> str:
    """SHA-256 of URL, first 16 hex chars."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


_MAX_ENCODE_CHARS = 2000  # truncate before encoding to keep it fast


def _encode(text: str) -> Optional[bytes]:
    """Return serialised float32 embedding, or None for empty text."""
    if not text:
        return None
    model = _get_model()
    snippet = text[:_MAX_ENCODE_CHARS]
    embedding: np.ndarray = model.encode(snippet, convert_to_numpy=True).astype(np.float32)
    return embedding.tobytes()


def _deserialise(blob: bytes) -> np.ndarray:
    """Deserialise a BLOB back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _connect() -> sqlite3.Connection:
    """Open a connection to the DB (creates file if needed)."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sqlite3.connect(db_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the DB and speeches table if they don't exist."""
    db_path = get_db_path()
    already_exists = os.path.exists(db_path) and os.path.getsize(db_path) > 0

    conn = _connect()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS speeches (
                id          TEXT PRIMARY KEY,
                speaker     TEXT NOT NULL,
                date        DATE NOT NULL,
                title       TEXT,
                url         TEXT UNIQUE NOT NULL,
                full_text   TEXT,
                embedding   BLOB,
                scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.close()

    if not already_exists:
        print(f"[DB] Initialised database at {db_path}")


def speech_exists(url: str) -> bool:
    """Return True if a speech with this URL is already in the DB."""
    conn = _connect()
    try:
        cur = conn.execute("SELECT 1 FROM speeches WHERE url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_existing_urls() -> set[str]:
    """Return all URLs currently in the DB."""
    conn = _connect()
    try:
        cur = conn.execute("SELECT url FROM speeches")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def upsert_speech(speech: dict) -> None:
    """
    Insert a speech (or ignore if URL already exists).

    speech dict keys: speaker, date, title, url, full_text
    Automatically generates id (sha256 of url) and computes + stores embedding.
    """
    url: str = speech["url"]
    speech_id = _make_id(url)
    full_text: Optional[str] = speech.get("full_text") or None
    embedding_blob = _encode(full_text) if full_text else None

    conn = _connect()
    with conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO speeches
                (id, speaker, date, title, url, full_text, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                speech_id,
                speech["speaker"],
                speech["date"],
                speech.get("title"),
                url,
                full_text,
                embedding_blob,
            ),
        )
    conn.close()

    print(f"[DB] Stored speech: {speech.get('title')} by {speech['speaker']}")


def get_speeches(
    speaker: str = None,
    date_from: str = None,
    date_to: str = None,
) -> list[dict]:
    """
    Return speeches matching filters. All filters optional.

    date_from / date_to: ISO strings YYYY-MM-DD
    Returns list of dicts with all columns EXCEPT embedding.
    """
    query = """
        SELECT id, speaker, date, title, url, full_text, scraped_at
        FROM speeches
        WHERE 1=1
    """
    params: list = []

    if speaker is not None:
        query += " AND speaker = ?"
        params.append(speaker)
    if date_from is not None:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to is not None:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY date DESC"

    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_all_speakers() -> list[str]:
    """Return sorted list of distinct speaker names."""
    conn = _connect()
    try:
        cur = conn.execute("SELECT DISTINCT speaker FROM speeches ORDER BY speaker")
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

"""
Tests for ecb_hawkometer.scraper — F2

All tests use unittest.mock to mock requests.get. No real HTTP calls are made.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import pytest

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

ECB_BASE = "https://www.ecb.europa.eu"
FOEDB_HOST = f"{ECB_BASE}/foedb/dbs/foedb"
DB_NAME = "publications.en"
VERSION = "9999999999"
DB_HASH = "TESTHASH"
VER_PATH = f"{FOEDB_HOST}/{DB_NAME}/{VERSION}/{DB_HASH}"

RECORD_HEADER = [
    "id",
    "pub_timestamp",
    "year",
    "issue_number",
    "type",
    "JEL_Code",
    "Taxonomy",
    "boardmember",
    "Authors",
    "documentTypes",
    "publicationProperties",
    "childrenPublication",
    "relatedPublications",
]
RECORD_SIZE = len(RECORD_HEADER)
SPEECH_TYPE_ID = 19


def _ts(days_ago: int) -> int:
    """Return a Unix timestamp for N days ago."""
    return int(
        (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).timestamp()
    )


def _make_flat_record(
    rec_id: int,
    pub_timestamp: int,
    rec_type: int,
    speaker: str,
    title: str,
    url_path: str,
) -> list:
    """Build a single flat record matching RECORD_HEADER layout."""
    return [
        rec_id,               # id
        pub_timestamp,        # pub_timestamp
        2025,                 # year
        0,                    # issue_number
        rec_type,             # type
        None,                 # JEL_Code
        None,                 # Taxonomy
        speaker,              # boardmember
        None,                 # Authors
        [url_path],           # documentTypes
        {"Title": title},     # publicationProperties
        [],                   # childrenPublication
        [],                   # relatedPublications
    ]


def _build_chunk(records: list[list]) -> list:
    """Concatenate flat records into a single flat list."""
    flat = []
    for rec in records:
        flat.extend(rec)
    return flat


def _versions_json() -> bytes:
    return json.dumps([{"version": VERSION, "hash": DB_HASH}]).encode()


def _chunk_json(records: list[list]) -> bytes:
    return json.dumps(_build_chunk(records)).encode()


def _mock_response(body: bytes, status: int = 200) -> MagicMock:
    """Create a mock requests.Response.

    If *body* is valid JSON, `.json()` will return the parsed value.
    In all cases, `.text` contains the decoded string.
    """
    mock = MagicMock()
    mock.status_code = status
    decoded = body.decode("utf-8", errors="replace")
    mock.text = decoded
    try:
        mock.json.return_value = json.loads(decoded)
    except json.JSONDecodeError:
        mock.json.side_effect = json.JSONDecodeError("Not JSON", decoded, 0)
    return mock


def _not_found_response() -> MagicMock:
    mock = MagicMock()
    mock.status_code = 404
    return mock


# ---------------------------------------------------------------------------
# Side-effect factory
# ---------------------------------------------------------------------------

def _make_get_side_effect(url_map: dict):
    """Return a side-effect function for requests.Session.get that returns
    pre-configured mock responses indexed by URL.  Unknown URLs raise
    AssertionError.
    """
    def _side_effect(url, **kwargs):
        if url in url_map:
            return url_map[url]
        # Return 404 for unknown URLs (e.g. ssl probe, extra chunks)
        return _not_found_response()
    return _side_effect


# ---------------------------------------------------------------------------
# Test 1 — Delta refresh: existing URLs are skipped
# ---------------------------------------------------------------------------

class TestDeltaRefresh:
    """Speeches whose URL is already in existing_urls must be skipped."""

    def test_all_existing_urls_skipped(self):
        speech_url = f"{ECB_BASE}/press/key/date/2025/html/ecb.sp250101~abc.en.html"
        ts = _ts(30)  # 30 days ago — within 12 months

        rec = _make_flat_record(
            rec_id=1001,
            pub_timestamp=ts,
            rec_type=SPEECH_TYPE_ID,
            speaker="Christine Lagarde",
            title="Test Speech",
            url_path="/press/key/date/2025/html/ecb.sp250101~abc.en.html",
        )

        url_map = {
            # SSL probe
            f"{ECB_BASE}/": _not_found_response(),
            # versions
            f"{FOEDB_HOST}/{DB_NAME}/versions.json": _mock_response(_versions_json()),
            # data chunk group 0, sub 0
            f"{VER_PATH}/data/0/chunk_0.json": _mock_response(_chunk_json([rec])),
        }

        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession:
            sess_instance = MagicMock()
            sess_instance.get.side_effect = _make_get_side_effect(url_map)
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            result = scraper.scrape_speeches(existing_urls={speech_url})

        assert result == [], (
            f"Expected empty list when all URLs are in existing_urls, got {result}"
        )


# ---------------------------------------------------------------------------
# Test 2 — 12-month filter: old speeches are excluded
# ---------------------------------------------------------------------------

class TestTwelveMonthFilter:
    """Speeches older than 365 days must be filtered out."""

    def test_old_speech_excluded(self):
        ts_old = _ts(400)  # 400 days ago — outside 12-month window

        rec = _make_flat_record(
            rec_id=2001,
            pub_timestamp=ts_old,
            rec_type=SPEECH_TYPE_ID,
            speaker="Philip Lane",
            title="Old Speech",
            url_path="/press/key/date/2024/html/ecb.sp240101~xyz.en.html",
        )

        url_map = {
            f"{ECB_BASE}/": _not_found_response(),
            f"{FOEDB_HOST}/{DB_NAME}/versions.json": _mock_response(_versions_json()),
            f"{VER_PATH}/data/0/chunk_0.json": _mock_response(_chunk_json([rec])),
        }

        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession:
            sess_instance = MagicMock()
            sess_instance.get.side_effect = _make_get_side_effect(url_map)
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            result = scraper.scrape_speeches(existing_urls=set())

        assert result == [], (
            f"Expected empty list for speeches older than 365 days, got {result}"
        )

    def test_recent_speech_included(self):
        """A speech within 12 months should be included (provided its page is fetchable)."""
        ts_recent = _ts(10)  # 10 days ago
        url_path = "/press/key/date/2025/html/ecb.sp251201~new.en.html"
        full_url = f"{ECB_BASE}{url_path}"

        rec = _make_flat_record(
            rec_id=3001,
            pub_timestamp=ts_recent,
            rec_type=SPEECH_TYPE_ID,
            speaker="Isabel Schnabel",
            title="Recent Speech",
            url_path=url_path,
        )

        speech_html = (
            b"<html><body><main>"
            b"<div class='section'><p>Hello world speech text.</p></div>"
            b"</main></body></html>"
        )

        url_map = {
            f"{ECB_BASE}/": _not_found_response(),
            f"{FOEDB_HOST}/{DB_NAME}/versions.json": _mock_response(_versions_json()),
            f"{VER_PATH}/data/0/chunk_0.json": _mock_response(_chunk_json([rec])),
            full_url: _mock_response(speech_html),
        }

        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession, \
             patch("ecb_hawkometer.scraper.time.sleep"):
            sess_instance = MagicMock()
            sess_instance.get.side_effect = _make_get_side_effect(url_map)
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            result = scraper.scrape_speeches(existing_urls=set())

        assert len(result) == 1, f"Expected 1 speech, got {len(result)}"
        assert result[0]["speaker"] == "Isabel Schnabel"
        assert result[0]["title"] == "Recent Speech"
        assert result[0]["url"] == full_url


# ---------------------------------------------------------------------------
# Test 3 — Graceful failure: ConnectionError returns empty list, no exception
# ---------------------------------------------------------------------------

class TestGracefulFailure:
    """On ConnectionError during versions fetch, return [] without raising."""

    def test_connection_error_returns_empty_list(self):
        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession:
            sess_instance = MagicMock()
            sess_instance.get.side_effect = ConnectionError("Network unreachable")
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            result = scraper.scrape_speeches(existing_urls=set())

        assert result == [], (
            f"Expected empty list on ConnectionError, got {result}"
        )

    def test_connection_error_does_not_raise(self):
        """Calling scrape_speeches must never raise an exception."""
        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession:
            sess_instance = MagicMock()
            sess_instance.get.side_effect = ConnectionError("Network unreachable")
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            try:
                scraper.scrape_speeches(existing_urls=set())
            except Exception as exc:
                pytest.fail(f"scrape_speeches raised an unexpected exception: {exc}")


# ---------------------------------------------------------------------------
# Test 4 — Text extraction: HTML tags are stripped
# ---------------------------------------------------------------------------

class TestTextExtraction:
    """Verify that HTML is stripped from full_text and only plain text remains."""

    def test_html_tags_stripped_from_full_text(self):
        ts_recent = _ts(5)
        url_path = "/press/key/date/2025/html/ecb.sp251201~strip.en.html"
        full_url = f"{ECB_BASE}{url_path}"

        rec = _make_flat_record(
            rec_id=4001,
            pub_timestamp=ts_recent,
            rec_type=SPEECH_TYPE_ID,
            speaker="Fabio Panetta",
            title="Stripped Speech",
            url_path=url_path,
        )

        # A speech page with HTML that should be stripped
        speech_html = (
            b"<html><body><main>"
            b"<h1>Headline</h1>"
            b"<div class='section'>"
            b"  <p>First <strong>paragraph</strong> text.</p>"
            b"  <p>Second paragraph with <a href='#'>a link</a>.</p>"
            b"</div>"
            b"</main></body></html>"
        )

        url_map = {
            f"{ECB_BASE}/": _not_found_response(),
            f"{FOEDB_HOST}/{DB_NAME}/versions.json": _mock_response(_versions_json()),
            f"{VER_PATH}/data/0/chunk_0.json": _mock_response(_chunk_json([rec])),
            full_url: _mock_response(speech_html),
        }

        with patch("ecb_hawkometer.scraper.requests.Session") as MockSession, \
             patch("ecb_hawkometer.scraper.time.sleep"):
            sess_instance = MagicMock()
            sess_instance.get.side_effect = _make_get_side_effect(url_map)
            MockSession.return_value = sess_instance

            from ecb_hawkometer import scraper
            result = scraper.scrape_speeches(existing_urls=set())

        assert len(result) == 1, f"Expected 1 result, got {len(result)}"
        full_text = result[0]["full_text"]

        # Must not contain any HTML tags
        assert "<" not in full_text, f"HTML tag found in full_text: {full_text!r}"
        assert ">" not in full_text, f"HTML tag found in full_text: {full_text!r}"

        # Must contain the actual text content
        assert "First" in full_text, f"Expected 'First' in full_text: {full_text!r}"
        assert "paragraph" in full_text, f"Expected 'paragraph' in full_text: {full_text!r}"
        assert "Second paragraph" in full_text, f"Expected 'Second paragraph' in full_text: {full_text!r}"

    def test_html_tags_stripped_direct(self):
        """Unit-test _extract_speech_text directly without the full scrape pipeline."""
        from ecb_hawkometer.scraper import _extract_speech_text

        html = """
        <html>
          <head><style>body { font-size: 12px; }</style></head>
          <body>
            <nav>Navigation links here</nav>
            <header>Header content</header>
            <main>
              <p>Speech content <em>with emphasis</em>.</p>
              <p>More <b>bold</b> text here.</p>
            </main>
            <footer>Footer</footer>
          </body>
        </html>
        """
        result = _extract_speech_text(html)

        # No HTML tags
        assert "<" not in result
        assert ">" not in result
        # Expected text present
        assert "Speech content" in result
        assert "with emphasis" in result
        assert "More" in result
        assert "bold" in result
        # Navigation and footer removed (they are in <nav>/<footer> tags)
        assert "Navigation links here" not in result
        assert "Footer" not in result

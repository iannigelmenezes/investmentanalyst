"""
ECB Hawkometer — F2: Scraper
Scrapes ECB speeches from the past 12 months via the ECB foedb JSON API.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LISTING_URL = "https://www.ecb.europa.eu/press/key/html/index.en.html"

_FOEDB_HOST = "https://www.ecb.europa.eu/foedb/dbs/foedb"
_DB_NAME = "publications.en"
_SPEECH_TYPE_ID = 19          # foedb type-id for ECB speeches
_CHUNK_SIZE = 250             # records per data sub-chunk
_CHUNK_GROUP_SIZE = 1000      # records per chunk group

_CA_PATH = r"C:\Users\MNZI\OneDrive - PGGM\Analyst\corporate_ca.pem"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
}

_FOEDB_RECORD_HEADER = [
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> tuple[requests.Session, bool]:
    """Return a (session, ssl_ok) tuple.

    Tries the corporate CA first; falls back to verify=False with a warning.
    Returns ssl_ok=True when the CA cert works, False otherwise.
    """
    session = requests.Session()
    session.headers.update(_HEADERS)
    # Quick probe with corporate CA
    try:
        session.get(
            "https://www.ecb.europa.eu/", verify=_CA_PATH, timeout=10
        )
        return session, True
    except Exception:
        print(
            "[Scraper] WARNING: Corporate CA cert failed — "
            "falling back to verify=False (TLS verification disabled)."
        )
        return session, False


def _get(session: requests.Session, url: str, ssl_ok: bool, **kwargs):
    """GET with SSL toggle, retrying up to 2 times (3 total attempts) with
    3-second backoff.  Returns the Response or None on permanent failure.
    """
    verify = _CA_PATH if ssl_ok else False
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = session.get(url, verify=verify, timeout=20, **kwargs)
            if resp.status_code == 200:
                return resp
            last_error = Exception(f"HTTP {resp.status_code}")
        except Exception as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(3)
    print(f"[Scraper] Failed to fetch {url} after 3 attempts: {last_error}")
    return None


# ---------------------------------------------------------------------------
# foedb helpers
# ---------------------------------------------------------------------------


def _get_foedb_version(session: requests.Session, ssl_ok: bool) -> tuple[str, str] | None:
    """Return (version, hash) for the current publications DB, or None."""
    url = f"{_FOEDB_HOST}/{_DB_NAME}/versions.json"
    resp = _get(session, url, ssl_ok)
    if resp is None:
        return None
    try:
        data = resp.json()
        return str(data[0]["version"]), str(data[0]["hash"])
    except Exception as exc:
        print(f"[Scraper] WARNING: Could not parse foedb versions.json — {exc}")
        return None


def _get_data_chunk(
    session: requests.Session,
    ssl_ok: bool,
    ver_path: str,
    group: int,
    subchunk: int,
) -> list | None:
    """Fetch a flat data array from the foedb data API."""
    url = f"{ver_path}/data/{group}/chunk_{subchunk}.json"
    resp = _get(session, url, ssl_ok)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as exc:
        print(f"[Scraper] WARNING: Could not decode data chunk {group}/{subchunk} — {exc}")
        return None


def _parse_records_from_flat(flat: list) -> list[dict]:
    """Convert a flat foedb array into a list of record dicts."""
    record_size = len(_FOEDB_RECORD_HEADER)
    total = len(flat) // record_size
    records = []
    for i in range(total):
        offset = i * record_size
        rec = {_FOEDB_RECORD_HEADER[j]: flat[offset + j] for j in range(record_size)}
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Speech text extraction
# ---------------------------------------------------------------------------


def _extract_speech_text(html: str) -> str:
    """Strip HTML tags from a speech page and return plain text of the main
    content area (ignoring nav, headers, footers).
    """
    soup = BeautifulSoup(html, "lxml")
    # Remove navigation, header, footer, script, style
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()
    # Try to find the main content section
    content = (
        soup.find("main")
        or soup.find("div", class_="section")
        or soup.find("article")
        or soup.find("body")
    )
    if content is None:
        return soup.get_text(separator=" ", strip=True)
    return content.get_text(separator=" ", strip=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scrape_speeches(existing_urls: set[str]) -> list[dict]:
    """Scrape ECB speeches from the past 12 months.

    Args:
        existing_urls: set of URL strings already in the database (for delta
            refresh).

    Returns:
        List of dicts, one per NEW speech:
            {
                "speaker":   str,
                "date":      str  (ISO format YYYY-MM-DD),
                "title":     str,
                "full_text": str  (plain text, HTML tags stripped),
                "url":       str  (full absolute URL, unique key),
            }

    Raises:
        Nothing — all errors are caught, printed with context, and an empty
        list returned.
    """
    try:
        return _scrape(existing_urls)
    except Exception as exc:
        print(f"[Scraper] Unexpected error in scrape_speeches: {exc}")
        return []


def _scrape(existing_urls: set[str]) -> list[dict]:
    cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=365)
    cutoff_ts = cutoff_dt.timestamp()

    session, ssl_ok = _make_session()

    # 1. Get current foedb version
    version_info = _get_foedb_version(session, ssl_ok)
    if version_info is None:
        print(
            "[Scraper] WARNING: Could not find speech list on ECB page — "
            f"page structure may have changed. URL: {LISTING_URL}"
        )
        return []

    version, db_hash = version_info
    ver_path = f"{_FOEDB_HOST}/{_DB_NAME}/{version}/{db_hash}"

    # 2. Walk data chunks (sorted by pub_timestamp desc — newest first)
    #    Stop when the oldest record in a chunk is beyond the 12-month window.
    speeches_meta: list[dict] = []
    group = 0
    done = False

    while not done:
        # Each chunk group has 4 sub-chunks (1000 / 250 = 4)
        for subchunk in range(_CHUNK_GROUP_SIZE // _CHUNK_SIZE):
            flat = _get_data_chunk(session, ssl_ok, ver_path, group, subchunk)
            if flat is None:
                # No more data or error — stop scanning
                done = True
                break

            records = _parse_records_from_flat(flat)
            if not records:
                done = True
                break

            for rec in records:
                ts = rec.get("pub_timestamp")
                if ts is None:
                    continue
                if ts < cutoff_ts:
                    # Records are sorted newest-first; once we pass the cutoff
                    # every subsequent record will also be too old.
                    done = True
                    break
                if rec.get("type") != _SPEECH_TYPE_ID:
                    continue

                # Build the URL
                doc_types = rec.get("documentTypes") or []
                if not doc_types:
                    continue
                rel_path = doc_types[0]
                if not isinstance(rel_path, str):
                    continue
                if rel_path.startswith("http"):
                    url = rel_path
                else:
                    url = "https://www.ecb.europa.eu" + rel_path

                speeches_meta.append({
                    "url": url,
                    "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
                    "title": (rec.get("publicationProperties") or {}).get("Title", ""),
                    "speaker": rec.get("boardmember") or "",
                })

            if done:
                break

        if not done:
            group += 1
            # Safety: if the first sub-chunk of the next group returns 404, we're done
            # (handled inside the loop above via flat is None)

    # 3. Filter out already-known URLs
    new_speeches = [s for s in speeches_meta if s["url"] not in existing_urls]

    if not new_speeches:
        return []

    # 4. Return metadata immediately (full_text=None).
    #    Full text is fetched lazily by fetch_full_texts() for the subset
    #    that actually needs analysis — avoids fetching 100+ speeches upfront.
    return [
        {
            "speaker": meta["speaker"],
            "date": meta["date"],
            "title": meta["title"],
            "full_text": None,
            "url": meta["url"],
        }
        for meta in new_speeches
    ]


def fetch_full_texts(speeches: list[dict]) -> list[dict]:
    """Fetch full text for a list of speech metadata dicts (those with full_text=None).

    Only fetches speeches that don't already have full_text set.
    Returns the same list with full_text populated in-place.
    """
    session, ssl_ok = _make_session()
    needs_fetch = [s for s in speeches if not s.get("full_text")]
    print(f"[Scraper] Fetching full text for {len(needs_fetch)} speech(es)...")
    for i, speech in enumerate(needs_fetch):
        if i > 0:
            time.sleep(1)
        resp = _get(session, speech["url"], ssl_ok)
        if resp is None:
            speech["full_text"] = ""
            continue
        speech["full_text"] = _extract_speech_text(resp.text)
        print(f"[Scraper] ({i+1}/{len(needs_fetch)}) Fetched: {speech['title'][:60]}")
    return speeches

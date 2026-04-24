"""
ecb_hawkometer/main.py
Full pipeline orchestrator for the ECB Hawkometer.
Called by intents/ecb_hawkometer.py
"""

import os
import sys

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError for box chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# add workspace root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ecb_hawkometer import db, scraper, analyzer, dashboard

def run_pipeline():
    from datetime import date, timedelta

    print("\n==========================================")
    print("       ECB Policy Monitor - Hawkometer    ")
    print("==========================================\n")

    # Step 1: Initialise DB
    print("[1/6] Initialising database...")
    db.init_db()

    # Step 2: Scrape new speech metadata (fast — no full-text fetch yet)
    print("[2/6] Scraping ECB speech listing (delta refresh)...")
    existing_urls = db.get_existing_urls()
    new_speeches = scraper.scrape_speeches(existing_urls)
    print(f"      -> {len(new_speeches)} new speech(es) found in listing")

    # Step 3: Store metadata stubs to DB (embeddings computed later after full text)
    print("[3/6] Storing speech metadata...")
    for speech in new_speeches:
        db.upsert_speech(speech)
    print(f"      -> {len(new_speeches)} speech(es) stored")

    # Step 4: Load 8-week window for analysis
    date_from = (date.today() - timedelta(weeks=8)).isoformat()
    recent = db.get_speeches(date_from=date_from)
    print(f"[4/6] {len(recent)} speech(es) in last 8 weeks — fetching full text for those...")

    if not recent:
        print("\n[!] No recent speeches found in database.")
        print("    Check ECB website connectivity.")
        return

    # Fetch full text only for the analysis window (not all 12 months)
    recent_needing_text = [s for s in recent if not s.get("full_text")]
    if recent_needing_text:
        enriched = scraper.fetch_full_texts(recent_needing_text)

        # Batch-encode all new texts in one model call (much faster than N individual calls)
        texts = [s.get("full_text", "") or "" for s in enriched]
        print(f"[4/6] Batch-encoding {len(texts)} speech(es)...")
        import numpy as np
        from sentence_transformers import SentenceTransformer
        import os as _os
        _env_key = "TOKENIZERS_PARALLELISM"
        _os.environ[_env_key] = "false"
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        snippets = [t[:2000] for t in texts]
        embeddings = _model.encode(snippets, convert_to_numpy=True, batch_size=8, show_progress_bar=True)

        import sqlite3, hashlib
        db_path = db.get_db_path()
        import datetime as _dt
        with sqlite3.connect(db_path) as conn:
            for speech, emb in zip(enriched, embeddings):
                if not speech.get("full_text"):
                    continue
                url = speech["url"]
                sid = hashlib.sha256(url.encode()).hexdigest()[:16]
                emb_blob = emb.astype(np.float32).tobytes()
                conn.execute("""
                    UPDATE speeches SET full_text=?, embedding=?, scraped_at=?
                    WHERE id=?
                """, (speech["full_text"], emb_blob, _dt.datetime.utcnow().isoformat(), sid))
        print(f"      -> Embeddings stored")

        # Reload from DB with full text
        recent = db.get_speeches(date_from=date_from)

    # Step 5: Inference — write prompts, pause for OpenCode, read results
    print("[5/6] Running inference (file-based handoff to OpenCode)...")
    speaker_scores = analyzer.get_speaker_scores(recent)
    policy_prediction = analyzer.get_policy_prediction(speaker_scores)

    # Step 6: Generate dashboard
    print("[6/6] Generating dashboard...")
    output_path = dashboard.generate_dashboard(speaker_scores, policy_prediction, recent)

    print(f"\n[OK] Source: ECB (ecb.europa.eu)")
    print(f"[OK] Vintage: {date.today().isoformat()}")
    print(f"[OK] Chart: {output_path} (opened automatically)")

if __name__ == "__main__":
    run_pipeline()

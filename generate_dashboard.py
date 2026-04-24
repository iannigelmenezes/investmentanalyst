"""
generate_dashboard.py
---------------------
One-shot script: reads existing speaker + policy + last-week JSON result files
and generates the ECB Hawkometer dashboard HTML.
Bypasses the full pipeline (no scraping, no inference loop).
"""

import json
import os
import sys
import glob
from datetime import datetime

# Add workspace root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ecb_hawkometer import dashboard, db

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "ecb_hawkometer", "data", "results")

def load_latest_results():
    """Load the most recent speaker + policy + last-week JSON results."""
    speaker_files   = glob.glob(os.path.join(RESULTS_DIR, "speaker_*.json"))
    last_week_files = glob.glob(os.path.join(RESULTS_DIR, "last_week_*.json"))

    if not speaker_files:
        print("[!] No speaker result JSON files found in", RESULTS_DIR)
        sys.exit(1)

    def get_ts(path):
        name = os.path.basename(path)
        parts = name.rsplit("_", 2)
        if len(parts) >= 3:
            return parts[-2] + "_" + parts[-1].replace(".json", "")
        return ""

    latest_ts = max(get_ts(f) for f in speaker_files)
    print(f"[*] Using result batch timestamp: {latest_ts}")

    speaker_scores = []
    for f in speaker_files:
        if latest_ts in f:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                speaker_scores.append(data)
            print(f"    Loaded speaker: {data.get('speaker', '?')} (score={data.get('hawkishness_score')})")

    # Load last-week speeches (latest file by timestamp)
    last_week_speeches = []
    if last_week_files:
        latest_lw = sorted(last_week_files)[-1]
        with open(latest_lw, "r", encoding="utf-8") as fh:
            last_week_speeches = json.load(fh)
        print(f"    Loaded {len(last_week_speeches)} last-week speech analysis(es) from {os.path.basename(latest_lw)}")
    else:
        print("[!] No last-week speech analysis file found — top section will be empty")

    return speaker_scores, last_week_speeches, latest_ts


def load_recent_speeches():
    """Load recent speeches from DB for sparkline data."""
    from datetime import date, timedelta
    db.init_db()
    date_from = (date.today() - timedelta(weeks=13)).isoformat()
    return db.get_speeches(date_from=date_from)


if __name__ == "__main__":
    print("\n==========================================")
    print("  ECB Hawkometer — Dashboard Generator   ")
    print("==========================================\n")

    speaker_scores, last_week_speeches, latest_ts = load_latest_results()

    print("\n[*] Loading recent speeches from DB...")
    recent_speeches = load_recent_speeches()
    print(f"    {len(recent_speeches)} speeches loaded")

    print("\n[*] Generating dashboard HTML...")
    output_path = dashboard.generate_dashboard(
        speaker_scores,
        policy_prediction={},
        db_speeches=recent_speeches,
        last_week_speeches=last_week_speeches,
    )

    print(f"\n[OK] Dashboard written to: {output_path}")

    batch_line = (
        f"{latest_ts} | speakers={len(speaker_scores)} | "
        f"last_week_speeches={len(last_week_speeches)} | "
        f"generated={datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    )
    batch_file = os.path.join(RESULTS_DIR, "CURRENT_BATCH.txt")
    with open(batch_file, "w", encoding="utf-8") as fh:
        fh.write(batch_line)
    print(f"[OK] Batch state written to: ecb_hawkometer/data/results/CURRENT_BATCH.txt")

    print("[OK] Opening in browser...")

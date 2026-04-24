import sys, os
sys.path.insert(0, r'C:\Users\MNZI\OneDrive - PGGM\Analyst')
from ecb_hawkometer import db, scraper
from datetime import date, timedelta

db.init_db()

# Delta refresh
print("=== DELTA REFRESH ===")
existing_urls = db.get_existing_urls()
print(f"Existing speeches in DB: {len(existing_urls)}")
new_speeches = scraper.scrape_speeches(existing_urls)
print(f"New speeches found: {len(new_speeches)}")
for s in new_speeches:
    print(f"  NEW: {s.get('date')} | {s.get('speaker')} | {s.get('title')}")

# Store new stubs
for s in new_speeches:
    db.upsert_speech(s)

# Show last-week window
print("\n=== LAST WEEK ===")
last_week = (date.today() - timedelta(weeks=1)).isoformat()
recent = db.get_speeches(date_from=last_week)
for s in sorted(recent, key=lambda x: x.get('date',''), reverse=True):
    ft = s.get('full_text') or ''
    print(f"  {s.get('date')} | {s.get('speaker','?')} | {s.get('title','')[:55]} | text={len(ft)} chars")

# Show 8-week window
print("\n=== 8-WEEK WINDOW ===")
eight_weeks = (date.today() - timedelta(weeks=8)).isoformat()
window = db.get_speeches(date_from=eight_weeks)
print(f"Total speeches in 8w window: {len(window)}")
speakers = {}
for s in window:
    sp = s.get('speaker','?')
    speakers[sp] = speakers.get(sp, 0) + 1
for sp, cnt in sorted(speakers.items()):
    print(f"  {sp}: {cnt} speech(es)")

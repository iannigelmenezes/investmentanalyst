import sys
sys.path.insert(0, r'C:\Users\MNZI\OneDrive - PGGM\Analyst')
from ecb_hawkometer import db
from datetime import date, timedelta

db.init_db()
all_speeches = db.get_speeches()
date_from = (date.today() - timedelta(weeks=8)).isoformat()
recent = db.get_speeches(date_from=date_from)
with_text = [s for s in recent if s.get('full_text')]
print(f'Total speeches in DB: {len(all_speeches)}')
print(f'Last 8 weeks (from {date_from}): {len(recent)}')
print(f'With full_text populated: {len(with_text)}')
speakers = sorted(set(s['speaker'] for s in recent))
print(f'Speakers in 8-week window: {speakers}')

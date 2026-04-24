import sys, os
sys.path.insert(0, r'C:\Users\MNZI\OneDrive - PGGM\Analyst')
from ecb_hawkometer import db
from datetime import date, timedelta
db.init_db()
last_week = (date.today() - timedelta(weeks=1)).isoformat()
recent = db.get_speeches(date_from=last_week)
for s in sorted(recent, key=lambda x: x.get('date',''), reverse=True):
    print('=== SPEECH ===')
    print('Date:', s.get('date'))
    print('Speaker:', s.get('speaker'))
    print('Title:', s.get('title'))
    print('URL:', s.get('url'))
    ft = s.get('full_text') or ''
    print('Full text length:', len(ft))
    print('First 2000 chars:')
    print(ft[:2000])
    print()

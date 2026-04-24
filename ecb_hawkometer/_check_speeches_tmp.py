import sys, os
sys.path.insert(0, r'C:\Users\MNZI\OneDrive - PGGM\Analyst')
from ecb_hawkometer import db
from datetime import date, timedelta
db.init_db()
last_week = (date.today() - timedelta(weeks=1)).isoformat()
last_12w  = (date.today() - timedelta(weeks=13)).isoformat()
recent = db.get_speeches(date_from=last_week)
older  = db.get_speeches(date_from=last_12w, date_to=last_week)
print('LAST WEEK speeches:', len(recent))
for s in sorted(recent, key=lambda x: x.get('date',''), reverse=True):
    print(' ', s.get('date'), s.get('speaker','?'), '|', s.get('title','')[:60])
print()
print('PRIOR 12W speeches:', len(older))
for s in sorted(older, key=lambda x: x.get('date',''), reverse=True):
    print(' ', s.get('date'), s.get('speaker','?'), '|', s.get('title','')[:60])

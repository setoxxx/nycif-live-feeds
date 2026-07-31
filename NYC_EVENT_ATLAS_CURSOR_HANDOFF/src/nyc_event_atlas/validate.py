from __future__ import annotations
import re
from datetime import date
from urllib.parse import urlparse
from .schema import EXPORT_COLUMNS, VALID_BOROUGHS, VALID_STATUSES, VALID_CONFIDENCE

ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

def validate_records(records):
    errors=[]; ids=set(); keys=set()
    for i,r in enumerate(records, start=2):
        if list(r.keys()) != EXPORT_COLUMNS: errors.append(f'row {i}: column order mismatch')
        eid=r.get('EVENT_ID','')
        if not eid or eid in ids: errors.append(f'row {i}: duplicate/missing EVENT_ID {eid!r}')
        ids.add(eid)
        if r.get('BOROUGH') not in VALID_BOROUGHS: errors.append(f'row {i}: invalid borough')
        if r.get('EVENT_STATUS') not in VALID_STATUSES: errors.append(f'row {i}: invalid status')
        if r.get('SOURCE_CONFIDENCE') not in VALID_CONFIDENCE: errors.append(f'row {i}: invalid source confidence')
        for c in ('START_DATE','END_DATE','LAST_VERIFIED'):
            v=r.get(c,'')
            if v not in ('Unknown','TBA',''):
                if not ISO_DATE.match(v): errors.append(f'row {i}: invalid {c} {v}')
                else:
                    try: date.fromisoformat(v)
                    except ValueError: errors.append(f'row {i}: impossible {c} {v}')
        for c in ('PHOTO_VALUE','NEWS_VALUE'):
            v=r.get(c,'Unknown')
            if v not in ('Unknown','') and str(v) not in {'1','2','3','4','5'}: errors.append(f'row {i}: invalid {c}')
        lat,lon=r.get('LATITUDE'),r.get('LONGITUDE')
        if (lat in ('','Unknown')) != (lon in ('','Unknown')): errors.append(f'row {i}: incomplete coordinate pair')
        if lat not in ('','Unknown'):
            try:
                if not -90 <= float(lat) <= 90 or not -180 <= float(lon) <= 180: errors.append(f'row {i}: coordinate range')
            except ValueError: errors.append(f'row {i}: nonnumeric coordinate')
        if not r.get('PRIMARY_SOURCE') or r.get('PRIMARY_SOURCE')=='Unknown': errors.append(f'row {i}: missing source')
        elif urlparse(r['PRIMARY_SOURCE']).scheme not in ('http','https'): errors.append(f'row {i}: invalid source URL')
    return errors

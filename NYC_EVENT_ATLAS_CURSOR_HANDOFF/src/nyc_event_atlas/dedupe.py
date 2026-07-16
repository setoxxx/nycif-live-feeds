from __future__ import annotations
from rapidfuzz.fuzz import token_set_ratio
from .normalize import normalize_name

def occurrence_key(r):
    title = normalize_name(r.get('EVENT_NAME'))
    date = r.get('START_DATE','Unknown')
    place = normalize_name(r.get('VENUE') if r.get('VENUE') not in ('','Unknown') else r.get('FULL_ADDRESS'))
    org = normalize_name(r.get('ORGANIZER'))
    return '|'.join((title,date,place,org))

def similarity(a,b):
    title = token_set_ratio(normalize_name(a.get('EVENT_NAME')), normalize_name(b.get('EVENT_NAME')))
    place = token_set_ratio(normalize_name(a.get('VENUE')), normalize_name(b.get('VENUE')))
    org = token_set_ratio(normalize_name(a.get('ORGANIZER')), normalize_name(b.get('ORGANIZER')))
    date_score = 100 if a.get('START_DATE') == b.get('START_DATE') else 0
    permit_score = 100 if a.get('PERMIT_ID') not in ('','Unknown') and a.get('PERMIT_ID') == b.get('PERMIT_ID') else 0
    return 0.40*title + 0.20*place + 0.15*org + 0.15*date_score + 0.10*permit_score

def find_matches(candidate, existing, threshold=75):
    out=[]
    cand_series = candidate.get('SERIES_ID')
    for row in existing:
        if candidate.get('BOROUGH') != row.get('BOROUGH'): continue
        same_date = candidate.get('START_DATE') == row.get('START_DATE')
        row_series = row.get('SERIES_ID')
        same_series = (
            cand_series not in (None, '', 'Unknown')
            and row_series not in (None, '', 'Unknown')
            and cand_series == row_series
        )
        # Require same date, or a real shared series id — never treat Unknown==Unknown as a series match.
        if not same_date and not same_series:
            continue
        score=similarity(candidate,row)
        if score>=threshold: out.append((score,row))
    return sorted(out,key=lambda x:x[0],reverse=True)

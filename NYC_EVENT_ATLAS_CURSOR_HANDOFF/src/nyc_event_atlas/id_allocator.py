from __future__ import annotations
import re
from .schema import BOROUGH_CODES

def next_numbers(records):
    maxima={code:0 for code in BOROUGH_CODES.values()}
    pattern=re.compile(r'^(?:NYC|ADJ)-\d{4}-([A-Z]+)-(\d{6})$')
    for r in records:
        m=pattern.match(r.get('EVENT_ID',''))
        if m: maxima[m.group(1)] = max(maxima.get(m.group(1),0), int(m.group(2)))
    return maxima

def allocate(borough, year, maxima):
    code=BOROUGH_CODES[borough]; maxima[code]=maxima.get(code,0)+1
    prefix='ADJ' if borough=='NYC-adjacent' else 'NYC'
    return f'{prefix}-{year}-{code}-{maxima[code]:06d}'

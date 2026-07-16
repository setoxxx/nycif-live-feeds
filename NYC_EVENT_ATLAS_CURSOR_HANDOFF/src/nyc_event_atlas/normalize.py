from __future__ import annotations
import re, unicodedata
from datetime import datetime
from urllib.parse import quote_plus
from .schema import EXPORT_COLUMNS

BOROUGH_MAP = {'Bronx':'The Bronx','Manhattan':'Manhattan','Brooklyn':'Brooklyn','Queens':'Queens','Staten Island':'Staten Island'}

def clean_text(value):
    if value is None: return 'Unknown'
    value = unicodedata.normalize('NFKC', str(value)).strip()
    value = re.sub(r'\s+', ' ', value)
    return value or 'Unknown'

def normalize_name(value):
    value = clean_text(value).lower()
    value = value.replace('&',' and ')
    value = re.sub(r'[^a-z0-9]+',' ',value)
    return re.sub(r'\s+',' ',value).strip()

def empty_record():
    return {c:'Unknown' for c in EXPORT_COLUMNS}

def maps_url(query, apple=False):
    base = 'https://maps.apple.com/?q=' if apple else 'https://www.google.com/maps/search/?api=1&query='
    return base + quote_plus(query)

def iso_parts(value):
    if not value: return ('Unknown','Unknown')
    dt = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return dt.date().isoformat(), dt.strftime('%H:%M')

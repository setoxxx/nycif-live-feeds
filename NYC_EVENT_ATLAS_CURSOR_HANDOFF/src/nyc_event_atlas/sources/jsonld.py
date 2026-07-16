from __future__ import annotations
import json
from bs4 import BeautifulSoup

EVENT_TYPES = {'Event','MusicEvent','Festival','ScreeningEvent','SportsEvent','TheaterEvent','DanceEvent','ExhibitionEvent','EducationEvent','BusinessEvent','FoodEvent'}

def _walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values(): yield from _walk(v)
    elif isinstance(value, list):
        for v in value: yield from _walk(v)

def extract_jsonld_events(html: str, page_url: str):
    soup = BeautifulSoup(html, 'lxml')
    out = []
    for script in soup.find_all('script', attrs={'type':'application/ld+json'}):
        text = script.string or script.get_text(' ', strip=True)
        try: data = json.loads(text)
        except Exception: continue
        for obj in _walk(data):
            typ = obj.get('@type')
            types = {typ} if isinstance(typ,str) else set(typ or [])
            if types & EVENT_TYPES:
                out.append({
                    'source_url': page_url,
                    'source_record_id': obj.get('@id') or obj.get('url'),
                    'name': obj.get('name'), 'start': obj.get('startDate'), 'end': obj.get('endDate'),
                    'status': obj.get('eventStatus'), 'location': obj.get('location'),
                    'organizer': obj.get('organizer'), 'offers': obj.get('offers'), 'raw': obj
                })
    return out

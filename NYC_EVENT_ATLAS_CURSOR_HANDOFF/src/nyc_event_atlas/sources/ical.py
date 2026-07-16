from __future__ import annotations
from datetime import datetime
from icalendar import Calendar
from dateutil.rrule import rrulestr

def _value(v):
    return v.dt if hasattr(v, 'dt') else v

def extract_ical_events(content: bytes, window_start: datetime, window_end: datetime, source_url: str):
    cal = Calendar.from_ical(content)
    out = []
    for component in cal.walk('VEVENT'):
        start = _value(component.get('dtstart'))
        end = _value(component.get('dtend')) if component.get('dtend') else start
        uid = str(component.get('uid',''))
        summary = str(component.get('summary',''))
        location = str(component.get('location',''))
        rule = component.get('rrule')
        starts = [start]
        if rule and isinstance(start, datetime):
            rule_text = rule.to_ical().decode()
            starts = list(rrulestr(rule_text, dtstart=start).between(window_start, window_end, inc=True))
        for occurrence in starts:
            if isinstance(occurrence, datetime) and not (window_start <= occurrence <= window_end): continue
            out.append({'source_url':source_url,'source_record_id':uid,'name':summary,'start':occurrence,'end':end,'location':location,'raw':component.to_ical().decode(errors='replace')})
    return out

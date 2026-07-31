from __future__ import annotations
import re
from datetime import date
from .normalize import empty_record, clean_text, iso_parts, maps_url

TYPE_MAP = {
 'Street Festival':('Street Fair','Street Festival'), 'Religious Event':('Religious Event','Religious Event'),
 'Parade':('Parade','Parade'), 'Single Block Festival':('Community Festival','Single Block Festival'),
 'Farmers Market':('Farmers Market','Farmers Market'), 'Open Street Partner Event':('Open Streets','Open Street Partner Event'),
 'Street Event':('Community Festival','Street Event'), 'Block Party':('Block Party','Public Block Party'),
 'Athletic Race / Tour':('Race','Athletic Race / Tour'), 'Open Culture':('Public Performance','Open Culture'),
 'Plaza Event':('Community Program','Plaza Event'), 'Plaza Partner Event':('Community Program','Plaza Partner Event'),
 'Special Event':('Community Program','Special Event')
}
REJECT = re.compile(r'^(soccer|softball|baseball|basketball$|tennis$|football|volleyball$|cricket$|picnic$|barbecue$|party$|kickball$|track and field$|miscellaneous$)', re.I)

def relevant(row):
    name = clean_text(row.get('event_name'))
    if REJECT.search(name): return False
    if name in {'Unknown','Celebration'} and row.get('event_type') == 'Special Event': return False
    return True

def map_permit(row, verified_on=None):
    rec = empty_record()
    start_date, start_time = iso_parts(row.get('start_date_time'))
    end_date, end_time = iso_parts(row.get('end_date_time'))
    borough = 'The Bronx' if row.get('event_borough') == 'Bronx' else clean_text(row.get('event_borough'))
    category, subcategory = TYPE_MAP.get(row.get('event_type'),('Community Program',clean_text(row.get('event_type'))))
    location = clean_text(row.get('event_location'))
    permit_id = clean_text(row.get('event_id'))
    rec.update({
      'EVENT_NAME':clean_text(row.get('event_name')), 'EVENT_STATUS':'Permitted',
      'ANNUAL_OR_RECURRING':'Unknown','FIRST_YEAR':'Unknown','CATEGORY':category,'SUBCATEGORY':subcategory,
      'START_DATE':start_date,'END_DATE':end_date,'DAY_OF_WEEK':'Unknown','START_TIME':start_time,'END_TIME':end_time,
      'TIME_NOTES':'Permit times may include setup and breakdown rather than public program hours.',
      'BOROUGH':borough,'NEIGHBORHOOD':'Unknown','VENUE':location,'FULL_ADDRESS':location,
      'GOOGLE_MAPS_URL':maps_url(location),'APPLE_MAPS_URL':maps_url(location,True),
      'PERMIT_ID':permit_id,'PERMIT_AGENCY':clean_text(row.get('event_agency')),
      'PRIMARY_SOURCE':'https://data.cityofnewyork.us/City-Government/NYC-Permitted-Event-Information/tvpp-9vvx',
      'SOURCE_CONFIDENCE':'High','LAST_VERIFIED':verified_on or date.today().isoformat(),
      'RESEARCH_NOTES':f"Raw permit location: {location}; street side: {clean_text(row.get('event_street_side'))}; closure: {clean_text(row.get('street_closure_type'))}; community board: {clean_text(row.get('community_board'))}; precinct: {clean_text(row.get('police_precinct'))}; CEMSID: {clean_text(row.get('cemsid'))}."
    })
    return rec

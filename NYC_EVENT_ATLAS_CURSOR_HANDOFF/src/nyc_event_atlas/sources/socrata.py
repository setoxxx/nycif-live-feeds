from __future__ import annotations
import os
from datetime import date, timedelta
from ..http_client import AtlasHttpClient

RELEVANT_TYPES = [
 'Street Festival','Religious Event','Parade','Single Block Festival','Farmers Market',
 'Open Street Partner Event','Street Event','Block Party','Athletic Race / Tour',
 'Open Culture','Plaza Event','Plaza Partner Event','Special Event'
]

class SocrataEventSource:
    def __init__(self, dataset_id='tvpp-9vvx', domain='data.cityofnewyork.us', client=None):
        self.dataset_id = dataset_id
        self.domain = domain
        self.client = client or AtlasHttpClient()
        self.endpoint = f'https://{domain}/resource/{dataset_id}.json'

    def fetch(self, start: date, end: date, limit=50000):
        type_list = ','.join("'" + x.replace("'", "''") + "'" for x in RELEVANT_TYPES)
        end_exclusive = end + timedelta(days=1)
        where = (
            f"start_date_time >= '{start.isoformat()}T00:00:00.000' AND "
            f"start_date_time < '{end_exclusive.isoformat()}T00:00:00.000' AND "
            f"event_type in({type_list})"
        )
        # SoQL requires star selections first; `:id,:updated_at,*` returns HTTP 400.
        params = {
            '$select': '*,:id,:updated_at',
            '$where': where,
            '$order': 'start_date_time,event_id',
            '$limit': str(limit),
        }
        token = os.getenv('SOCRATA_APP_TOKEN')
        if token: self.client.session.headers['X-App-Token'] = token
        response, meta = self.client.get(self.endpoint, params=params)
        return response.json(), meta

#!/usr/bin/env python3
"""Build ADR-0013 approximate event GeoJSON without promoting review records."""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
APPROVED_MANIFEST = ROOT / 'data/schema-v1-discovery/approved/manifest.json'
REVIEW_MANIFEST = ROOT / 'data/schema-v1-discovery/review/manifest.json'
OUTPUT = ROOT / 'data/schema-v1-discovery/approximate/approximate-stacks.json'
PARK_LOOKUP = ROOT / 'data/park_centroids.json'

from enigma.shadow2.location_evidence import classify_location_evidence
from nycif.normalize.facility_resolver import resolve_facility_anchor
from nycif.normalize.park_geometry import load_park_lookup

# Interior borough anchors derived from NYC DCP Borough Boundaries (nybb, 7t3b-ywvw).
# They are municipality-level disclosure anchors, never event-location claims.
BOROUGH_ANCHORS = {
    'Manhattan': {'lat': 40.7831000, 'lng': -73.9712000},
    'Brooklyn': {'lat': 40.6782000, 'lng': -73.9442000},
    'Queens': {'lat': 40.7282000, 'lng': -73.7949000},
    'Bronx': {'lat': 40.8448000, 'lng': -73.8648000},
    'Staten Island': {'lat': 40.5795000, 'lng': -74.1502000},
}
BOROUGH_ALIASES = {'mn':'Manhattan','manhattan':'Manhattan','new york':'Manhattan','bk':'Brooklyn','brooklyn':'Brooklyn','qn':'Queens','q':'Queens','queens':'Queens','bx':'Bronx','bronx':'Bronx','the bronx':'Bronx','si':'Staten Island','staten island':'Staten Island'}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def page_rows(manifest_path: Path) -> Iterable[dict[str, Any]]:
    manifest = load_json(manifest_path)
    root = manifest_path.parent / 'pages'
    pages = manifest.get('pages') if isinstance(manifest, dict) else []
    for item in pages or []:
        name = item.get('page') or f"{str(item.get('cursor') or '').replace('.json','')}.json"
        payload = load_json(root / name)
        for row in payload.get('events', []):
            if isinstance(row, dict):
                yield row


def canonical_borough(value: Any) -> str | None:
    raw = value[0] if isinstance(value, list) and value else value
    return BOROUGH_ALIASES.get(' '.join(str(raw or '').strip().casefold().split()))


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    src = row.get('source') if isinstance(row.get('source'), dict) else {}
    return str(src.get('dataset') or row.get('source_dataset') or ''), str(src.get('source_event_id') or row.get('source_event_id') or '')


def event_day(row: dict[str, Any]) -> str:
    nycif = row.get('nycif') if isinstance(row.get('nycif'), dict) else {}
    return str(nycif.get('event_date') or row.get('start_date_time') or row.get('date') or '')[:10]


def feature(row: dict[str, Any], *, lat: float, lng: float, approximation_class: str, anchor_name: str, anchor_id: str, coordinate_source: str) -> dict[str, Any]:
    dataset, source_event_id = source_parts(row)
    return {
        'type': 'Feature',
        'id': str(row.get('id') or f'{dataset}:{source_event_id}@{event_day(row)}'),
        'geometry': {'type': 'Point', 'coordinates': [round(float(lng), 7), round(float(lat), 7)]},
        'properties': {
            'source_group': 'approximate-clustered-events',
            'approximation_class': approximation_class,
            'coordinate_status': 'approximate',
            'coordinate_precision': approximation_class,
            'coordinate_source': coordinate_source,
            'display_disposition': 'approximate_marker',
            'promotion_allowed': False,
            'production_feed': False,
            'public_map_modified': False,
            'title': row.get('title') or 'Untitled event',
            'borough': canonical_borough(row.get('borough') or row.get('event_borough')),
            'original_location': row.get('location') or row.get('display_location'),
            'event_date': event_day(row),
            'start_date_time': row.get('start_date_time'),
            'end_date_time': row.get('end_date_time'),
            'category': row.get('category') or 'general',
            'source_dataset': dataset,
            'source_event_id': source_event_id,
            'anchor_name': anchor_name,
            'anchor_id': anchor_id,
            'disclaimer': 'Approximate location',
            'list_view_href': '#event-list',
        },
    }


def build(approved_manifest: Path=APPROVED_MANIFEST, review_manifest: Path=REVIEW_MANIFEST, park_lookup_path: Path=PARK_LOOKUP) -> dict[str, Any]:
    approved_count = sum(1 for _ in page_rows(approved_manifest))
    lookup = load_park_lookup(park_lookup_path)
    features=[]
    counts=Counter()
    excluded=Counter()
    for row in page_rows(review_manifest):
        nycif = row.get('nycif') if isinstance(row.get('nycif'), dict) else {}
        if str(nycif.get('coordinate_status') or row.get('coordinate_status') or '') != 'list_only':
            excluded['not_list_only'] += 1; continue
        try: tier=classify_location_evidence(row).tier.value
        except Exception: excluded['classification_failed'] += 1; continue
        if tier == 'approximate_area':
            borough=canonical_borough(row.get('borough') or row.get('event_borough'))
            anchor=BOROUGH_ANCHORS.get(borough or '')
            if not anchor: excluded['approximate_area_without_canonical_borough'] += 1; continue
            features.append(feature(row, lat=anchor['lat'], lng=anchor['lng'], approximation_class='municipality_level', anchor_name=borough, anchor_id=f'borough:{borough}', coordinate_source='nyc_dcp_borough_boundary_interior_anchor'))
            counts['approximate_area'] += 1
            continue
        if tier == 'unresolved':
            probe=dict(row); probe['evidence_tier']='unresolved'
            hit=resolve_facility_anchor(probe, lookup=lookup)
            if hit:
                features.append(feature(row, lat=hit['latitude'], lng=hit['longitude'], approximation_class='park_level_anchor', anchor_name=str(hit.get('park_name') or hit.get('park_query_name') or 'NYC park'), anchor_id=f"park:{hit.get('park_id')}", coordinate_source='dpr_parks_properties_centroid'))
                counts['park_level_anchor'] += 1
            else: excluded['unresolved'] += 1
        else: excluded[tier] += 1
    features.sort(key=lambda f:(f['properties']['approximation_class'], f['properties']['anchor_id'], f['properties']['event_date'], f['id']))
    return {
        'type':'FeatureCollection',
        'schema_version':'adr-0013-approximate-stacks-v1',
        'source_contracts': {
            'approximate-clustered-events': {'cluster': True, 'classes':['municipality_level','park_level_anchor']},
            'approximate-facility-events': {'cluster': False, 'classes':['certified_facility'], 'status':'empty_future_stub'},
        },
        'safety': {'map_ready':False,'map_safe':False,'promotion_allowed':False,'automatic_promotion':False,'unresolved_geometry_emitted':False},
        'counts': {
            'approved_records_read': approved_count,
            'approximate_area': counts['approximate_area'],
            'park_level_anchor': counts['park_level_anchor'],
            'certified_facility': 0,
            'visible_approximate_occurrences': len(features),
            'excluded': dict(sorted(excluded.items())),
        },
        'features': features,
    }


def main(argv=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--approved-manifest', type=Path, default=APPROVED_MANIFEST)
    ap.add_argument('--review-manifest', type=Path, default=REVIEW_MANIFEST)
    ap.add_argument('--park-lookup', type=Path, default=PARK_LOOKUP)
    ap.add_argument('--output', type=Path, default=OUTPUT)
    args=ap.parse_args(argv)
    payload=build(args.approved_manifest,args.review_manifest,args.park_lookup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    c=payload['counts']
    ok=c['approximate_area']==1292 and c['park_level_anchor']==325 and c['visible_approximate_occurrences']==1617 and c['excluded'].get('unresolved')==170
    print(json.dumps({'qa_pass':ok,'output':str(args.output),**c},indent=2))
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())

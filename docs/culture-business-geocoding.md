# Culture business geocoding (Enigma bridge)

Enigma can natively geocode **Culture Business Discovery** candidates produced
by Borg (`nycif-data-pipeline`), so there is one geocoder, not two.

`scripts/geocode_culture_business_candidates.py` reads Borg's
`location-candidates.json` and resolves each address through the **same** NYC
GeoSearch path as `scripts/geocode_unfilled_gps_proposals.py` — it reuses that
module's `geosearch` and `pick_best_result` helpers (NYC bounds + confidence
floor of 0.5).

## Flow

```text
Borg: culture/pipeline/geocode_candidates.py  →  location-candidates.json
Enigma: geocode_culture_business_candidates.py →  <proposals>.json  (staging, pending review)
Human: copy approved rows → Borg culture/sample_sources/geocoded_locations.sample.json (approved: true)
Borg: normalize_businesses applies approved coords → business becomes mappable
```

## Safety (same discipline as the sibling geocoder)

- Every proposal is `manual_review_status: "pending"`, `promotion_allowed:
  false`, `approved: false`. Nothing is auto-applied.
- Only NYC-bounds hits at confidence ≥ 0.5 become `proposed_needs_review`;
  everything else is `unresolved_no_confident_match`.
- Output is staging only (`public_safe: false`).

## Usage

```bash
python3 scripts/geocode_culture_business_candidates.py \
  --input path/to/location-candidates.json \
  --output data/culture_business_geosearch_proposals.json
```

Code name: **Enigma** is this repo's normalization/processing system; **Borg** is
the aggregation pipeline. See `nycif-data-pipeline/docs/CODENAMES.md`.

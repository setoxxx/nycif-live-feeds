# NYCIF Event Card V2 — Public Data and Media Contract

Status: production workstream draft

Owner: Howard Weiss

Frontend consumer: `setoxxx/nycif-field-desk`

## Purpose

Provide backward-compatible public fields for image-led map event cards, exact-venue secondary-event selection, and clearly separated sponsored placement data.

Existing event records must remain valid when every field in this document is absent.

## Event additions

```json
{
  "venue_identity": {
    "canonical_venue_id": "parks:central-park:rumsey-playfield",
    "canonical_venue_name": "Rumsey Playfield",
    "location_confidence": "verified"
  },
  "display_media": {
    "primary": {
      "image_url": "https://...",
      "thumbnail_url": "https://...",
      "alt": "People watching an outdoor performance in the park in the 1970s.",
      "caption": "Archive photo of outdoor performance activity in the park, 1974.",
      "creator": "",
      "source_name": "",
      "source_url": "https://...",
      "rights_statement": "",
      "license_code": "public-domain",
      "license_url": "https://...",
      "date_created_display": "1974",
      "location_match": "venue",
      "activity_match": true,
      "is_archival": true,
      "is_ai_generated": false,
      "review_status": "approved",
      "reviewed_by": "",
      "reviewed_at": "2026-08-05T00:00:00Z",
      "crop_focus_x": 0.5,
      "crop_focus_y": 0.5
    }
  }
}
```

## Validation enums

### `venue_identity.location_confidence`

- `verified`
- `approximate`
- `pending`

Only `verified` records may participate in same-venue secondary-event resolution.

### `display_media.primary.location_match`

- `exact`
- `venue`
- `neighborhood`
- `borough`
- `activity_only`
- `fallback`

### `display_media.primary.review_status`

- `approved`
- `needs_review`
- `rejected`

Only `approved` media may be emitted to the public map feed.

## Public media gate

A media record must be excluded from public output when any of the following is true:

- `review_status` is not `approved`.
- `rights_statement` is missing.
- `source_url` is missing.
- `alt` is missing.
- `image_url` or `thumbnail_url` is missing.
- `is_ai_generated` is true while `is_archival` is also true.
- the URL does not use HTTPS.
- the asset is known broken or unstable.
- the licensing record prohibits the intended use.

The gate must fail closed for the image only. It must not suppress an otherwise valid event record.

## Approved media manifest

Use a separate generated manifest so images can be reused by place or activity without copying full rights metadata into every source record.

Suggested path:

`data/schema-v1/media/approved-event-media.json`

Suggested shape:

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-08-05T00:00:00Z",
  "items": [
    {
      "media_id": "nycif-media-000001",
      "event_ids": ["event-id"],
      "place_keys": ["parks:central-park:rumsey-playfield"],
      "activity_keys": ["outdoor-music"],
      "primary": {}
    }
  ]
}
```

Internal research notes, rejected candidates, download receipts, and legal-review comments must remain outside public feeds.

## Secondary event resolver

The frontend may calculate the display rail, but the backend should emit enough stable identity to make the result deterministic.

Eligibility order:

1. Same `canonical_venue_id`, same local calendar date, `location_confidence=verified`.
2. Same `canonical_venue_id`, selected public date window, `location_confidence=verified`.
3. Same exact verified coordinates only when no canonical venue ID exists and the location is not an approximate stack.

Ranking within eligible events:

1. Earliest upcoming start after the selected event.
2. Highest public editorial priority if tied.
3. Stable event ID lexical order as deterministic final tie-breaker.

Never infer same venue from borough, neighborhood, park name substring, or approximate location.

## Sponsored placement feed

Sponsored campaigns must be stored separately from event records.

Suggested path:

`data/schema-v1/sponsored/event-card-placements.json`

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-08-05T00:00:00Z",
  "campaigns": [
    {
      "campaign_id": "",
      "advertiser_name": "",
      "label": "Sponsored",
      "headline": "",
      "destination_url": "https://...",
      "image_url": "https://...",
      "starts_at": "",
      "ends_at": "",
      "boroughs": [],
      "category_keys": [],
      "approval_status": "approved",
      "creative_rights_confirmed": true
    }
  ]
}
```

A real eligible same-venue event takes priority over a sponsored placement. Sponsored records must not affect event verification, medals, ranking, location confidence, or publication status.

## Public disclosure fields

The frontend should be able to display one concise disclosure from structured media fields:

- `Archive photo, 1974`
- `Historical photo of the park`
- `Archive image; not the current event`

Do not claim an exact year unless the approved rights record supports it.

## Test fixtures required

- approved exact-location archival image
- approved activity-only archival image
- missing rights statement
- rejected image
- AI fallback illustration
- broken image URL
- single verified event
- two same-venue verified events
- three same-venue verified events
- same coordinates but approximate records
- sponsored placement eligible
- sponsored placement expired

## Release gate

No public media or sponsored feed reaches `main` until:

- schema tests pass
- public/private field separation is verified
- media-rights validation passes
- same-venue resolver tests pass
- frontend feature-flag QA passes
- Howard Weiss authorizes release

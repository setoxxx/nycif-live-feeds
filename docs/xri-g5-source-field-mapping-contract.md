# XRI-G5 Source Field Mapping Contract

Phase: XRI-G5
Mode: planning-only contract
Production allowed: false

This contract maps the MVP source datasets into the XRI registry candidate schema before any live extractor work. It defines source-owned identity, candidate identity keys, field handling, ambiguity flags, and Parks table relationships without creating a live joiner.

## Hard boundary

This is documentation and reporting only. It does not fetch live data, geocode, approve candidates, promote candidates, create a registry database, create an importer, change production feeds, change public map runtime, change WordPress, change iframe/embed settings, change scheduled workflows, or read/write `data/location_cache.json`.

## Candidate schema targets

Core candidate fields:

- `candidate_id`
- `source_dataset_id`
- `source_name`
- `source_record_id`
- `source_owned_key`
- `candidate_identity_key`
- `title`
- `description`
- `category`
- `borough`
- `location_text`
- `location_hint`
- `event_start`
- `event_end`
- `source_url`
- `extracted_at`
- `production_allowed`
- `approval_status`
- `geocode_status`
- `promotion_status`
- `required_field_status`
- `ambiguity_flags`

All candidates emitted by any future implementation based on this contract must remain blocked by default:

- `production_allowed: false`
- `approval_status: candidate_only`
- `geocode_status: not_geocoded`
- `promotion_status: blocked`

## Identity rules

### Source-owned ID

Use the most stable source-owned primary key available from the dataset. If a source lacks a stable official ID, derive a source-owned key from source dataset ID plus a stable source row identifier already present in the dataset. Do not use review rank, row order, or display order as an identity key.

### Candidate identity key

Candidate identity keys are deterministic strings built from:

- `source_dataset_id`
- `source_record_id` or source-owned ID
- normalized title
- normalized event start date where available
- normalized location text where available

The candidate identity key is for candidate deduplication and review grouping only. It is not approval, geocoding, cache, or production-publish authority.

## Source mapping

### tvpp-9vvx — NYC Permitted Event Information

Purpose: street activity, permitted events, closures, festivals, parades, markets, and similar events.

Required target fields:

- `source_dataset_id`: `tvpp-9vvx`
- `source_name`: NYC Permitted Event Information
- `source_record_id`: stable permit/event identifier if present; otherwise source row identifier
- `title`: event name or permit/event description
- `location_text`: source location, route, block, or street segment text
- `event_start`: event start date/time if present
- `event_end`: event end date/time if present

Optional target fields:

- `borough`
- `category`
- `description`
- `source_url`
- `location_hint`

Missing/ambiguous handling:

- If location is a route, corridor, or intersection, set ambiguity flag `route_or_intersection_location`.
- If date exists but time is missing, set `time_missing`.
- If borough is missing or inferred only from text, set `borough_uncertain`.
- Do not geocode route text.

### fudw-fgrp — Parks Event Listing

Purpose: primary Parks event listing records.

Required target fields:

- `source_dataset_id`: `fudw-fgrp`
- `source_name`: Parks Event Listing
- `source_record_id`: Parks event ID or source row ID
- `title`: Parks event name
- `event_start`: event start date/time if present
- `event_end`: event end date/time if present

Optional target fields:

- `description`
- `category`
- `borough`
- `location_text`
- `location_hint`
- `source_url`

Missing/ambiguous handling:

- If a Parks event references a location/facility ID rather than plain address text, set `parks_location_reference_present`.
- If no location text is present, set `location_missing`.
- Do not join to Parks location tables in this phase.

### cpcm-i88g — Parks Event Locations

Purpose: Parks event location reference table.

Contract role: supporting reference only.

Required contract fields:

- source location ID or facility/location key
- location display name
- borough or park context if present
- location descriptor if present

Mapping behavior:

- This table can provide `location_text` or `location_hint` for future Parks candidates when a listing references the same source-owned location key.
- It must not be used to geocode in this phase.
- It must not be joined live in this phase.

Ambiguity flags:

- `parks_location_reference_only`
- `parks_location_join_required_future_phase`
- `location_geometry_not_authorized`

### xtsw-fqvh — Parks Event Categories

Purpose: Parks category reference table.

Contract role: supporting reference only.

Required contract fields:

- source category ID or category key
- category display name

Mapping behavior:

- This table may normalize future `category` values for Parks candidates.
- It must not be joined live in this phase.
- Missing category joins must not block candidate creation if the primary listing is otherwise valid.

Ambiguity flags:

- `parks_category_reference_only`
- `category_join_required_future_phase`

### 6v4b-5gp4 — Public Programs Division Special Events

Purpose: agency or public-program special event records.

Required target fields:

- `source_dataset_id`: `6v4b-5gp4`
- `source_name`: Public Programs Division Special Events
- `source_record_id`: stable source event ID or row ID
- `title`: event/program title
- `location_text`: source location text if present
- `event_start`: event start if present
- `event_end`: event end if present

Optional target fields:

- `description`
- `borough`
- `category`
- `source_url`
- `location_hint`

Ambiguity flags:

- `agency_program_location_uncertain`
- `time_missing`
- `location_missing`

### 3vyj-dkjt — Safety Events

Purpose: safety-related event records.

Required target fields:

- `source_dataset_id`: `3vyj-dkjt`
- `source_name`: Safety Events
- `source_record_id`: stable source event ID or row ID
- `title`: safety event title or description
- `event_start`: event start if present

Optional target fields:

- `event_end`
- `description`
- `borough`
- `category`
- `location_text`
- `source_url`

Ambiguity flags:

- `safety_event_context_required`
- `location_missing`
- `time_missing`
- `sensitive_context_review_required`

## Parks relationship contract

Parks MVP datasets must be treated as one future enriched Parks Events layer, but XRI-G5 does not create the joiner.

Future relationship direction:

- `fudw-fgrp` is the primary event listing source.
- `cpcm-i88g` is a location reference source.
- `xtsw-fqvh` is a category reference source.

Future joins must use stable Parks source-owned keys only. They must not use row order, review rank, display order, or fuzzy title matching as join authority.

## Location handling without geocoding

- Preserve source location text exactly enough for audit.
- Store normalized location text separately for identity/deduplication.
- Use `location_hint` for non-coordinate context such as park name, borough, route, plaza, or facility label.
- Set ambiguity flags instead of guessing.
- Do not call geocoding APIs.
- Do not read or write `data/location_cache.json`.
- Do not approve, promote, or publish a candidate based on text-only location handling.

## Required-field status

Candidate rows must have one of these statuses:

- `complete_for_review`
- `missing_location`
- `missing_time`
- `missing_title`
- `missing_source_id`
- `supporting_reference_only`
- `needs_source_schema_review`

## Next recommended gate

XRI-G6 should create a static fixture-only mapping validator contract or prototype that validates sample records against this mapping. It should still be read-only and sample-only. It must not fetch live source data, geocode, approve, promote, write production feeds, modify public map runtime, or touch `data/location_cache.json`.

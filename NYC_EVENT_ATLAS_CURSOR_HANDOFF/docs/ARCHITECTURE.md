# Architecture

## Why the database needs layers

A public event can appear in a permit feed, an organizer page, a parish bulletin, a BID calendar, a PDF vendor schedule, and media listings. The system must preserve evidence separately from the canonical event row.

## Recommended layers

### 1. Source registry
Tracks every monitored domain or feed, its acquisition method, authority level, crawl policy, update frequency, and last result.

### 2. Raw evidence store
Immutable HTTP bodies, downloaded PDFs/ICS/CSV/JSON, screenshot references, hashes, headers, retrieval timestamps, and parser version.

### 3. Extracted candidates
One candidate per discovered occurrence before normalization. Preserve the source-native title, date text, location text, and source record ID.

### 4. Normalized candidates
Candidates mapped into the 59-field schema, but not yet canonical.

### 5. Canonical events
Accepted event occurrences with permanent IDs.

### 6. Event series
Stable identity for recurring programs such as Queens Night Market or a yearly feast.

### 7. Event-source links
Many-to-many evidence links with field-level support notes.

### 8. Update ledger
Explicit changes to existing permanent IDs. The cumulative export applies the update while Part files retain the update row.

### 9. Review queue
Ambiguous duplicates, conflicts, weak sources, unresolved TBA items, and geocoding failures.

## Pipeline

```text
source registry
    -> acquisition
    -> raw snapshots
    -> extractor
    -> source-native candidates
    -> normalization
    -> relevance filter
    -> exact duplicate check
    -> fuzzy candidate matching
    -> review / accept / reject
    -> enrichment
    -> validation
    -> Part export + cumulative export + manifest
```

## Update semantics

- New occurrence: allocate a new borough-specific `EVENT_ID`.
- Existing occurrence changed: create an update-ledger row referencing the permanent ID.
- Same series, different date/location: new occurrence with existing `SERIES_ID`.
- Event cancelled: update status; do not delete history.
- Source disappears: retain event but flag source health and require reverification.

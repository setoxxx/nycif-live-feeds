# Deduplication Strategy

## Stage 1: exact identifiers

Automatically match when any of these are equal and non-empty:

- same permit ID
- same source-native UID
- same organizer event ID
- same canonical URL with same occurrence date

## Stage 2: exact occurrence key

Build:

```text
normalized_title | start_date | normalized_venue_or_street | normalized_organizer
```

Normalization removes punctuation, legal suffixes, ordinal noise and common filler words, but must not remove saints, neighborhoods, dates, cultural identities or numbered series names.

## Stage 3: fuzzy candidate generation

Compare only records sharing at least one blocking key:

- same borough and date
- same ZIP and date ±1 day
- same organizer and month
- same permit location
- same normalized title prefix

Suggested scoring:

```text
40% title token-set similarity
20% location similarity
15% organizer similarity
15% date proximity
10% source/permit identity
```

Recommended actions:

- 95–100: auto-match only if date and borough are compatible
- 88–94: manual review
- 75–87: possible series relationship; do not merge
- below 75: new candidate

## Common false merges

- parade versus accompanying festival
- same event name in different boroughs
- recurring weekly market occurrences
- same movie screened at different parks
- church feast versus religious procession
- multi-date concert series
- event announcement page versus actual occurrence

## Common missed duplicates

- abbreviated saint names
- sponsor prefixes
- punctuation and apostrophe differences
- route endpoint changes
- organizer renaming
- `Festival`, `Fest`, `Fair`, and `Street Fair` variants
- Spanish/English title pairs

The system should present candidate pairs and evidence to a reviewer rather than optimizing for a fully automatic merge rate.

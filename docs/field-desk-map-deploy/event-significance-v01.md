# Event significance v01

Deterministic, transparent, evidence-based Gold / Silver / Bronze labels for the Field Desk public map.

**Integrity rule:** Event significance is evidence-based and cannot be purchased.

This is a provisional Field Desk classifier (`SIGNIFICANCE_VERSION = event-significance-v01`). It is not a future app-facing paid designation service.

## Inputs consulted

- Canonical `significance_tier` when already Gold/Silver/Bronze
- Title and event type
- Category
- Duration from start/end timestamps
- `street_closure_type`
- `expected_crowd_score`, `priority_score`, `crowd_level`
- `major_reason`, `photo_pick`, `field_default`, major-feed assignment

## Inputs ignored

Sponsorship, payment, advertiser status, organizer identity, and any paid-tier fields are ignored and cannot change the result.

## Exclusions (remain untiered)

- Titles that are only “closed” / closure / maintenance
- Routine practices, miscellaneous permits, generic field reservations
- Ordinary `Sport - Youth` / `Sport - Adult` rows without additional public-impact evidence

## Thresholds (conservative)

| Tier | Minimum score |
| --- | ---: |
| Gold | 85 |
| Silver | 50 |
| Bronze | 28 |
| Untiered | below 28 |

## Representative examples (staged feed sample)

| Example | Evidence | Result |
| --- | --- | --- |
| World Cup Activation (plaza + long duration) | landmark title, plaza impact, duration | Gold |
| Block party with full street closure | civic pattern + closure | often Gold/Silver |
| Farmers market with curb/sidewalk impact | market type + closure | often Silver/Bronze |
| Baseball Little League (`Sport - Youth`) | ordinary reservation | Untiered |
| Title `closed` / maintenance day | exclusion rules | Untiered |
| Row with `significance_tier: Gold` | canonical override | Gold regardless of fallback score |

## Observed distribution on current staged feed

Approximate after threshold calibration:

- Gold: ~161
- Silver: ~295
- Bronze: ~224
- Untiered: ~32,165 of 32,845

Most of the 32k staged rows remain untiered by design.

## UI

- Gold / Silver / Bronze filters (all on by default)
- Optional “Significance only” hides untiered rows
- Badges on markers, list cards, and popups (text + color)
- Popup “Why this tier” lists plain-language reasons + integrity statement

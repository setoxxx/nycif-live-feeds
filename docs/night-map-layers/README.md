# NYC In Focus Tonight Auxiliary Map Layers — LOCKED BEHAVIOR

Status: production behavior contract
Locked: 2026-09-01
Runtime authority: Supabase project `oggwpvdirkrnzoolparx`
Public map: native app via `nycif-native-map-feed` `chip_rows.night` → `nycif-night-layers`. WordPress `/map/` is not a live event destination.

## Purpose

These are auxiliary overlays inside **Tonight**. They are not event records and must not be merged into the canonical event corpus.

The user-facing behavior is intentionally stable. Maintenance jobs may refresh source data, but must not redesign the controls, icons, labels, eligibility semantics, or event-map behavior without an explicit product decision.

## Locked controls

Tonight exposes exactly these auxiliary choices:

- 🍹 **It's 5 PM Somewhere** — nightlife/party activity signal. Its ranking/eligibility authority is recent NYC 311 noise/party complaint activity; liquor-license data may be used as venue/reference enrichment, not as the sole activity signal.
- 🌿 **Legal Cannabis Shops** — currently active, operational, legal NYC cannabis retail locations from NYS Office of Cannabis Management authority.
- 🍸 **Liquor Stores** — current NYC liquor-store licenses from NYS Liquor Authority authority.

Turning an auxiliary layer off returns to Tonight's event pins. Auxiliary layers do not delete, rewrite, or expire event records.

## Refresh cadence

Reference data is deliberately refreshed separately from map interaction:

- Cannabis license authority: **monthly**. Detect newly active/operational licenses and licenses no longer active/operational. Add/remove map eligibility accordingly. Do not treat a temporary source outage as a license revocation.
- Liquor-store license authority: **monthly**. Detect newly current licenses and licenses no longer current. Add/remove map eligibility accordingly. Do not treat a temporary source outage as a license loss.
- It's 5 PM Somewhere activity authority: **weekly**. Refresh recent 311 noise/party complaint evidence and recompute eligible/ranked nightlife locations. This layer is evidence of recurring nightlife activity, not a claim that a venue is currently violating a rule.

## Runtime rule

**The public map must never perform corpus construction, mass geocoding, or full-license reconciliation when a user taps a layer.**

User interaction reads a precomputed/cached GeoJSON layer. Heavy source fetches, geocoding, deduplication, license reconciliation, and 311 aggregation belong in maintenance routines. A failed maintenance refresh must leave the last known-good layer available.

Mobile stability takes priority over displaying every point simultaneously. Rendering may be viewport-bounded, canvas-based, or otherwise performance-limited while preserving all eligible records in the underlying cached authority.

## Source authorities

- Cannabis: NYS Office of Cannabis Management current license authority (`jskf-tt3q` / Buy Legal NY).
- Alcohol licenses: NYS Liquor Authority current active licenses (`9s3h-dpkz`).
- Nightlife activity: NYC 311 noise/party complaint data, using documented complaint-type/descriptor filters and a bounded recent-history window.

## Change-control guardrail

Before modifying this subsystem, an engineer or agent must answer all of these:

1. Is the change only a source-data refresh or bug/performance repair?
2. Does it preserve the three labels, icons, and Tonight-only interaction?
3. Does it preserve monthly cannabis/liquor refresh and weekly 311 activity refresh?
4. Does it avoid changing canonical event ingestion?
5. Does it preserve last-known-good data if an upstream source fails?
6. Has mobile map stability been tested?

If any answer is **no**, stop and require an explicit product decision before changing production behavior.

## Current production implementation note

The first `nycif-night-layers` implementation fetched upstream license data on demand and geocoded cannabis addresses during a user's request. This is not the locked target architecture because it can cause long cold requests and mobile rendering pressure. The production repair should move that work to maintenance refreshes and make the public endpoint a fast cached reader.

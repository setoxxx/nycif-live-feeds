# BORG / ENIGMA Event Intelligence Reconciliation — 2026-08-09

## Purpose

Unify the NYCIF event-data authority across `nycif-data-pipeline`, `nycif-event-radar`, and `nycif-live-feeds` so the public map is fed by current, trusted, auditable event data instead of parallel stale pipelines.

## Current observed split

### nycif-data-pipeline
- owns scheduled daily Socrata event pulls;
- current documented blocking sources: NYC Permitted Event Information (`tvpp-9vvx`) and NYC Parks Public Events (`w3wp-dpdi`);
- performs normalization, geocoding QA, public GeoJSON build, dedupe, display QA, prepublish gate, and rollback-safe live release preparation;
- checked-in `public/feeds/events-current.geojson` and `public/feeds/live/events-live.geojson` are currently empty on main;
- latest commit matching `Update daily events pipeline output` observed during review is 2026-07-18.

### nycif-event-radar
- broader weekly/manual discovery and editorial intake;
- source manifest currently contains at least one stale assumption: NYC Permitted Event Information is marked manual/unconfirmed even though Data Pipeline already uses `tvpp-9vvx` as production/blocking;
- should remain discovery/editorial intake, not bypass production QA.

### nycif-live-feeds
- is the actual public-feed repository consumed by Field Desk;
- Field Desk README points to `nycif_major_radar_map_events.json` and `nycif_all_radar_map_events.json` here;
- live-sync workflow is manual `workflow_dispatch` only and requires `allow_live_fetch=yes`;
- workflow performs broad source sync, staging, location/GPS, supplemental review, schema projection, coverage audits and backend reliability gating;
- committed backend reliability report says PASS, but its `generated_at_utc` is 2026-07-14, so it is stale health evidence;
- repository search confirms official Dominican Day Parade Event ID `957653` appears in internal/digest artifacts, but this alone is not proof that the current public map feed exposes the event.

## Staff assignments

### Bianca Torres — BORG Source Intelligence & Rights
Create one cross-repo source authority table:
- source ID;
- provider;
- trust tier;
- owning repo/adapter;
- retrieval method;
- current activation state;
- freshness SLA;
- public-map eligibility;
- attribution/rights constraints.

No source should be independently active in two ingestion paths unless one is explicitly a corroborating source.

### Grace Lin — ENIGMA Engineering Intelligence
Record contradictions and stale knowledge:
1. Event Radar `tvpp-9vvx` manual/unconfirmed vs Data Pipeline production/blocking;
2. Data Pipeline daily workflow documented as scheduled but latest observed output commit 2026-07-18;
3. Live Feeds backend gate marked PASS but evidence generated 2026-07-14;
4. Data Pipeline checked-in current/live GeoJSON empty while Live Feeds contains large staged/test event stores;
5. Event ID `957653` present in Live Feeds evidence/digest layer but public-map projection not yet proven.

Each contradiction needs owner, resolution test, and supersession record.

### Elena Park — Systems Integration
Define canonical flow and ownership:

`trusted source -> one authoritative adapter -> raw observation -> canonical normalization/reconciliation -> ENIGMA evidence -> location authority -> public projection -> nycif-live-feeds -> Field Desk / public map`

Decide which existing repository owns each step and remove duplicate authority, not historical evidence.

### Sofia Marin — Contracts & Provenance
Create/align a shared versioned event contract across repositories. Required fields include stable source ID, source record ID, canonical event ID, source tier, provenance, source updated time, ingestion time, normalized start/end/timezone, status/cancellation, location state, geometry provenance, projection eligibility, and schema/hash/version.

### Rafael Alvarez — Evidence & Storage
Trace Event ID `957653` end to end:
- authoritative NYC source row;
- raw stored observation;
- normalized/canonical record;
- location decision;
- public projection;
- final live-feed object;
- map-consumer record.

Every hop must retain a deterministic ID/provenance reference. Missing hop = explicit gap.

### Nina Kovacs — Runtime Continuity
Replace stale-green health with freshness-aware health. A gate report older than its SLA must classify STALE/UNKNOWN, never healthy green. Ensure source failures preserve prior-known-good public output without pretending it is fresh.

### Evan Brooks — Release Engineering
Determine why scheduled Data Pipeline output commits stopped after 2026-07-18 while other repository automation continued. Inspect workflow activation, Actions state, secrets/token requirements, branch protection/push behavior, artifact failures, and prepublish blocks. Do not rerun or publish production data until exact failure mode is known and current authorization permits it.

### Nadia Brooks — Product Security
Review cross-repo fetch/write boundaries, tokens, workflow permissions, SSRF/redirect controls, and public/private artifact separation. Preserve least privilege.

### Maya Chen — Verification
Required cross-repo regression cases:
- upstream official event exists but is absent from final public feed;
- stale-green health report;
- source pipeline succeeds but promotion repo does not update;
- promotion repo updates from stale upstream build;
- duplicate source ownership creates two canonical events;
- annual event prior-year collision;
- cancellation/update propagation;
- route event reduced incorrectly to exact point;
- discovery-only lead attempts direct public promotion;
- prior-known-good retention after source failure.

### Jordan Lee / Chloe Kim — Product / Frontend
Field Desk and future GUI must consume one canonical public feed contract. Do not combine Data Pipeline and Live Feeds client-side to paper over backend drift. Expose freshness/stale state when the backend cannot guarantee current data.

### Amara Okafor — Geospatial Systems
Trace location/route authority through the promotion layer. Preserve route/area semantics for parades; do not allow downstream feed projection to replace route authority with unexplained centroid precision.

### Priya Nair — Runtime Configuration
Version the source pack, canonical event build, public projection and previous-known-good release as one activation tuple. Rollback must restore a complete coherent tuple, not mix source registry from one run with projection from another.

### Omar Haddad — Quality Engineering
Independent acceptance test:
- Event ID `957653` must be traceable from Tier-A source to the exact consumer feed used by the map;
- map-visible data must match authoritative date/time/borough/route semantics;
- no stale health gate may count as PASS;
- no manual insertion may substitute for pipeline proof.

## Immediate classification

- Source existence for Dominican Day Parade: VERIFIED.
- Event ID 957653 appears in Live Feeds evidence/digest artifacts: VERIFIED.
- Current Data Pipeline public GeoJSON on main: EMPTY.
- Live Feeds backend reliability report: HISTORICAL PASS / CURRENT STATUS STALE.
- Final current public-map presence of Event ID 957653: NOT YET VERIFIED.

## Program rule

Do not solve this by copying events manually between repositories. Fix the authority and promotion path so the next major event arrives automatically, with provenance and freshness intact.

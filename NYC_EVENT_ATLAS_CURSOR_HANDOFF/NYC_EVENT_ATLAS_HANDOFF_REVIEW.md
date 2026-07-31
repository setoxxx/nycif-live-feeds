# NYC Event Atlas Handoff — Review vs NYCIF Live Feeds

Date: 2026-07-16  
Package: `NYC_EVENT_ATLAS_CURSOR_HANDOFF`  
Related backend: `setoxxx/nycif-live-feeds` (News Desk / God View / civic desk)

## Verdict

Yes — you have already covered **most of the acquisition and safety method** inside NYCIF Live Feeds (permits, Parks/calendar, civic SODA, pin integrity, News Desk checklist, God View digests).  

This Atlas handoff is **not a duplicate of the public-map pipeline**. It is a separate **editorial master CSV system** (exact 59-column schema, 827 curated occurrences, SQLite evidence/review ledger). Treat it as the long-form research database that News Desk / photographer packs can *draw from*, not as a second public feed.

## What the handoff package is

| Piece | Status in zip | Status after this session |
|------|----------------|---------------------------|
| 827-row baseline CSV (59 cols) | Present | Imported into SQLite (all 827) |
| SQLite schema (raw/candidates/events/review) | Present | Bootstrapped; `occurrence_key` uniqueness relaxed so baseline SI tour pair imports |
| Socrata permit fetch | Broken SoQL (`:id,:updated_at,*`) | **Fixed** (`*,:id,:updated_at`) |
| Immutable raw snapshot + sha256 | HTTP client only | Also written to `raw_snapshots` |
| Normalize → 59 cols | `map_permit` | Working; coords left `Unknown` |
| Dedupe + review queue | Partial | **Working** — 2,036 new permits queued for review |
| Auto-expand canonical events | Skeleton risked mass insert | **Conservative default**: no auto-accept; `--auto-accept-new` opt-in |
| `run_pipeline.py` | Print stub | Orchestrates fetch → ingest → export → validate |
| Source adapters 2–8 (Parks, fairs, BIDs, libraries…) | Config + thin JSON-LD/ICS helpers | **Implemented** — see README adapters table; human accept → EVENT_ID |
| Human accept/reject → EVENT_ID | Missing | **`apply_review_decisions.py`** + `export_review_queue.py` |
| Socrata app token | `.env` empty | Anonymous SODA worked for this run |

## What we ran successfully

```bash
cd NYC_EVENT_ATLAS_CURSOR_HANDOFF
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env   # SOCRATA_APP_TOKEN left blank; public SODA OK
python scripts/bootstrap_db.py
python scripts/import_existing.py data/NYC_EVENTS_MASTER_CUMULATIVE_BASELINE.csv
python -m pytest -q
python scripts/run_pipeline.py --start 2026-07-16 --end 2026-12-31
```

### Permit window 2026-07-16 → 2026-12-31

- Fetched **7,218** relevant-type SODA rows  
- After relevance filter: **4,369** candidates  
- Raw snapshot sha256: `add05ee336d0205a8ba949036dd7539679f44c03631f638fe958b3d108710862`  
- Exact permit skips (mostly within-batch dups): **2,328**  
- Exact occurrence-key skips vs baseline: **5**  
- Queued `new_occurrence_candidate` for human verify: **2,036**  
- Auto-accepted into canonical `events`: **0** (by design)  
- Canonical events remain **827**  
- Cumulative export validated: **827 rows / 59 columns**  
- Review CSV: `data/staging/permit_review_queue.csv`

## Overlap with NYCIF (already built)

| Atlas goal | NYCIF equivalent already live / in PR #179 |
|------------|--------------------------------------------|
| Daily permit extract `tvpp-9vvx` | `scripts/sync_nyc_open_data.py`, staged feed, reliability gate |
| Historical permits `bkfu-528j` | `scripts/sync_nyc_permits_historical.py` + viral recurrence |
| Parks / public calendars | Parks BigApps + citywide calendar sync; discovery taxonomy |
| Editorial assignment desk | News Desk checklist + parade census + Money-Day / Shoot Day packs |
| Operator bookmark | Civic + Discovery + News Desk God View panels |
| No invented pins | Pin integrity gate + client NYC-box recertify |
| No silent public publish | `promotion_allowed` / `map_eligible` false; protected files |

**Do not** load Atlas review-queue CSV or cumulative master as the Field Desk public default feed. Atlas = research/editorial. NYCIF staged/approved feeds = map.

## Gaps Atlas still needs (after permits + adapters)

Adapters **1–8 are scaffolded and runnable** (`scripts/run_source_adapters.py`).
This session verified:

| Adapter | Mapped → review (window 2026-07-16…12-31) |
|---------|-------------------------------------------|
| parks | 210 |
| public_calendar | 102 (editorial filter from 2781 snapshot rows) |
| clearview | 33 (+ demo 2 accept / 1 reject) |
| nyc_street_fairs | 25 |
| community / holidays / santa_rosalia | 0 mapped (robots/404/no JSON-LD); use `offline_html` |

Also still needed inside Atlas:

- Human review of the large open queues (permits ~2,036 + adapter candidates)  
- Update-ledger application path for corrections to existing IDs  
- Optional Geoclient enrichment **only** with disclosed quality + stored response  
- Wire `SOCRATA_APP_TOKEN` if rate limits appear  
- Save official holiday / Santa Rosalia announcement HTML into `data/raw/offline/` when live fetch is blocked  

## Safety confirmation

- No coordinates invented by adapters/importers (`LATITUDE`/`LONGITUDE` = `Unknown` unless source-provided)  
- No prior-year date inference  
- Baseline `EVENT_ID` / `SERIES_ID` preserved  
- Canonical grows **only** via `apply_review_decisions.py` (demo: 827 → 829)  
- Separate from NYCIF `location_cache.json` / staged live feed / WordPress map  

## Recommended next move

1. Keep Atlas as its **own repo** (or clearly isolated package) — do not merge into the NYCIF public-map path.  
2. Export open review → fill accept/reject → `--export` to grow Part 013 / cumulative.  
3. Drop official announcement HTML into `data/raw/offline/` for holiday + Santa Rosalia seeds.  
4. Set `SOCRATA_APP_TOKEN` in `.env` when you have one (optional today).

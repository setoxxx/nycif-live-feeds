# NYC Event Atlas — Cursor Automation Handoff

This package continues the NYC Event Atlas from the curated 827-row cumulative master.
Canonical growth happens **only** after human accept → `EVENT_ID` allocation.

## Current baseline

- Input: `data/NYC_EVENTS_MASTER_CUMULATIVE_BASELINE.csv` (827 rows)
- Export schema: 59 columns, preserved exactly
- SQLite ledger: `data/atlas.sqlite` (local; gitignored)
- Goal: source-backed candidates into review; accept/reject before Part 013 / cumulative growth

## Safety rules

- Never invent coordinates, organizers, routes, or prior-year→current dates
- Adapters write **review_queue** only — they do not allocate `EVENT_ID`
- `apply_review_decisions.py` is the sole path that grows the canonical master
- Atlas review artifacts are **not** NYCIF public-map feeds

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env

python scripts/bootstrap_db.py
python scripts/import_existing.py data/NYC_EVENTS_MASTER_CUMULATIVE_BASELINE.csv
python -m pytest -q

# Optional permits window
python scripts/run_pipeline.py --start 2026-07-16 --end 2026-12-31
```

## Adapters 1–8 (evidence → review)

```bash
python scripts/run_source_adapters.py --start 2026-07-16 --end 2026-12-31
# subset:
python scripts/run_source_adapters.py --start 2026-07-16 --end 2026-12-31 --only parks clearview
```

| Adapter | Source | Notes |
|---------|--------|-------|
| `parks` | NYC Parks BigApps JSON | `official_feed` (robots blocks HTML) |
| `public_calendar` | Citywide calendar snapshot | Uses `/workspace/data/nyc_citywide_events_calendar_snapshot.json`; editorial filter |
| `clearview` | Clearview vendor schedule HTML | Table + jammed-cell parser |
| `nyc_street_fairs` | NYC Street Fairs annual PDF | Ordinal month dates; PDF via `official_feed` |
| `community` | BID / CB / library / museum / parish seeds | JSON-LD → ICS → `<time>` fallback; `offline_html` supported |
| `holidays` | Holiday organizer seeds | Same as community; save offline HTML when robots blocks |
| `santa_rosalia` | 18th Avenue Feast monitor | Offline HTML + feast keyword/date scrape |

Seeds: `config/seeds/*.yaml`. Put saved pages in `data/raw/offline/` and set `offline_html:`.

## Human accept / reject → EVENT_ID

```bash
python scripts/export_review_queue.py
# Edit data/staging/open_review_queue.csv → decision=accept|reject|defer

python scripts/apply_review_decisions.py \
  --decisions data/staging/open_review_queue.csv \
  --export
```

Or a small decisions file:

```bash
python scripts/apply_review_decisions.py \
  --decisions data/decisions/demo_accept_reject.csv \
  --export
```

`--export` rebuilds:

- `data/exports/NYC_EVENTS_MASTER_CUMULATIVE.*`
- `data/exports/NYC_EVENTS_PART_013.*` (accepted IDs only)

Demo verification (this workspace): baseline **827** → after 2 accepts **829**, with Part 013 = 2 rows.

## Core operating rule

Never edit the canonical cumulative CSV directly. Every run should:

1. acquire raw evidence;
2. store immutable snapshots;
3. extract candidates;
4. normalize;
5. compare against canonical + open review;
6. queue for human review (no silent EVENT_ID);
7. accept/reject via decisions CSV;
8. validate + export.

See `docs/OPERATIONS_RUNBOOK.md` and `NYC_EVENT_ATLAS_HANDOFF_REVIEW.md`.

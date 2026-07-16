# NYCIF News Desk + Parade Census — Next Prompt to Complete

**Bookmark date:** 2026-07-16  
**Backend repo:** [setoxxx/nycif-live-feeds](https://github.com/setoxxx/nycif-live-feeds)  
**Frontend repo:** [setoxxx/nycif-field-desk](https://github.com/setoxxx/nycif-field-desk)  
Read [AGENTS.md](https://github.com/setoxxx/nycif-live-feeds/blob/main/AGENTS.md) in **both** repos before any changes.

**Prime directive:** Do not publish bad data.  
Staging/checklist/census artifacts are editorial tools until explicit promotion.

---

## Where we are now (do not rebuild)

**Backend PR #179** (branch: `cursor/citywide-parade-census-bfb8`):  
https://github.com/setoxxx/nycif-live-feeds/pull/179

### Completed on backend

- [x] [data/nycif_citywide_parade_anchor_registry.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/nycif_citywide_parade_anchor_registry.json) (47 editorial anchors)
- [x] [scripts/citywide_parade_census_common.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/citywide_parade_census_common.py) (Phase 2 multi-source)
- [x] [scripts/build_citywide_parade_census.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/build_citywide_parade_census.py) (schema v2)
- [x] [data/citywide_parade_census_snapshot.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/citywide_parade_census_snapshot.json) — **233 rows**, `qa_pass: true`
- [x] Parade census Phase 2: permits + citywide calendar (**+86**) + Parks BigApps (**+33**)
- [x] Historical permits → TBA inference on unmatched anchors only
- [x] SAPO FOIL operator join hook (when [sapo_foil_operator_index.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/sapo_foil_operator_index.json) filled)
- [x] `anchor_watchlist` in census snapshot
- [x] [scripts/news_desk_checklist_common.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/news_desk_checklist_common.py)
- [x] [scripts/build_news_desk_assignment_checklist.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/build_news_desk_assignment_checklist.py)
- [x] [data/news_desk_assignment_checklist.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/news_desk_assignment_checklist.json) — **661 rows**, `qa_pass: true`
- [x] ODB street co-naming: permit **945819**, Jul 25 Brooklyn, `highest`, `street_co_naming`
- [x] `priority_unchecked`: **514 rows**
- [x] [scripts/build_major_radar_map_events.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/build_major_radar_map_events.py)
- [x] [nycif_major_radar_map_events.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/nycif_major_radar_map_events.json) rebuilt (**369 rows**, 11 NYPD hard-writes preserved)
- [x] Wired into [run_daily_people_facing_desk_sync.py](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/scripts/run_daily_people_facing_desk_sync.py)
- [x] Wired into [live-sync-qa.yml](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/.github/workflows/live-sync-qa.yml)
- [x] God View digest + [civic-godview-panel-v01.js](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/docs/field-desk-admin-deploy/admin/civic-godview-panel-v01.js) updated
- [x] **14 pytest cases** passing

### Completed in field-desk (v02 ready — human push + merge to main)

- [x] [`field-desk-news-desk-v01.js`](https://github.com/setoxxx/nycif-field-desk/blob/cursor/news-desk-staging-overlay-bfb8/field-desk-news-desk-v01.js) v02 — assignment merge, sort, URL handshake, priority filter
- [x] [`admin/news-desk-godview-panel-v01.js`](https://github.com/setoxxx/nycif-field-desk/blob/cursor/news-desk-staging-overlay-bfb8/admin/news-desk-godview-panel-v01.js)
- [x] 14 frontend tests passing
- Branch: `cursor/news-desk-staging-overlay-bfb8` — **cursor[bot] cannot push field-desk**
- Deploy package: [docs/field-desk-map-deploy/civic-people-facing-v01/field-desk-news-desk-v01.js](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/docs/field-desk-map-deploy/civic-people-facing-v01/field-desk-news-desk-v01.js)

### Safety (enforced)

- `map_eligible: false` on **all** census + checklist rows
- `promotion_allowed: false` everywhere
- `location_cache.json`, `nycif_staged_live_events.json`, staged manifests **untouched**
- No public map publish

---

## Map links

| Surface | URL |
|--------|-----|
| **Field Desk map** | https://setoxxx.github.io/nycif-field-desk/ |
| **Assignment / News Desk mode** | https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1 |
| **ODB deep link** (Jul 25 Brooklyn) | https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date=2026-07-25&assignment=1&borough=Brooklyn |
| **Admin God View** | https://setoxxx.github.io/nycif-field-desk/admin/index.html |
| **WordPress public map** (unchanged) | https://nycinfocus.com/map/ |

---

## Artifact URLs (raw GitHub — after PR #179 merges to `main`)

| Artifact | URL |
|----------|-----|
| **News desk checklist** | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/news_desk_assignment_checklist.json |
| **Parade census snapshot** | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/citywide_parade_census_snapshot.json |
| **Major radar (rebuilt)** | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json |
| **Photographer money-day calendar** | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/photographer_assignment_calendar_2mo.json |
| **Public staged feed** (DEFAULT — do not replace) | https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json |

**QA-only** — never public map default: parade census, news desk checklist, all `gps_review_*` / `gps_manual_approval_*` artifacts.

---

## Remaining work — complete these next

### Task A — Merge + deploy (human gates)

1. Review and merge [PR #179](https://github.com/setoxxx/nycif-live-feeds/pull/179)
2. Push field-desk branch to GitHub Pages:
   ```bash
   cd nycif-field-desk
   git checkout cursor/news-desk-staging-overlay-bfb8
   git push -u origin cursor/news-desk-staging-overlay-bfb8
   ```
   Open PR → merge to `main` → Pages refresh
3. Copy deploy packages if needed:
   - [docs/field-desk-map-deploy/civic-people-facing-v01/](https://github.com/setoxxx/nycif-live-feeds/tree/cursor/citywide-parade-census-bfb8/docs/field-desk-map-deploy/civic-people-facing-v01) → `nycif-field-desk/`
   - [docs/field-desk-admin-deploy/admin/](https://github.com/setoxxx/nycif-live-feeds/tree/cursor/citywide-parade-census-bfb8/docs/field-desk-admin-deploy/admin) → `nycif-field-desk/admin/`
4. Verify assignment mode loads checklist + census overlay in Filters panel
5. Confirm public map (no `?assignment=1`) shows **no** News Desk UI

### Task B — Field Desk polish (`nycif-field-desk`)

Read [field-desk AGENTS.md](https://github.com/setoxxx/nycif-field-desk/blob/main/AGENTS.md). **Operator/assignment mode only.**

1. **Assignment mode merge:** money-day calendar + `priority_unchecked`; show `why_story` + `assignment_score`; sort by `editorial_priority` then score; honor `?date=` + `?borough=` deep links
2. **News Desk panel:** editorial_priority filter; list_only off map, in sidebar; localStorage status OK for now
3. **Parade census overlay:** full popup cards; lane-colored pins; staging banner
4. **Admin God View:** checklist + census QA from digest
5. **Tests:** `node --test tools/public-map/operator-desk.test.mjs`

### Task C — Backend data quality (`nycif-live-feeds`)

1. Fill [sapo_foil_operator_index.json](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/sapo_foil_operator_index.json) when FOIL PDFs arrive
2. Expand [anchor registry](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/data/nycif_citywide_parade_anchor_registry.json) as 2026 dates confirm
3. Permit refresh → census → checklist pipeline
4. `anchor_watchlist` tracks unmatched annual events
5. Street co-namings never silently dropped (ODB class)

### Task D — Display / geocode (optional hardening)

- List view: headline, date, borough, route, lane, priority, confidence, `field_desk_link`
- Map pin: lat/lng + `coordinate_status: map_ready` (join from all-radar; **never** write `location_cache.json`)
- Display cleanup: `C0-Naming` → `Co-Naming`

### Task E — Daily operator workflow

**Automated** ([daily-people-facing-desk-sync.yml](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/.github/workflows/daily-people-facing-desk-sync.yml)): sync → civic staging → photographer calendar → historical → viral → **census → checklist → major radar** → pin integrity → shoot day → godview.

**Human morning:**

1. [Admin](https://setoxxx.github.io/nycif-field-desk/admin/index.html)
2. Verify `daily_people_facing_sync_report.json` `qa_pass`
3. [Assignment mode for today](https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1)
4. Review [priority_unchecked](https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/news_desk_assignment_checklist.json)
5. Assign → `news_desk_status: assigned` → after coverage → `covered`

**Full permit refresh:**
```bash
gh workflow run live-sync-qa.yml -f allow_live_fetch=yes -f allow_email=no
```

---

## Success criteria

| Area | Status |
|------|--------|
| Backend checklist/census QA | ✅ Done — verify after merge |
| Field Desk staging overlay | ✅ Built — push branch + merge to main |
| Assignment mode sort/merge | ✅ Built in v02 overlay |
| Admin God View KPIs | ✅ Built — verify after Pages deploy |
| Anchor watchlist completeness | ⬜ Ongoing |

---

## Protected files

Do **not** edit without explicit authorization: `location_cache.json`, `nycif_staged_live_events.json`, staged manifests, public map outputs, WordPress embed, GitHub secrets.

Publishing requires explicit language: *"promote these approved rows"*, *"publish this to the public map"*.

---

## Run locally

```bash
# Backend
python3 scripts/build_citywide_parade_census.py
python3 scripts/build_news_desk_assignment_checklist.py
python3 scripts/build_major_radar_map_events.py
python3 -m pytest tests/test_citywide_parade_census.py \
  tests/test_news_desk_assignment_checklist.py \
  tests/test_major_radar_rebuild.py -q

# Frontend
node --test tools/public-map/operator-desk.test.mjs
```

---

## Copy-paste agent kickoff (short)

```
Complete NYCIF News Desk display rollout:

1. Merge PR #179 on setoxxx/nycif-live-feeds.
2. Push nycif-field-desk branch cursor/news-desk-staging-overlay-bfb8
   (field-desk-news-desk-v01.js ready — operator/assignment mode only).
3. Polish assignment mode: merge money-day + priority_unchecked;
   show why_story + assignment_score; sort by editorial_priority then score.
4. Verify parade census staging pins; list_only stays off map.
5. Merge field-desk to main → GitHub Pages refresh.
6. QA: https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1
7. Do NOT publish census/checklist without explicit promotion.

Full spec: docs/NYCIF-NEWS-DESK-FULL-PROMPT.txt
Status: docs/NYCIF-NEWS-DESK-NEXT-PROMPT.md
```

---

**Related docs**

- [Full continuation prompt (txt)](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/docs/NYCIF-NEWS-DESK-FULL-PROMPT.txt)
- [This next-step prompt (md)](https://github.com/setoxxx/nycif-live-feeds/blob/cursor/citywide-parade-census-bfb8/docs/NYCIF-NEWS-DESK-NEXT-PROMPT.md)
- [PR #179](https://github.com/setoxxx/nycif-live-feeds/pull/179)

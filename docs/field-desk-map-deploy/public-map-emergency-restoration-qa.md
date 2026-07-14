# Public map emergency restoration — QA

Branch: `cursor/emergency-public-map-restoration-20260713`  
App version: `0.8-emergency-map-restore-v01`  
Public defaults: `staged-live-v03`  
Query: `?v=map-restore-v01&resetFilters=1`

## Automated checks

| Check | Result |
| --- | --- |
| `node --check` on app / significance / date / defaults / SW | PASS |
| `node tests/map-restore-unit.test.js` | PASS (8 assertions) |
| PHP lint plugin 1.2.1 | PASS (in live-feeds repo) |
| ZIP integrity `dist/nycif-events-map-1.2.1.zip` | PASS |

## Local browser smoke (`http://127.0.0.1:8765/?v=map-restore-v01&resetFilters=1`)

| Check | Result |
| --- | --- |
| Staged feed HTTP 200 | PASS |
| Source rows | 32,845 |
| Events today (visible) | 1,125 |
| Markers drawn (≤ cap) | 1,125 markers for today / up to 2,000 when broader |
| Event list populated | PASS (60 list rows) |
| Fitness / wellness control present + default on | PASS |
| Fitness-only filter | PASS (9 fitness events listed) |
| Parks + General default on | PASS |
| Major events only default off | PASS |
| Gold/Silver/Bronze filters default on | PASS |
| Significance-only mode | PASS (122 tiered events) |
| Why this tier + integrity text in popup | PASS |
| 5PM / cannabis / correlation overlay controls present | PASS |
| Service worker cache | `nycif-v015-emergency-map-restore` |
| Fatal console errors | none |
| Mobile 390px screenshot captured | PASS |
| Manual “All” date not overridden | PASS (32,845 events) |

Screenshots:

- `/opt/cursor/artifacts/screenshots/map-restore-desktop.png`
- `/opt/cursor/artifacts/screenshots/map-restore-mobile-390.png`

## Feed fallback

| Scenario | Result |
| --- | --- |
| Staged abort → full | PASS (`Full feed`, 33,127 GPS rows) |
| Staged+full abort → major | PASS (`Fast major feed`) |
| All abort | PASS explicit error: `All map feeds failed...` |

## Date behavior

| Scenario | Result |
| --- | --- |
| `row.date` preferred over UTC `start_date_time` | PASS (unit test) |
| Simulated empty today → next date Wed Jul 15 | PASS with status message |
| Manual All after fallback | stays All; not overridden |

## Significance

| Scenario | Result |
| --- | --- |
| Paid/sponsored ignored | PASS |
| Closed/maintenance untiered | PASS |
| Canonical `significance_tier` override | PASS |
| Displayed tiers include reasons | PASS |
| Untiered visible by default | PASS |

## Safety

- `data/location_cache.json` not modified
- GPS review / approval artifacts not modified
- Overlays not removed
- No WordPress upload performed
- No silent PR merges

## Remaining limitation

GitHub Pages and WordPress still serve the pre-restore runtime until the Field Desk PR is merged/deployed and the 1.2.1 plugin ZIP is uploaded manually.

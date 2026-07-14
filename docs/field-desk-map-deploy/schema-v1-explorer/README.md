# Field Desk schema v1 explorer patch (mirror)

Copy these files into `setoxxx/nycif-field-desk` on top of the all-source explorer branch / PR #106:

- `event-feed-schema-v1.js` (new)
- `all-source-data-explorer-v01.js`
- `index.html`
- `service-worker.js`
- `all-source-data-explorer-v01.md` → `docs/all-source-data-explorer-v01.md`

Requires `nycif-live-feeds` schema projection artifacts on `main`:

- `data/events_schema_v1_staged.json`
- `data/events_schema_v1_supplemental_review.json`

Fallback: explorer still projects legacy staged/supplemental feeds client-side to schema v1.0.

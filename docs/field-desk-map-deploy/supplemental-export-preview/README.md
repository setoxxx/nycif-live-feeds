# Supplemental approved export preview (field-desk deploy)

Admin/QA-only map for **3,566** approved supplemental events from
`supplemental_approved_export_feed.json`. Not production map data.

## Sync to field-desk (requires write access)

```bash
./scripts/sync_supplemental_export_preview_to_field_desk.sh /path/to/nycif-field-desk
cd /path/to/nycif-field-desk
git push -u origin cursor/supplemental-export-preview-c1f9
gh pr create --fill
gh pr merge --squash
```

## Verify after deploy

| Entry | URL |
| --- | --- |
| Standalone QA | `https://setoxxx.github.io/nycif-field-desk/approved-export-preview.html` |
| Desk overlay | `https://setoxxx.github.io/nycif-field-desk/desk.html?previewExport=1` |
| Dist feed override | add `?distExport=1` |

Expected: **3,566** purple preview markers; banner shows PREVIEW / NOT PRODUCTION.

## Backend feed URLs

- `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_approved_export_feed.json`
- `https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/supplemental_approved_export_feed.json`

Both are `production_feed=false` and `promotion_allowed=false`.

## Safety

Does not load GPS review queues, pending approvals, or `production_feed=true` artifacts.

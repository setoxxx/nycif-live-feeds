NYCIF Events Map 1.5.0-rc2

Purpose
- Embeds the deployed NYC In Focus Field Desk map in WordPress posts/pages (in-article).
- Uses approved public discovery feed: feeds=main only (allowlist — other values rejected).
- Runtime cache bust: public-map-v10 only (allowlist).
- Preserves geolocation and fullscreen permissions on the iframe.
- WordPress does not download or parse event JSON.

Production /map/ page (IMPORTANT)
- https://nycinfocus.com/map/ does NOT use this shortcode.
- Page 2647 uses the fullscreen #nycifMapAppShell Custom HTML block.
- Deploy /map/ via CHATGPT-EXECUTION-PROMPT.md in the live-feeds repo.

Package contents (verify before upload)
- nycif-events-map.php
- block.json
- readme.txt
- README.md
- RECOVERY-MANIFEST.json

Build ZIP (WordPress requires nycif-events-map/ folder inside archive)
```bash
./scripts/build_nycif_events_map_plugin_zip.sh
# → dist/nycif-events-map-1.5.0-rc2.zip
unzip -l dist/nycif-events-map-1.5.0-rc2.zip   # must show nycif-events-map/ prefix on every path
```

Install / upgrade from 1.4.0-rc1
1. WordPress → Plugins → Add New → Upload Plugin.
2. Upload nycif-events-map-1.5.0-rc2.zip.
3. Replace the existing NYCIF Events Map plugin.
4. Clear WordPress/page/CDN caches.
5. Settings → NYCIF Events Map — confirm version 1.5.0-rc2, public-map-v10, feeds=main.
6. Test https://nycinfocus.com/map/ in private window (desktop + mobile) — shell page, not shortcode.
7. Test any pages that still use [nycif_events_map] shortcode.

What changed from 1.4.0-rc1
- RETIRED: discovery-taxonomy-v03 runtime token
- RETIRED: commit SHA feed pins
- NEW: feeds=main and public-map-v10 allowlists
- NEW: block.json for dynamic block registration

Shortcode
  [nycif_events_map]
  [nycif_events_map height="90vh" feeds="main" loading="lazy"]

Repositories
- Field Desk: https://github.com/setoxxx/nycif-field-desk
- Live feeds: https://github.com/setoxxx/nycif-live-feeds

Safety
- No GPS review artifacts, staged feed, or supplemental export on feeds=main.
- Plugin is for in-article embeds; public /map/ uses freeze doc shell only.

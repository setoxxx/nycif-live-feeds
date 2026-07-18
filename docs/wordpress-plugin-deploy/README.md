# NYCIF Events Map — WordPress plugin deploy

> **Production `/map/` page (FROZEN):** read [`nycinfocus-map-page-v1-freeze.md`](./nycinfocus-map-page-v1-freeze.md) before any WordPress or embed change. That doc is the signed-off fullscreen display contract for https://nycinfocus.com/map/.

Copy `nycif-events-map/` into your WordPress plugins directory:

```bash
cp -r docs/wordpress-plugin-deploy/nycif-events-map /path/to/wp-content/plugins/
# Activate in WP Admin → Plugins → NYCIF Events Map
```

## Usage

Page or post shortcode (for **in-article** embeds — **not** for `/map/`):

```
[nycif_events_map]
[nycif_events_map height="90vh" cache="public-map-v09" feeds="main"]
```

Settings: **WP Admin → Settings → NYCIF Events Map**

## Canonical embed URL (2026-07-18 — RC release / public-map-v09)

Approved public discovery feed on GitHub Pages:

```
https://setoxxx.github.io/nycif-field-desk/?v=public-map-v09&resetFilters=1&feeds=main
```

**Retire** legacy params: `?feed=staged&v=nycif-map-publish-02` (misleading; runtime ignores staged autoload on current index).

## nycinfocus.com/map/ (production — use freeze doc)

Do **not** use the plugin shortcode or a bare 85vh iframe on `/map/`.

The live page uses a Custom HTML fullscreen shell (`#nycifMapAppShell`) documented in [`nycinfocus-map-page-v1-freeze.md`](./nycinfocus-map-page-v1-freeze.md). Copy that file’s HTML block verbatim when restoring or updating the page.

## Safety

- Plugin loads GitHub Pages app only — approved public feed via `feeds=main`
- Does not auto-merge supplemental staging or GPS review artifacts
- GPS review artifacts are never exposed via this plugin

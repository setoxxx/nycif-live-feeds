# NYCIF Events Map — WordPress plugin deploy

**Primary ChatGPT prompt (use this):** [`CHATGPT-EXECUTION-PROMPT.md`](./CHATGPT-EXECUTION-PROMPT.md) — gated deploy with preflight, plugin review, and rollback truth.

Background runbook: [`CHATGPT-WORDPRESS-DEPLOY-PROMPT.md`](./CHATGPT-WORDPRESS-DEPLOY-PROMPT.md)

Copy `nycif-events-map/` into your WordPress plugins directory:

```bash
cp -r docs/wordpress-plugin-deploy/nycif-events-map /path/to/wp-content/plugins/
# Activate in WP Admin → Plugins → NYCIF Events Map
```

Or zip and upload: `nycif-events-map-1.5.0-rc1.zip` (package the `nycif-events-map/` folder).

## Plugin version alignment (2026-07-18)

| Package | Runtime `v=` | Feed | Status |
|---------|--------------|------|--------|
| **1.5.0-rc2** (repo) | `public-map-v10` | `feeds=main` | **Use this** — addresses deploy review |
| 1.5.0-rc1 | `public-map-v10` | `feeds=main` | Superseded by rc2 |
| 1.4.0-rc1 (live site) | `discovery-taxonomy-v03` | commit `bf7dedd…` | **Retired** — upgrade |
| 1.3.2 (older repo) | `public-map-v10` | `feeds=main` | Superseded by 1.5.0-rc1 |

**1.4.0-rc1 problems:** pinned an unmerged commit SHA and old runtime token. The map on `/map/` uses the Custom HTML shell, but other pages with `[nycif_events_map]` still load whatever the **active plugin** builds — upgrade the plugin so shortcode embeds match RC.

Settings after upgrade: **WP Admin → Settings → NYCIF Events Map** — confirm canonical URL shows `public-map-v10` and `feeds=main`.

## Usage

Page or post shortcode (for **in-article** embeds — **not** for `/map/`):

```
[nycif_events_map]
[nycif_events_map height="90vh" cache="public-map-v10" feeds="main"]
```

Settings: **WP Admin → Settings → NYCIF Events Map**

## Canonical embed URL (2026-07-18 — RC release / public-map-v10)

Approved public discovery feed on GitHub Pages:

```
https://setoxxx.github.io/nycif-field-desk/?v=public-map-v10&resetFilters=1&feeds=main
```

**Retire** legacy params: `?feed=staged&v=nycif-map-publish-02` (misleading; runtime ignores staged autoload on current index).

## nycinfocus.com/map/ (production — use freeze doc)

Do **not** use the plugin shortcode or a bare 85vh iframe on `/map/`.

The live page uses a Custom HTML fullscreen shell (`#nycifMapAppShell`) documented in [`nycinfocus-map-page-v1-freeze.md`](./nycinfocus-map-page-v1-freeze.md). Copy that file’s HTML block verbatim when restoring or updating the page.

## Safety

- Plugin loads GitHub Pages app only — approved public feed via `feeds=main`
- Does not auto-merge supplemental staging or GPS review artifacts
- GPS review artifacts are never exposed via this plugin

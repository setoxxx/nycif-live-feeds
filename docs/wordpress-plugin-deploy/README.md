# NYCIF Events Map — WordPress plugin deploy

Copy `nycif-events-map/` into your WordPress plugins directory:

```bash
cp -r docs/wordpress-plugin-deploy/nycif-events-map /path/to/wp-content/plugins/
# Activate in WP Admin → Plugins → NYCIF Events Map
```

## Usage

Page or post shortcode:

```
[nycif_events_map]
[nycif_events_map height="90vh" cache="public-map-v07" feeds="main"]
```

Settings: **WP Admin → Settings → NYCIF Events Map**

## Canonical embed (2026-07-16 — Complete-the-Map / public-map-v07)

Approved public discovery feed on GitHub Pages:

```
https://setoxxx.github.io/nycif-field-desk/?v=public-map-v07&resetFilters=1&feeds=main
```

**Retire** legacy params: `?feed=staged&v=nycif-map-publish-02` (misleading; runtime ignores staged autoload on current index).

## nycinfocus.com/map/ update (human deploy)

If the site uses a raw iframe in a page template instead of this plugin:

```html
<iframe
  title="NYC In Focus Event Map"
  src="https://setoxxx.github.io/nycif-field-desk/?v=public-map-v07&resetFilters=1&feeds=main"
  style="width:100%;height:85vh;border:0;"
  loading="lazy"
  allow="geolocation"></iframe>
```

WordPress block editor: edit the Map page → Custom HTML or iframe block → replace `src` → Update.

## Safety

- Plugin loads GitHub Pages app only — approved public feed via `feeds=main`
- Does not auto-merge supplemental staging or GPS review artifacts
- GPS review artifacts are never exposed via this plugin

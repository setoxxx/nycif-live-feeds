# NYCIF Events Map — WordPress plugin deploy (M10)

Copy `nycif-events-map/` into your WordPress plugins directory:

```bash
cp -r docs/wordpress-plugin-deploy/nycif-events-map /path/to/wp-content/plugins/
# Activate in WP Admin → Plugins → NYCIF Events Map
```

## Usage

Page or post shortcode:

```
[nycif_events_map]
[nycif_events_map height="90vh" cache="m10-staged-live"]
```

Settings: **WP Admin → Settings → NYCIF Events Map**

## What changed in M10

- Embed points at GitHub Pages map (`setoxxx.github.io/nycif-field-desk/`)
- Map boot loads **staged feed** (~32k resolver-backed permit events) instead of stale June major feed
- Feed URLs documented for staged + full radar JSON on `nycif-live-feeds/main`
- Cache-bust query `?v=m10-staged-live` — bump after each feed deploy

## nycinfocus.com/map/ update

If the site uses a raw iframe in a page template instead of this plugin:

```html
<iframe
  title="NYC In Focus Event Map"
  src="https://setoxxx.github.io/nycif-field-desk/?v=m10-staged-live"
  style="width:100%;height:85vh;border:0;"
  loading="lazy"
  allow="geolocation"></iframe>
```

## Safety

- Plugin loads GitHub Pages app only — does not auto-merge supplemental staging feed
- GPS review artifacts are never exposed via this plugin

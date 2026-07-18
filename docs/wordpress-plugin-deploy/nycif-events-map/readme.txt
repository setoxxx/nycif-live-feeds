=== NYCIF Events Map ===
Contributors: nycinfocus
Tags: map, events, nyc, iframe
Requires at least: 5.8
Tested up to: 6.8
Requires PHP: 7.4
Stable tag: 1.5.0-rc2
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Embeds the NYC In Focus public event map from GitHub Pages for in-article WordPress pages.

== Description ==

This plugin embeds the NYC In Focus Field Desk map via shortcode or block. It loads the **approved public discovery feed** (`feeds=main`) from GitHub Pages with runtime cache bust `public-map-v10`.

**Important:** The production map at https://nycinfocus.com/map/ does **not** use this shortcode. That page uses a fullscreen Custom HTML shell (WordPress page 2647). See the freeze doc in the nycif-live-feeds repository.

Mobile (≤720px) and desktop (≥721px) layouts are handled automatically inside the map iframe.

== Installation ==

1. Upload the plugin zip via Plugins → Add New → Upload Plugin.
2. Activate NYCIF Events Map.
3. Use `[nycif_events_map]` on posts/pages that need an in-article embed (not on /map/).
4. Clear page/CDN caches after upgrading from 1.4.0-rc1.

== Frequently Asked Questions ==

= Should I use this on nycinfocus.com/map/? =

No. Use the fullscreen shell documented in `nycinfocus-map-page-v1-freeze.md` in the live-feeds repo.

= What changed from 1.4.0-rc1? =

- Runtime: `discovery-taxonomy-v03` → `public-map-v10`
- Feed: commit SHA pin → `feeds=main`
- Aligns with RC release (#298–#302) and device display modes

== Changelog ==

= 1.5.0-rc2 =
* Review fixes: lazy shortcode loading, strict-origin referrer, block attributes registered
* Admin-visible warning when commit SHA feed pins normalize to main
* Settings clarify v= cache-bust vs Field Desk deploy rollback

= 1.5.0-rc1 =
* Align with public-map-v10 and feeds=main approved discovery contract
* Deprecate commit-SHA feed_ref pins (normalize to main)
* Settings page documents /map/ fullscreen shell vs shortcode
* Retain clusters=1 optional shortcode attribute

= 1.4.0-rc1 =
* Discovery taxonomy RC (superseded — do not use commit-pinned feeds in production)

== Upgrade Notice ==

= 1.5.0-rc1 =
Required for RC public map release. Replaces 1.4.0-rc1 commit-pinned feed with feeds=main.

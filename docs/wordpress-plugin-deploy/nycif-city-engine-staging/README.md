# NYCIF City Engine Staging

Source-controlled companion plugin for protected review of the City Engine on WordPress.

## Current state

**Fail closed.** The plugin source is not installed and the reviewed asset bundle is not yet packaged. Until both a valid local manifest and its hash-matched entrypoint are present, authenticated editors see a safely disabled message.

## WordPress boundary

- Site: `nycinfocus.com` (`239339912`)
- Designated staging page: draft page `2865`, **NYC Events Map Prototype**
- Shortcode: `[nycif_city_engine_staging]`
- Required capability: `edit_pages`
- Required page status: `draft`
- Anonymous and unauthorized visitors receive only: `This preview is not available.`

## Asset boundary

The private `setoxxx/nycif-web-platform` repository cannot be loaded from a public CDN. A later packaging step must vendor a reviewed snapshot beneath this plugin directory and create:

`assets/city-engine-staging-manifest.json`

Required manifest fields:

```json
{
  "schema_version": "1",
  "source_repository": "setoxxx/nycif-web-platform",
  "source_commit": "40-character-commit-sha",
  "entrypoint": "assets/city-engine/index.html",
  "entrypoint_sha256": "64-character-sha256"
}
```

The bridge rejects remote URLs, mutable branch names, parent-directory traversal, unapproved repositories, malformed commits and hash mismatches.

## Explicit non-actions

This package does not:

- install or activate a WordPress plugin
- update draft page 2865
- modify public page 2647 or `/map/`
- change the existing `[nycif_events_map]` shortcode
- change `feeds=main`
- upload media or plugin ZIPs
- modify themes, navigation, WPCode or homepage content
- publish or deploy anything

## Later controlled sequence

1. Package the reviewed City Engine snapshot from an exact `nycif-web-platform` commit.
2. Generate and validate the local manifest and hashes.
3. Build a review ZIP and verify its structure.
4. Obtain separate approval to upload/install the companion plugin.
5. Obtain separate approval to update draft page 2865 with the staging shortcode.
6. Verify the page remains draft and is inaccessible when logged out.
7. Perform desktop/mobile, accessibility, privacy and performance staging QA.

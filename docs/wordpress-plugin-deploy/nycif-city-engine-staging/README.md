# NYCIF City Engine Staging

Source-controlled companion plugin for protected review of the City Engine on WordPress.

## Current state

**Reviewed package prepared; WordPress unchanged.** The companion plugin source remains uninstalled. A deterministic, public-safety-scanned asset package has been produced from exact private-core commit `73fd0fe8118b0915de1152b40f3cd5623986ace4`, independently verified, and assembled into a local review ZIP. No upload, activation, page update, publishing or deployment has occurred.

The complete reviewed manifest, build report and artifact provenance are recorded under:

`reviewed-bundles/73fd0fe/`

The browser assets are retained in the immutable private CI artifact identified by `provenance.json`; they are not duplicated into this public repository through mutable or manual copying.

## WordPress boundary

- Site: `nycinfocus.com` (`239339912`)
- Designated staging page: draft page `2865`, **NYC Events Map Prototype**
- Shortcode: `[nycif_city_engine_staging]`
- Required capability: `edit_pages`
- Required page status: `draft`
- Anonymous and unauthorized visitors receive only: `This preview is not available.`

## Reviewed package

- Source repository: `setoxxx/nycif-web-platform`
- Source commit: `73fd0fe8118b0915de1152b40f3cd5623986ace4`
- Asset count: `34`
- Entrypoint: `assets/city-engine/prototype/index.html`
- Entrypoint SHA-256: `e3951f76d29cb72b14a558884c800fb2703d0cf2998941e453b8fc3e4b7bf7fb`
- Deterministic asset ZIP SHA-256: `d722b376ecef00bde8d0656a0be46a64b75ca4cdcef7b81a1eff906ad58bc007`
- Assembled plugin ZIP: `nycif-city-engine-staging-0.1.0-review.zip`
- Assembled plugin ZIP SHA-256: `0eac84b820e55f15eb4e312acaed583a1b17e96b922ab82c2cb6b9be9b873a91`

The package contains sample/review data and is authorized only for the protected editor-only draft preview after a separate WordPress confirmation.

## Runtime safety

The bridge requires a local manifest and matching entrypoint hash. It rejects remote URLs, mutable branch names, parent-directory traversal, unapproved repositories, malformed commits and hash mismatches.

The package does not authorize production use, public feeds, public navigation or a live `/map/` replacement.

## Explicit non-actions

This checkpoint does not:

- install or activate a WordPress plugin
- update draft page 2865
- modify public page 2647 or `/map/`
- change the existing `[nycif_events_map]` shortcode
- change `feeds=main`
- upload media or plugin ZIPs
- modify themes, navigation, WPCode or homepage content
- publish or deploy anything

## Remaining controlled sequence

1. Merge the public provenance checkpoint after exact-head CI passes.
2. Obtain explicit approval to upload and activate only `nycif-city-engine-staging-0.1.0-review.zip`.
3. Verify the plugin version, package hash and fail-closed behavior.
4. Obtain explicit approval to replace only draft page 2865 content with `[nycif_city_engine_staging]`.
5. Verify the page remains draft and unauthorized visitors cannot view the preview.
6. Perform desktop/mobile, accessibility, privacy and performance staging QA.

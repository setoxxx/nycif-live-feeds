# ChatGPT execution prompt — NYC In Focus map release (read this entire file)

**Purpose:** Give this document to ChatGPT (or any agent with WordPress admin + terminal access). It incorporates a third-party review of the deploy plan and fixes known gaps before anything goes live.

**Do not deploy until every GATE below is PASS.**

---

## GATE 0 — Understand the two repositories

| Repo | Role |
|------|------|
| `setoxxx/nycif-live-feeds` | Source of map deploy files, plugin PHP, runbooks, discovery feed JSON on `main` |
| `setoxxx/nycif-field-desk` | **Deployed** GitHub Pages app visitors load in the iframe |

PRs merge into **live-feeds**. The map visitors see is deployed by GitHub Actions:

- **Workflow:** `Deploy to Field Desk Pages`
- **File:** `.github/workflows/field-desk-complete-map-deploy.yml` in **nycif-live-feeds**
- **Action URL:** https://github.com/setoxxx/nycif-live-feeds/actions/workflows/field-desk-complete-map-deploy.yml

**GATE 0:** Confirm the latest run on `main` completed successfully **after** PR #302 (or the release PR) merged. If the workflow did not run or failed, **STOP**.

---

## GATE 1 — What `v=public-map-v10` actually means

`v=public-map-v10` in the iframe URL is a **cache-bust label** on query strings and asset URLs. It is **not** a server-side router that serves different code per query value.

The **immutable application build** is whatever commit GitHub Pages currently serves from `setoxxx/nycif-field-desk` `main` (updated by the workflow above).

**Real runtime rollback** = redeploy a known-good commit to `nycif-field-desk` via that workflow (or revert the workflow commit on live-feeds `main` and re-run), **not** changing `v=` alone to an older token.

**Real plugin rollback** = reinstall previous plugin ZIP (`nycif-events-map-1.4.0-rc1.zip` or documented rollback package).

---

## GATE 2 — `feeds=main` is intentionally mutable

`feeds=main` means: load discovery JSON from `nycif-live-feeds` branch `main` at `data/schema-v1-discovery/**`. The feed **will change** when the backend pipeline refreshes. That is the product requirement (always-current public events).

**Record at release time** (paste into your report):

```bash
curl -sS https://api.github.com/repos/setoxxx/nycif-field-desk/commits/main | python3 -c "import json,sys; print('field_desk_sha', json.load(sys.stdin)['sha'])"
curl -sS https://api.github.com/repos/setoxxx/nycif-live-feeds/commits/main | python3 -c "import json,sys; print('live_feeds_sha', json.load(sys.stdin)['sha'])"
curl -sS https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/approved/manifest.json | python3 -c "import json,sys; m=json.load(sys.stdin); print('feed_total', m['total'], 'generated_at_utc', m['generated_at_utc'])"
```

---

## GATE 3 — Run preflight (do not use grep-only checks)

From a machine with `curl` and `python3`, run the preflight script from the live-feeds repo:

```bash
# If you have the repo:
./scripts/preflight_field_desk_map_release.sh public-map-v10
```

**Or run these equivalent checks manually:**

```bash
RUNTIME=public-map-v10
BASE="https://setoxxx.github.io/nycif-field-desk"
MAP="${BASE}/?v=${RUNTIME}&resetFilters=1&feeds=main"

# 1) HTTP status
curl -sSI "$MAP" | head -1   # expect 200

# 2) Required assets return 200
for f in index.html public-display-mode-v01.js app-schema-v1-major-all-v01.js discovery-patch-v02.js; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/${f}")
  echo "$f -> $code"
done

# 3) Feed manifest
curl -sS "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/approved/manifest.json" \
  | python3 -c "import json,sys; m=json.load(sys.stdin); assert m['total']>0; print('feed_total', m['total'])"
```

**GATE 3:** All asset HTTP codes must be `200` and `feed_total` must be &gt; 0. If not, **STOP**.

---

## GATE 4 — Human smoke test on GitHub Pages (before WordPress)

Open in a browser (incognito):

`https://setoxxx.github.io/nycif-field-desk/?v=public-map-v10&resetFilters=1&feeds=main`

Verify:

- [ ] Map tiles render (not blank gray)
- [ ] Event pins appear within ~30s
- [ ] Filters panel opens
- [ ] Desktop (wide): Near Me visible, intro text visible
- [ ] Mobile DevTools ≤720px: Near Me hidden, week strip does not overlap GPS stack
- [ ] Tip jar share targets `https://www.nycinfocus.com/map/`

**GATE 4:** All checked. If not, **STOP**.

---

## TASK A — Upgrade WordPress plugin (review actual files first)

The live site may still have **1.4.0-rc1** (bad: `discovery-taxonomy-v03` + commit-pinned feed). Replace with **1.5.0-rc2**.

### Files that must exist in the package (verify before upload)

| File | Purpose |
|------|---------|
| `nycif-events-map.php` | Main plugin — version `1.5.0-rc2`, `public-map-v10`, `feeds=main` |
| `readme.txt` | WordPress plugin readme |
| `README.md` | Human install notes |
| `RECOVERY-MANIFEST.json` | Release metadata + feed snapshot fields |

**Source in GitHub (after PR merge):**  
https://github.com/setoxxx/nycif-live-feeds/tree/main/docs/wordpress-plugin-deploy/nycif-events-map

**Build ZIP locally:**

```bash
./scripts/build_nycif_events_map_plugin_zip.sh
# Produces dist/nycif-events-map-1.5.0-rc2.zip
```

### Install

1. WP Admin → Plugins → Add New → Upload Plugin
2. Upload `nycif-events-map-1.5.0-rc2.zip`
3. Activate / replace existing NYCIF Events Map
4. Settings → NYCIF Events Map — confirm:
   - Version **1.5.0-rc2**
   - Runtime cache bust **public-map-v10**
   - Approved feed **main**
   - Warning about `/map/` using fullscreen shell (not shortcode)

### Plugin review checklist (confirm in uploaded PHP)

- [ ] `NYCIF_RUNTIME_CACHE_BUST` = `public-map-v10`
- [ ] `NYCIF_APPROVED_FEED_REF` = `main`
- [ ] No `discovery-taxonomy-v03` constant
- [ ] No hardcoded `bf7dedd` commit SHA
- [ ] Shortcode iframe uses `loading="lazy"` (articles) and `referrerpolicy="strict-origin-when-cross-origin"`
- [ ] Commit SHA in shortcode shows **admin-visible warning** when normalized to main
- [ ] Block `nycif/events-map` registered with attributes (height, cache, feeds, loading, clusters)

**Do not** put `[nycif_events_map]` on page 2647 `/map/`.

---

## TASK B — Update production `/map/` page (page 2647)

### Page contract

| Field | Value |
|-------|-------|
| Page ID | **2647** |
| URL | https://nycinfocus.com/map/ |
| Template | Blank |
| Editor | **Code editor only** |
| Content | ONE Custom HTML block below |

### Canonical HTML (straight ASCII quotes only)

```html
<style>
  html, body { margin:0 !important; padding:0 !important; height:100% !important; overflow:hidden !important; }
  body:has(#nycifMapAppShell) .nycif-template-shell > header,
  body:has(#nycifMapAppShell) .nycif-template-shell > footer,
  body:has(#nycifMapAppShell) .nycif-page-main > .wp-block-post-title,
  body:has(#nycifMapAppShell) .nycif-events-map-wrap,
  body:has(#nycifMapAppShell) .nycif-events-map-caption,
  body:has(#nycifMapAppShell) .wordads-tag,
  body:has(#nycifMapAppShell) #wpconsent-root { display:none !important; }
  body:has(#nycifMapAppShell) .nycif-page-main { max-width:none !important; margin:0 !important; padding:0 !important; }
  #nycifMapAppShell { position:fixed; inset:0; width:100%; height:100%; z-index:99999; background:#0b1117; }
  #nycifMapAppShell iframe { display:block; width:100%; height:100%; border:0; }
</style>
<div id="nycifMapAppShell">
  <iframe
    title="NYC In Focus Event Map"
    src="https://setoxxx.github.io/nycif-field-desk/?v=public-map-v10&resetFilters=1&feeds=main"
    loading="eager"
    referrerpolicy="strict-origin-when-cross-origin"
    allow="geolocation; fullscreen"
    allowfullscreen></iframe>
</div>
```

Note: `/map/` uses `loading="eager"` (primary surface). Shortcode embeds use `lazy`.

### DO NOT

- Add `[nycif_events_map]` shortcode on this page
- Use JavaScript to set `iframe.src` (smart quotes break on WordPress)
- Pin `feeds=` to a git commit SHA
- Change iframe to 85vh or add border-radius

---

## TASK C — Post-deploy automated QA (WordPress HTML)

```bash
curl -sL 'https://nycinfocus.com/map/' | python3 -c "
import sys, re
h = sys.stdin.read()
checks = [
    ('nycifMapAppShell div', bool(re.search(r'<div id=\"nycifMapAppShell\"', h))),
    ('hide rules', 'body:has(#nycifMapAppShell)' in h),
    ('public-map-v10', 'public-map-v10' in h),
    ('feeds=main', 'feeds=main' in h or 'feeds&#038;main' in h or 'feeds&amp;main' in h),
    ('no plugin wrap', not re.search(r'<div class=\"nycif-events-map-wrap\"', h)),
    ('no caption', not re.search(r'<p class=\"nycif-events-map-caption\"', h)),
    ('no shortcode text', '[nycif_events_map]' not in h),
    ('no staged feed', 'feed=staged' not in h),
]
for name, ok in checks:
    print(('PASS' if ok else 'FAIL') + ' ' + name)
"
```

All lines must be PASS.

---

## TASK D — Post-deploy human QA on nycinfocus.com/map/

Repeat GATE 4 checks on **https://nycinfocus.com/map/** (not just GitHub Pages).

---

## Rollback (if production breaks)

### WordPress shell only broken

Restore previous Custom HTML from revision history in page 2647, or reinstall last known-good iframe `src` **after** confirming that Field Desk commit still exists on Pages.

### Map application broken

1. Identify last good `nycif-field-desk` commit SHA from GitHub.
2. Revert or cherry-pick deploy on `nycif-live-feeds` `main` and re-run **Deploy to Field Desk Pages**.
3. Re-run GATE 3 preflight before touching WordPress.

### Plugin broken

Reinstall `nycif-events-map-1.4.0-rc1.zip` (documented rollback) — but note that version has the retired commit-pinned feed and should not remain canonical.

**Changing `v=` alone without redeploying Field Desk does not roll back application code.**

---

## REPORT BACK (required template)

```
NYCIF map release deploy report
Date:
Agent:

GATE 0 — field-desk-complete-map-deploy workflow on main: PASS/FAIL (link to run)
GATE 1 — understood v= is cache-bust only: YES
GATE 2 — recorded SHAs:
  field_desk_sha:
  live_feeds_sha:
  feed_total:
  feed_generated_at_utc:
GATE 3 — preflight script: PASS/FAIL (paste output)
GATE 4 — GitHub Pages smoke test: PASS/FAIL

TASK A — plugin 1.5.0-rc2 uploaded: YES/NO
  Settings page version:
  PHP constants verified: YES/NO

TASK B — page 2647 updated: YES/NO
  iframe src (exact):

TASK C — curl QA on /map/: (paste all lines)

TASK D — nycinfocus.com/map/ human QA: PASS/FAIL
  Desktop:
  Mobile:
  Resize:

Deviations from canonical HTML/plugin: none / (describe)
```

---

## Reference links

- Freeze doc: `docs/wordpress-plugin-deploy/nycinfocus-map-page-v1-freeze.md`
- Display modes: `docs/wordpress-plugin-deploy/PUBLIC-MAP-DISPLAY-MODES.md`
- Freeze JSON: `status/nycif-map-v1-freeze.json`
- Plugin directory: `docs/wordpress-plugin-deploy/nycif-events-map/`

# ChatGPT WordPress deploy prompt (copy/paste)

Use this when **Cursor / GitHub** has merged map changes and you need **ChatGPT (or any agent with WordPress admin access)** to update https://nycinfocus.com/map/.

---

## Prompt to paste into ChatGPT

```
You have WordPress admin access for nycinfocus.com. Deploy the NYC In Focus public map shell to the production /map/ page.

READ FIRST (repo contract):
- Page ID: 2647
- URL: https://nycinfocus.com/map/
- Editor: Code Editor ONLY (not visual editor — avoids smart-quote corruption)
- Template: Blank
- Content: ONE Custom HTML block — no shortcode, no page title block in content

CURRENT CANONICAL VALUES (from nycif-live-feeds freeze doc — verify before editing):
- Runtime cache bust `v`: public-map-v10
- iframe src (exact):
  https://setoxxx.github.io/nycif-field-desk/?v=public-map-v10&resetFilters=1&feeds=main
- feeds MUST be `main` (approved public discovery). Never use staged, commit SHA, or feed=staged.

TASK:
1. WP Admin → Pages → open page 2647 (/map/)
2. Switch to Code Editor
3. Replace the entire page content with the canonical HTML block below (straight ASCII quotes only)
4. Click Update / Publish
5. Run the automated QA curl command below and paste output
6. Open https://nycinfocus.com/map/ in browser:
   - Desktop width (≥721px): fullscreen map, Filters/GPS/Bug upper-right, week strip centered top
   - Mobile width (≤720px): fullscreen map, compact week strip below brand row, Near Me hidden
7. Confirm no visible site header, footer, H1, caption, or raw CSS text on the page

CANONICAL HTML (copy verbatim):

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
    referrerpolicy="no-referrer-when-downgrade"
    allow="geolocation; fullscreen"
    allowfullscreen></iframe>
</div>

DO NOT:
- Add [nycif_events_map] shortcode
- Use frame.src = "..." in a script (smart quotes break on WordPress)
- Pin feeds= to a git commit hash
- Change iframe to 85vh or add border-radius (must stay fullscreen)
- Edit location_cache, staged feeds, or GPS review data (display shell only)

AUTOMATED QA (run in terminal after save):

curl -sL 'https://nycinfocus.com/map/' | python3 -c "
import sys, re
h = sys.stdin.read()
checks = [
    ('nycifMapAppShell div', bool(re.search(r'<div id=\"nycifMapAppShell\"', h))),
    ('hide rules', 'body:has(#nycifMapAppShell)' in h),
    ('public-map-v10', 'public-map-v10' in h),
    ('feeds=main', 'feeds=main' in h or 'feeds&#038;main' in h),
    ('no plugin wrap', not re.search(r'<div class=\"nycif-events-map-wrap\"', h)),
    ('no caption', not re.search(r'<p class=\"nycif-events-map-caption\"', h)),
    ('no shortcode text', '[nycif_events_map]' not in h),
]
for name, ok in checks:
    print(('PASS' if ok else 'FAIL') + ' ' + name)
"

REPORT BACK:
- Whether page save succeeded
- Full curl QA output (all lines must be PASS)
- Desktop + mobile viewport confirmation
- Any diff from canonical HTML if you had to adjust anything
```

---

## When to send this prompt

Send after **both** of these are true:

1. GitHub Actions **Deploy to Field Desk Pages** succeeded on `main` (map runtime live on GitHub Pages).
2. The freeze doc lists the new `v=` token: `docs/wordpress-plugin-deploy/nycinfocus-map-page-v1-freeze.md`

If the `v=` value in the prompt above is stale, read the freeze doc **Canonical iframe src** section and replace `public-map-v10` in the prompt before pasting.

---

## What ChatGPT cannot do (Cursor/backend agent owns this)

- Bump map JS/CSS in `docs/field-desk-map-deploy/`
- Merge PRs or trigger Field Desk Pages deploy
- Promote GPS rows to `location_cache.json` or change public feeds
- Enable supplemental calendar/Parks on `feeds=main` without explicit approval

---

## Related files

| File | Purpose |
|------|---------|
| `nycinfocus-map-page-v1-freeze.md` | Signed-off HTML + QA checklist |
| `status/nycif-map-v1-freeze.json` | Machine-readable canonical iframe src |
| `nycif-events-map/nycif-events-map.php` | Plugin for **other** pages only — not `/map/` |

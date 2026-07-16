# nycinfocus.com/map/ — Map v1 display freeze (2026-07-16)

**Status:** FROZEN — signed off after live QA PASS  
**URL:** https://nycinfocus.com/map/  
**WordPress page ID:** 2647  
**Editor:** Code Editor only for this page (avoid smart-quote corruption)

Any agent or human improving NYC In Focus must read this before touching the Map page, theme template, or embed params. The saved page content and the live rendered viewport must match this contract.

---

## What visitors must see

- **Fullscreen map only** — edge-to-edge on desktop and mobile
- **No visible** site header, footer, nav, H1 title, caption, ads slot, or plugin shortcode chrome
- **No visible CSS** as plain text in the page body
- **One map iframe** loading the approved public discovery feed

Theme header/footer/H1 may remain in the HTML DOM; CSS hides them. That is intentional. Do not remove the hide rules to “simplify” the page.

---

## What the page must contain (exact pattern)

**Template:** Blank  
**Content:** ONE Custom HTML block — nothing else (no `[nycif_events_map]` shortcode, no separate iframe block, no page title block in content)

**SEO excerpt / meta description:**

```
Live NYC public events map from NYC In Focus.
```

### Canonical page content (copy verbatim; straight ASCII quotes only)

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
    src="https://setoxxx.github.io/nycif-field-desk/?v=public-map-v07&resetFilters=1&feeds=main"
    loading="eager"
    referrerpolicy="no-referrer-when-downgrade"
    allow="geolocation; fullscreen"
    allowfullscreen></iframe>
</div>
```

### Canonical iframe `src` (must match exactly)

```
https://setoxxx.github.io/nycif-field-desk/?v=public-map-v07&resetFilters=1&feeds=main
```

| Param | Required value | Notes |
|-------|----------------|-------|
| `v` | `public-map-v07` | Field Desk runtime cache bust; bump only after Pages deploy + QA |
| `feeds` | `main` | Approved public discovery feed — **not** a commit hash, **not** `staged` |
| `resetFilters` | `1` | Clean boot filters on load |

**Retired (do not use):** `?feed=staged`, `v=nycif-map-publish-02`, `feeds=<git-commit-sha>`, `85vh` embedded shortcode layout.

---

## Do NOT do on /map/

| Action | Why it breaks the freeze |
|--------|--------------------------|
| Add `[nycif_events_map]` shortcode | Duplicate wrap, 85vh cap, visible caption |
| Replace shell with plugin-only iframe | Loses fullscreen hide rules |
| Put CSS outside `<style>...</style>` | Visible CSS text on page |
| Use `frame.src = "..."` in a `<script>` block | Smart quotes break JS on WordPress |
| Pin `feeds=` to a commit SHA | Bypasses approved `main` feed contract |
| Remove `#nycifMapAppShell` | Theme header/footer/title become visible |
| Change iframe to `85vh` or add `border-radius` | Not fullscreen |

The `nycif-events-map` plugin remains valid for **other** pages that need an in-article embed. It is **not** the production shell for `/map/`.

---

## Live QA checklist (run after any WordPress change)

```bash
curl -sL 'https://nycinfocus.com/map/' | python3 -c "
import sys, re
h = sys.stdin.read()
checks = [
    ('nycifMapAppShell div', bool(re.search(r'<div id=\"nycifMapAppShell\"', h))),
    ('hide rules', 'body:has(#nycifMapAppShell)' in h),
    ('public-map-v07', 'public-map-v07' in h),
    ('feeds=main', 'feeds=main' in h or 'feeds&#038;main' in h),
    ('no plugin wrap', not re.search(r'<div class=\"nycif-events-map-wrap\"', h)),
    ('no caption', not re.search(r'<p class=\"nycif-events-map-caption\"', h)),
    ('no shortcode text', '[nycif_events_map]' not in h),
    ('no commit pin', 'feeds=bf7dedd' not in h),
]
for name, ok in checks:
    print(('PASS' if ok else 'FAIL') + ' ' + name)
"
```

**Human check (required):** open https://nycinfocus.com/map/ in a browser — fullscreen map only, no header/footer/caption visible. Text crawlers may still see hidden DOM nodes; trust the viewport.

**Pass criteria:** all automated checks PASS + human viewport confirms fullscreen map.

---

## Related deploy surfaces

| Surface | Role |
|---------|------|
| GitHub Pages map | https://setoxxx.github.io/nycif-field-desk/ — map runtime (`public-map-v07`) |
| WordPress `/map/` | Fullscreen iframe shell → Pages URL above |
| `docs/field-desk-map-deploy/` | Field Desk file deploy handshake |
| `docs/wordpress-plugin-deploy/nycif-events-map/` | Plugin for non-/map/ embeds only |

When Field Desk Pages updates (`v=` bump), update the iframe `src` on `/map/` in the same release window, then re-run this checklist.

---

## Freeze sign-off record

| Field | Value |
|-------|-------|
| Signed off | 2026-07-16 |
| Live QA | PASS — fullscreen shell, `public-map-v07`, `feeds=main` |
| Repo | `nycif-live-feeds` docs only; WordPress content is human/ChatGPT deploy |

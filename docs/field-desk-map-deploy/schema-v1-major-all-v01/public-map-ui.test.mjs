// Public map UI contract tests: static checks against canonical deploy sources.
// Run from live-feeds: node --test docs/field-desk-map-deploy/schema-v1-major-all-v01/public-map-ui.test.mjs
// Run from field-desk: node --test tools/public-map/public-map-ui.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const testDir = dirname(fileURLToPath(import.meta.url));
const fieldDeskRoot = join(testDir, '..', '..');
const usesCanonicalDeploySources = existsSync(join(testDir, 'index.html'));
const repoRoot = usesCanonicalDeploySources ? testDir : fieldDeskRoot;
const tipJarPath = usesCanonicalDeploySources
  ? join(testDir, '..', 'shared', 'nycif-tip-jar-v01.js')
  : join(fieldDeskRoot, 'nycif-tip-jar-v01.js');

const indexHtml = readFileSync(join(repoRoot, 'index.html'), 'utf8');
const appJs = readFileSync(join(repoRoot, 'app-schema-v1-major-all-v01.js'), 'utf8');
const tipJarSource = readFileSync(tipJarPath, 'utf8');
const publicMapCss = readFileSync(join(repoRoot, 'public-map-v01.css'), 'utf8');

test('production index mounts tip jar beside the NYCIF brand header', () => {
  assert.match(indexHtml, /brand-header-row/);
  assert.match(indexHtml, /public-map-v10/);
  assert.match(indexHtml, /nycif-tip-jar-v01\.js\?v=06/);
});

test('upper-right control stack has Filters, GPS, Bug, then Near Me', () => {
  const stack = /<div class="map-controls"[\s\S]*?<\/div>/.exec(indexHtml);
  assert.ok(stack, 'map-controls stack missing');
  const order = ['layersBtn', 'locateBtn', 'bugBtn', 'nearMeBtn'];
  let last = -1;
  for (const id of order) {
    const at = stack[0].indexOf(`id="${id}"`);
    assert.ok(at > last, `${id} must appear in stack order`);
    last = at;
  }
});

test('tip jar exposes share template and social profile links', () => {
  assert.match(tipJarSource, /You gotta check this out/);
  assert.match(tipJarSource, /navigator\.share/);
  assert.match(tipJarSource, /instagram\.com\/youfoundhowie/);
  assert.match(tipJarSource, /tiktok\.com\/@howardweiss/);
  assert.match(tipJarSource, /youtube\.com\/@youfoundhowie/);
  assert.match(tipJarSource, /www\.nycinfocus\.com\/map/);
  assert.match(tipJarSource, /PUBLIC_MAP_SHARE_URL/);
  assert.match(tipJarSource, /Follow Howard Weiss/);
  assert.match(tipJarSource, /nycif-tip-jar-strobe/);
});

test('public map css anchors brand header left and stacks right controls', () => {
  assert.match(publicMapCss, /\.brand-header-row/);
  assert.match(publicMapCss, /\.map-controls/);
  assert.match(publicMapCss, /Filters, GPS, Bug, then Near Me/);
  assert.match(publicMapCss, /max-width: 720px/);
  assert.match(publicMapCss, /#nearMeBtn/);
});

test('display mode script sets mobile/desktop classes at 720px breakpoint', () => {
  assert.match(indexHtml, /public-display-mode-v01\.js/);
  const displayModeJs = readFileSync(join(repoRoot, 'public-display-mode-v01.js'), 'utf8');
  assert.match(displayModeJs, /max-width: 720px/);
  assert.match(displayModeJs, /dataset\.nycifDisplay/);
  assert.match(displayModeJs, /nycif:display-mode/);
  assert.match(displayModeJs, /NYCIF_DISPLAY_MODE/);
  assert.match(appJs, /nycif:display-mode/);
});

test('filters panel exposes news assignments and readable overlay disclaimer', () => {
  assert.match(indexHtml, /panel-sub-label/);
  assert.match(indexHtml, /News assignments/);
  assert.match(publicMapCss, /\.panel-sub-label/);
  assert.match(publicMapCss, /\.nycif-approved-overlays-note/);
  assert.match(publicMapCss, /#374151/);
});

test('stacked location popups expose scrollable picker, time rows, and side placement', () => {
  assert.match(publicMapCss, /\.popup-stack-scroll/);
  assert.match(publicMapCss, /\.popup-stack-time/);
  assert.match(publicMapCss, /\.nycif-event-popup--side-right/);
  assert.match(publicMapCss, /\.nycif-popup-back/);
  assert.match(appJs, /openStackDetail/);
  assert.match(appJs, /popupPicker/);
  assert.match(appJs, /formatTimeRange/);
  assert.match(appJs, /syncStackPopupPlacement/);
});

test('category filter badges are date-scoped and explain other-day totals', () => {
  assert.match(appJs, /function categoryKeysForEvent/);
  assert.match(appJs, /function categoryOtherDayHint/);
  assert.match(appJs, /selectedDateKey\(\)/);
  assert.match(appJs, /dateMatches\(e\)/);
  assert.match(appJs, /other days/);
  assert.match(appJs, /on map/);
});

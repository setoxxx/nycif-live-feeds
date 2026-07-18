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
  assert.match(indexHtml, /nycif-tip-jar-v01\.js\?v=04/);
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
  assert.match(tipJarSource, /brand-header-row/);
});

test('public map css anchors brand header left and stacks right controls', () => {
  assert.match(publicMapCss, /\.brand-header-row/);
  assert.match(publicMapCss, /\.map-controls/);
  assert.match(publicMapCss, /Filters, GPS, Bug, then Near Me/);
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

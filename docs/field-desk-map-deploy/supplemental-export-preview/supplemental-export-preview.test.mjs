// Supplemental approved export preview tests.
// Run with: node --test tools/public-map/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const source = readFileSync(join(repoRoot, 'supplemental-approved-export-preview-v01.js'), 'utf8');
const redirectSource = readFileSync(join(repoRoot, 'supplemental-preview-desk-redirect.js'), 'utf8');
const deskHtml = readFileSync(join(repoRoot, 'desk.html'), 'utf8');
const previewHtml = readFileSync(join(repoRoot, 'approved-export-preview.html'), 'utf8');
const indexHtml = readFileSync(join(repoRoot, 'index.html'), 'utf8');

function loadWithUrl(href, dataset = {}) {
  const html = { dataset: { ...dataset } };
  const sandbox = {
    window: {},
    document: {
      readyState: 'loading',
      documentElement: html,
      addEventListener() {},
      getElementById() { return null; },
      createElement() { return { appendChild() {} }; },
      head: { appendChild() {} },
      body: { appendChild() {} },
    },
    location: { href },
    URL,
    console: { info() {}, error() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.window.NYCIF_SUPPLEMENTAL_EXPORT_PREVIEW;
}

test('does nothing for public visitors (no preview mode)', () => {
  const api = loadWithUrl('https://setoxxx.github.io/nycif-field-desk/desk.html');
  assert.equal(api.previewExportMode(), false);
  assert.equal(api.deskOverlayMode(), false);
});

test('redirects desk previewExport to standalone unless deskOverlay=1', () => {
  let replaced = null;
  const sandbox = {
    location: {
      href: 'https://setoxxx.github.io/nycif-field-desk/desk.html?previewExport=1',
      replace(url) {
        replaced = url;
      },
    },
    URL,
  };
  vm.createContext(sandbox);
  vm.runInContext(redirectSource, sandbox);
  assert.match(String(replaced), /approved-export-preview\.html$/);
});

test('keeps desk overlay when deskOverlay=1', () => {
  const api = loadWithUrl('https://x/desk.html?previewExport=1&deskOverlay=1');
  assert.equal(api.previewExportMode(), true);
  assert.equal(api.deskOverlayMode(), true);
});

test('standalone page mode uses data attribute only', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  assert.equal(api.standaloneMode(), true);
  assert.equal(api.deskOverlayMode(), false);
});

const previewApi = loadWithUrl('https://x/desk.html?previewExport=1&deskOverlay=1');

test('validateExportPayload accepts supplemental approved export feed', () => {
  const payload = previewApi.validateExportPayload({
    artifact_type: 'supplemental_approved_export_feed',
    production_feed: false,
    promotion_allowed: false,
    events: [],
  });
  assert.equal(payload.artifact_type, 'supplemental_approved_export_feed');
});

test('validateExportPayload refuses GPS review queue artifacts', () => {
  assert.throws(
    () => previewApi.validateExportPayload({ artifact_type: 'gps_manual_approval_queue', events: [] }),
    /Refusing review\/staging artifact/
  );
});

test('validateExportPayload refuses production_feed=true', () => {
  assert.throws(
    () => previewApi.validateExportPayload({
      artifact_type: 'supplemental_approved_export_feed',
      production_feed: true,
      events: [],
    }),
    /production_feed=true/
  );
});

test('normalizePin keeps only approved rows with NYC coordinates', () => {
  const good = previewApi.normalizePin({
    manual_review_status: 'approved',
    production_feed: false,
    promotion_allowed: false,
    lat: 40.75,
    lng: -73.98,
    title: 'Test event',
  }, 0);
  assert.ok(good);
  assert.equal(good.title, 'Test event');

  assert.equal(previewApi.normalizePin({ manual_review_status: 'pending', lat: 40.75, lng: -73.98 }, 1), null);
  assert.equal(previewApi.normalizePin({ manual_review_status: 'approved', lat: 0, lng: 0 }, 2), null);
});

test('desk.html loads preview module but production index.html does not', () => {
  assert.match(deskHtml, /supplemental-approved-export-preview-v01\.js/);
  assert.match(previewHtml, /supplemental-approved-export-preview-v01\.js/);
  assert.ok(!/supplemental-approved-export-preview-v01\.js/.test(indexHtml), 'production index must not load preview module');
});

test('preview terminology is not added to production index markup', () => {
  assert.ok(!/previewExport/.test(indexHtml), 'no previewExport gate in production index');
  assert.ok(!/Supplemental approved export/.test(indexHtml), 'no supplemental preview label in production index');
});

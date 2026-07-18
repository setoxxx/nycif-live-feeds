// Supplemental approved export preview tests.
// Run with: node --test tools/public-map/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const testDir = dirname(fileURLToPath(import.meta.url));
const previewDir = existsSync(join(testDir, 'supplemental-approved-export-preview-v01.js'))
  ? testDir
  : join(testDir, '..', '..');
const deployRoot = existsSync(join(previewDir, 'index.html'))
  ? previewDir
  : join(previewDir, '..');
const canonicalProductionIndex = join(deployRoot, 'schema-v1-major-all-v01', 'index.html');
const source = readFileSync(join(previewDir, 'supplemental-approved-export-preview-v01.js'), 'utf8');
const tipJarCandidates = [
  join(previewDir, '..', 'shared', 'nycif-tip-jar-v01.js'),
  join(previewDir, 'nycif-tip-jar-v01.js'),
];
const tipJarPath = tipJarCandidates.find(candidate => existsSync(candidate));
if (!tipJarPath) {
  throw new Error(`nycif-tip-jar-v01.js not found (checked: ${tipJarCandidates.join(', ')})`);
}
const tipJarSource = readFileSync(tipJarPath, 'utf8');
const redirectSource = readFileSync(join(previewDir, 'supplemental-preview-desk-redirect.js'), 'utf8');
const previewHtml = readFileSync(join(previewDir, 'approved-export-preview.html'), 'utf8');
const deskHtmlPath = existsSync(join(previewDir, 'desk.html'))
  ? join(previewDir, 'desk.html')
  : existsSync(join(deployRoot, 'desk.html'))
    ? join(deployRoot, 'desk.html')
    : null;
const indexHtmlPath = existsSync(canonicalProductionIndex)
  ? canonicalProductionIndex
  : existsSync(join(previewDir, 'index.html'))
    ? join(previewDir, 'index.html')
    : existsSync(join(deployRoot, 'index.html'))
      ? join(deployRoot, 'index.html')
      : canonicalProductionIndex;
const deskHtml = deskHtmlPath ? readFileSync(deskHtmlPath, 'utf8') : '';
const indexHtml = readFileSync(indexHtmlPath, 'utf8');

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
    date: '2026-07-18',
    title: 'Test event',
  }, 0);
  assert.ok(good);
  assert.equal(good.title, 'Test event');
  assert.equal(good.dateKey, '2026-07-18');

  assert.equal(previewApi.normalizePin({ manual_review_status: 'pending', lat: 40.75, lng: -73.98, date: '2026-07-18' }, 1), null);
  assert.equal(previewApi.normalizePin({ manual_review_status: 'approved', lat: 0, lng: 0, date: '2026-07-18' }, 2), null);
  assert.equal(previewApi.normalizePin({ manual_review_status: 'approved', lat: 40.75, lng: -73.98 }, 3), null);
});

test('desk.html loads preview module but production index.html does not', () => {
  assert.match(previewHtml, /supplemental-approved-export-preview-v01\.js/);
  assert.ok(!/supplemental-approved-export-preview-v01\.js/.test(indexHtml), 'production index must not load preview module');
  if (deskHtmlPath) {
    assert.match(deskHtml, /supplemental-approved-export-preview-v01\.js/);
  }
});

test('preview terminology is not added to production index markup', () => {
  assert.ok(!/previewExport/.test(indexHtml), 'no previewExport gate in production index');
  assert.ok(!/Supplemental approved export/.test(indexHtml), 'no supplemental preview label in production index');
});

test('uses public map RC marker cap and viewport buffer', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  assert.equal(api.MARKER_SOFT_CAP, 600);
  assert.equal(api.VIEWPORT_BUFFER, 0.15);
  assert.ok(!/nycif-supplemental-dots-canvas/.test(source), 'canvas layer removed');
  assert.match(source, /layerGroup/);
  assert.match(source, /divIcon/);
  assert.match(source, /anniversary-badge/);
  assert.match(source, /showPrecinctGeofenceForPin/);
});

test('anniversaryBadgeLabel renders year count or annual fallback', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  assert.equal(api.anniversaryBadgeLabel({ culturalAnniversary: true, anniversaryNumber: 15 }), '15');
  assert.equal(api.anniversaryBadgeLabel({ culturalAnniversary: true }), 'A');
});

test('standalone preview html uses cache bust v=10', () => {
  assert.match(previewHtml, /supplemental-approved-export-preview-v01\.js\?v=10/);
  assert.match(previewHtml, /cultural anniversary badges/i);
});

test('tip jar links include Cash App, Venmo, and PayPal', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  assert.equal(api.TIP_JAR_LINKS.length, 3);
  assert.match(previewHtml, /nycif-tip-jar-v01\.js/);
  assert.match(source, /NYCIF_TIP_JAR/);
  assert.match(tipJarSource, /nycif-tip-jar/);
  assert.match(tipJarSource, /cash\.app\/\$NYCINFOCUS/);
  assert.match(tipJarSource, /venmo\.com\/u\/Howie-Doin/);
  assert.match(tipJarSource, /py\.pl\/oxvv2Mgg0bztfniKXwpQWA/);
});

test('production index loads shared tip jar module', () => {
  assert.match(indexHtml, /nycif-tip-jar-v01\.js/);
  assert.ok(!/supplemental-approved-export-preview-v01\.js/.test(indexHtml));
});

test('formatMapRenderMeta reports cap when viewport exceeds soft cap', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  const capped = api.formatMapRenderMeta({
    drawn: 600,
    inView: 1200,
    total: 249,
    loadedTotal: 3493,
    selectedDate: '2026-07-18',
  });
  assert.match(capped, /249 events on today/);
  assert.match(capped, /3,493 loaded total/);
  assert.match(capped, /600 shown of 1,200 in view/);
});

test('filterPinsForSelectedDate matches public map single-day rule', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  const pins = [
    { date: '2026-07-18', lat: 40.75, lng: -73.98, title: 'A' },
    { date: '2026-07-19', lat: 40.76, lng: -73.97, title: 'B' },
    { date: '2026-07-18', lat: 40.77, lng: -73.96, title: 'C' },
  ];
  const filtered = api.filterPinsForSelectedDate(pins, '2026-07-18');
  assert.equal(filtered.length, 2);
  assert.deepEqual(filtered.map(p => p.title), ['A', 'C']);
});

test('dateChipModel exposes eight forward day choices', () => {
  const api = loadWithUrl('https://x/approved-export-preview.html', {
    nycifSupplementalExportPreview: '1',
  });
  const chips = api.dateChipModel(new Date(2026, 6, 18));
  assert.equal(chips.length, 8);
  assert.equal(chips[0].label, 'Today');
  assert.equal(chips[1].label, 'Tomorrow');
});

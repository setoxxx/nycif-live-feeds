#!/usr/bin/env node
/**
 * C5P — merge-not-replace publish of one Howard-approved major-event row.
 * Adds only source_record_id 914695 (2026 Queensboro Dance Festival).
 * Preserves existing production rows and all manual/NYPD records.
 */
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const APPROVED_SOURCE_RECORD_ID = '914695';
const HOWARD_APPROVAL_PHRASE =
  'I approve creating a separate setoxxx/nycif-live-feeds production-publish PR that preserves the 11 manual/NYPD records, adds only the approved-geocode Queensboro Dance Festival row, keeps the 896 needs-review rows blocked, creates rollback snapshots first, and does not touch WordPress or public UI.';

const APPROVED_PREVIEW_ROW = {
  id: 'prototype-tvpp-914695',
  title: '2026 Queensboro Dance Festival',
  date: '2026-07-02',
  start_date_time: '2026-07-02T18:00:00.000',
  end_date_time: '2026-07-02T19:00:00.000',
  borough: 'Queens',
  location: 'Flushing Meadows Corona Park: Around the Unisphere',
  display_location: 'Flushing Meadows Corona Park: Around the Unisphere',
  lat: 40.739312,
  lng: -73.842193,
  photo_pick: true,
  priority_score: 75,
  verification_status: 'source_listed',
  source_name: 'NYC Permitted Event Information',
  source_url: 'https://data.cityofnewyork.us/resource/tvpp-9vvx.json',
  source_record_id: '914695',
  event_agency: 'Parks Department',
  event_type: 'Special Event',
  street_closure_type: 'N/A',
  major_score: 75,
  major_reason: 'festival_or_cultural_event',
  major_reason_tags: ['festival_or_cultural_event'],
  expected_crowd_signal: 'source_listed_public_event',
  safety_note:
    'Source-listed public event listing. Field/photo candidate. Confirm before traveling. Event details can change.',
  geocode_source: 'normalized_exact',
  approved_geocode_applied: true
};

const PATHS = {
  major: path.join(ROOT, 'nycif_major_radar_map_events.json'),
  all: path.join(ROOT, 'nycif_all_radar_map_events.json'),
  backupsDir: path.join(ROOT, 'data/backups'),
  report: path.join(ROOT, 'data/reports/production_feed_publish_report.json')
};

function isManualRecord(row) {
  if (!row || typeof row !== 'object') return false;
  if (row.verification_status === 'nypd_field_intel') return true;
  if (row._manual_priority) return true;
  if (/^nypd-hardwrite-/i.test(String(row.id || ''))) return true;
  if (/manual|hardwrite|hard-write|field[-_ ]intel|nypd/i.test(String(row.source_file || ''))) return true;
  return false;
}

function rowKey(row) {
  return String(row.source_record_id || row.id || '');
}

function previewToProductionRow(row) {
  const lat = Number(row.lat);
  const lng = Number(row.lng);
  const searchLabel = [row.title, row.display_location || row.location, row.borough]
    .filter(Boolean)
    .join(' ');

  return {
    id: String(row.source_record_id || row.id),
    title: row.title,
    date: row.date,
    start_date_time: row.start_date_time || null,
    end_date_time: row.end_date_time || null,
    location: row.location || null,
    display_location: row.display_location || row.location || null,
    borough: row.borough || null,
    lane: 'general',
    color: 'gray',
    photo_pick: Boolean(row.photo_pick),
    priority_score: row.priority_score ?? row.major_score ?? 0,
    verification_status: row.verification_status || 'source_listed',
    lat,
    lng,
    source_name: row.source_name || null,
    source_url: row.source_url || null,
    source_record_id: String(row.source_record_id || ''),
    event_agency: row.event_agency || null,
    event_type: row.event_type || null,
    street_closure_type: row.street_closure_type || null,
    geocode_source: row.geocode_source || null,
    geocode_confidence: 'high',
    assignment_feed: 'major',
    major_score: row.major_score ?? null,
    major_reason: row.major_reason || null,
    major_reason_tags: row.major_reason_tags || [],
    expected_crowd_signal: row.expected_crowd_signal || 'source_listed_public_event',
    safety_note: row.safety_note || null,
    search_label: searchLabel,
    google_maps_url: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`,
    field_default: true,
    approved_geocode_applied: true,
    production_publish_phase: 'C5P',
    c5p_publish_source: 'setoxxx/nycif-field-desk/data/preview_major_feed.json'
  };
}

function applyApprovedGeocodeUpdate(existing, approvedRow) {
  return {
    ...existing,
    lat: approvedRow.lat,
    lng: approvedRow.lng,
    display_location: approvedRow.display_location,
    geocode_source: approvedRow.geocode_source,
    geocode_confidence: approvedRow.geocode_confidence,
    approved_geocode_applied: true,
    verification_status: approvedRow.verification_status,
    safety_note: approvedRow.safety_note,
    source_name: approvedRow.source_name,
    source_url: approvedRow.source_url,
    source_record_id: approvedRow.source_record_id,
    major_reason: approvedRow.major_reason,
    major_score: approvedRow.major_score,
    priority_score: approvedRow.priority_score,
    expected_crowd_signal: approvedRow.expected_crowd_signal,
    google_maps_url: approvedRow.google_maps_url,
    search_label: approvedRow.search_label,
    start_date_time: approvedRow.start_date_time ?? existing.start_date_time,
    end_date_time: approvedRow.end_date_time ?? existing.end_date_time,
    production_publish_phase: approvedRow.production_publish_phase,
    c5p_publish_source: approvedRow.c5p_publish_source
  };
}

function upsertApprovedRow(rows, approvedRow, { sortRows = false } = {}) {
  const targetId = String(approvedRow.source_record_id || approvedRow.id || '');
  let updated = false;
  let added = false;

  const nextRows = rows.map(row => {
    const rowId = String(row.id || '');
    const rowSourceId = String(row.source_record_id || '');
    if (rowId === targetId || rowSourceId === targetId) {
      updated = true;
      return applyApprovedGeocodeUpdate(row, approvedRow);
    }
    return row;
  });

  if (!updated) {
    nextRows.push(approvedRow);
    added = true;
  }

  if (sortRows) {
    nextRows.sort((a, b) =>
      (Number(b.priority_score) || Number(b.major_score) || 0) - (Number(a.priority_score) || Number(a.major_score) || 0)
      || String(a.start_date_time || a.date || '').localeCompare(String(b.start_date_time || b.date || ''))
    );
  }

  return { rows: nextRows, added, updated, existing: updated };
}

async function readJsonArray(filePath) {
  const raw = await readFile(filePath, 'utf8');
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : (parsed.events || []);
}

async function main() {
  const generatedAt = new Date().toISOString();
  const stamp = generatedAt.replace(/[:.]/g, '-');
  await mkdir(PATHS.backupsDir, { recursive: true });
  await mkdir(path.dirname(PATHS.report), { recursive: true });

  const majorBefore = await readJsonArray(PATHS.major);
  const allBefore = await readJsonArray(PATHS.all);
  const manualBefore = majorBefore.filter(isManualRecord);
  const approvedProductionRow = previewToProductionRow(APPROVED_PREVIEW_ROW);

  const majorBackup = path.join(PATHS.backupsDir, `nycif_major_radar_map_events.${stamp}.json`);
  const allBackup = path.join(PATHS.backupsDir, `nycif_all_radar_map_events.${stamp}.json`);
  await copyFile(PATHS.major, majorBackup);
  await copyFile(PATHS.all, allBackup);

  const majorMerge = upsertApprovedRow(majorBefore, approvedProductionRow, { sortRows: false });
  const allMerge = upsertApprovedRow(allBefore, approvedProductionRow, { sortRows: false });
  const manualAfter = majorMerge.rows.filter(isManualRecord);

  if (manualAfter.length !== manualBefore.length) {
    throw new Error(`manual record count changed: before=${manualBefore.length} after=${manualAfter.length}`);
  }

  await writeFile(PATHS.major, `${JSON.stringify(majorMerge.rows, null, 2)}\n`, 'utf8');
  await writeFile(PATHS.all, `${JSON.stringify(allMerge.rows, null, 2)}\n`, 'utf8');

  const report = {
    phase: 'C5P',
    mode: 'production_publish_merge_not_replace',
    generated_at: generatedAt,
    howard_approval_phrase: HOWARD_APPROVAL_PHRASE,
    howard_approval_recorded: true,
    field_desk_readiness_report: 'setoxxx/nycif-field-desk/data/reports/major_event_production_readiness_report.json',
    field_desk_preview_report: 'setoxxx/nycif-field-desk/data/reports/preview_major_feed_report.json',
    preview_review_url: 'https://setoxxx.github.io/nycif-field-desk/preview-major-feed-review.html?v=c5g4-01',
    approved_source_record_ids: [APPROVED_SOURCE_RECORD_ID],
    approved_rows_published: [
      {
        source_record_id: APPROVED_SOURCE_RECORD_ID,
        title: APPROVED_PREVIEW_ROW.title,
        date: APPROVED_PREVIEW_ROW.date,
        borough: APPROVED_PREVIEW_ROW.borough
      }
    ],
    blocked_needs_review_rows_not_published: 896,
    preserved_manual_records_before: manualBefore.length,
    preserved_manual_records_after: manualAfter.length,
    manual_records_removed: 0,
    merge_strategy: 'merge_not_replace',
    files_modified: [
      'nycif_major_radar_map_events.json',
      'nycif_all_radar_map_events.json'
    ],
    files_not_modified: [
      'data/nycif_staged_live_events.json',
      'data/location_cache.json'
    ],
    wordpress_modified: false,
    public_ui_modified: false,
    rollback_backups: {
      major: path.relative(ROOT, majorBackup),
      all: path.relative(ROOT, allBackup)
    },
    publish_action: {
      major: majorMerge.added ? 'added' : (majorMerge.updated ? 'updated_approved_geocode' : 'unchanged'),
      all: allMerge.added ? 'added' : (allMerge.updated ? 'updated_approved_geocode' : 'unchanged')
    },
    counts: {
      major_rows_before: majorBefore.length,
      major_rows_after: majorMerge.rows.length,
      major_rows_added: majorMerge.added ? 1 : 0,
      major_rows_updated: majorMerge.updated ? 1 : 0,
      all_rows_before: allBefore.length,
      all_rows_after: allMerge.rows.length,
      all_rows_added: allMerge.added ? 1 : 0,
      all_rows_updated: allMerge.updated ? 1 : 0
    },
    production_feed_urls: [
      'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_major_radar_map_events.json',
      'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/nycif_all_radar_map_events.json'
    ],
    post_merge_verification_required: [
      'Verify raw GitHub URLs after merge',
      'Browser-test public map default view',
      'Do not touch WordPress until feed URLs verified good'
    ]
  };

  await writeFile(PATHS.report, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

  console.log(`major_rows_before=${report.counts.major_rows_before}`);
  console.log(`major_rows_after=${report.counts.major_rows_after}`);
  console.log(`all_rows_before=${report.counts.all_rows_before}`);
  console.log(`all_rows_after=${report.counts.all_rows_after}`);
  console.log(`preserved_manual_records=${report.preserved_manual_records_after}`);
  console.log(`manual_records_removed=${report.manual_records_removed}`);
  console.log(`approved_source_record_id=${APPROVED_SOURCE_RECORD_ID}`);
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});

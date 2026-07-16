/**
 * News Desk + Parade Census QA panel for God View admin.
 * Read-only — loads civic_people_facing_godview_digest.json from live-feeds.
 */
(() => {
  'use strict';
  const VERSION = 'news-desk-godview-panel-v01';
  const LIVE_FEEDS = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds';
  const BRANCHES = ['main', 'cursor/citywide-parade-census-bfb8'];

  function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function fmt(v) {
    return Number.isFinite(Number(v)) ? Number(v).toLocaleString() : '0';
  }

  async function fetchDigest() {
    let last = null;
    for (const branch of BRANCHES) {
      try {
        const url = `${LIVE_FEEDS}/${branch}/data/civic_people_facing_godview_digest.json?cache=${Date.now()}`;
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) {
          last = new Error(`${branch}: HTTP ${res.status}`);
          continue;
        }
        return { branch, payload: await res.json() };
      } catch (e) {
        last = e;
      }
    }
    throw last || new Error('Could not load civic godview digest');
  }

  function render(root, branch, digest) {
    const checklist = digest.news_desk_checklist || {};
    const census = digest.parade_census || {};
    const assignment = checklist.assignment_mode_link
      || 'https://setoxxx.github.io/nycif-field-desk/?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&assignment=1';

    root.innerHTML = `
      <div class="notice violet">News Desk + Parade Census ${esc(VERSION)} — read-only staging QA. Not a publish control.</div>
      <div class="notice ok">Loaded from <code>${esc(branch)}</code> · ${esc(digest.public_map_policy || 'Staging only')}</div>
      <div class="grid">
        <div class="stat"><div class="label">Checklist QA</div><div class="value">${checklist.qa_pass ? 'PASS' : 'CHECK'}</div><div class="detail">total ${esc(fmt(checklist.total_rows))}</div></div>
        <div class="stat"><div class="label">Today stories</div><div class="value">${esc(fmt(checklist.today_count))}</div><div class="detail">priority unchecked ${esc(fmt(checklist.priority_unchecked_count))}</div></div>
        <div class="stat"><div class="label">Parade census QA</div><div class="value">${census.qa_pass ? 'PASS' : 'CHECK'}</div><div class="detail">merged ${esc(fmt(census.merged_total))}</div></div>
        <div class="stat"><div class="label">Priority events</div><div class="value">${esc(fmt(census.priority_event_count))}</div><div class="detail">anchor matches ${esc(fmt(census.anchor_permit_matches))}</div></div>
        <div class="stat"><div class="label">Map-ready checklist</div><div class="value">${esc(fmt(checklist.map_ready_count))}</div><div class="detail">list_only demoted rows</div></div>
      </div>
      <div class="links" style="margin-top:12px">
        <a href="${esc(assignment)}" target="_blank" rel="noopener noreferrer">Open Assignment mode</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/news_desk_assignment_checklist.json" target="_blank" rel="noopener noreferrer">Checklist JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/citywide_parade_census_snapshot.json" target="_blank" rel="noopener noreferrer">Parade census JSON</a>
        <a href="https://github.com/setoxxx/nycif-live-feeds/blob/${encodeURIComponent(branch)}/data/news_desk_assignment_checklist_report.json" target="_blank" rel="noopener noreferrer">Checklist QA report</a>
      </div>
    `;
  }

  async function load() {
    const anchor = document.getElementById('live-pipeline-section');
    if (!anchor || document.getElementById('news-desk-god-view')) return;
    const section = document.createElement('section');
    section.className = 'panel';
    section.id = 'news-desk-god-view';
    section.innerHTML = '<h2>News Desk + Parade Census (staging)</h2><div id="news-desk-god-view-body" class="loading-block">Loading checklist + census QA…</div>';
    anchor.before(section);
    const body = document.getElementById('news-desk-god-view-body');
    try {
      const { branch, payload } = await fetchDigest();
      body.className = '';
      render(body, branch, payload);
    } catch (e) {
      body.innerHTML = `<div class="notice danger">Could not load News Desk QA summary.<br><br>${esc(e.message || e)}</div>`;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }

  window.NYCIF_NEWS_DESK_GODVIEW = { version: VERSION, load };
})();

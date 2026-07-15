/**
 * Photographer Assignment Calendar (premium/operator) — Evently-style 2-month God View.
 * Read-only. Clicking a day opens Field Desk focused on that date when possible.
 */
(() => {
  const VERSION = "photographer-calendar-panel-v01";
  const LIVE_FEEDS_BASE = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = ["main", "cursor/photographer-calendar-daily-pull-da92"];
  const PATH = "data/photographer_assignment_calendar_2mo.json";
  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  async function fetchCalendar() {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${PATH}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${PATH}: HTTP ${response.status}`);
          continue;
        }
        return { branch, payload: await response.json() };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error(`Could not load ${PATH}`);
  }

  function fieldDeskUrl(dateKey) {
    const base = "https://setoxxx.github.io/nycif-field-desk/";
    const params = new URLSearchParams({
      v: "civic-people-facing-v01",
      resetFilters: "1",
      feeds: "main",
      date: dateKey || "",
      mode: "all",
    });
    return `${base}?${params.toString()}`;
  }

  function topEventTitle(day) {
    return (day.top_events || [])
      .map((e) => `${e.title || ""} (${e.borough || "?"})`)
      .join(" · ");
  }

  function dayCellHtml(day) {
    if (!day) return `<td class="cal-empty"></td>`;
    const count = day.count || 0;
    const cls = count ? "cal-day has-events" : "cal-day";
    return `<td class="${cls}" data-date="${esc(day.date)}" title="${esc(topEventTitle(day))}">
              <button type="button" class="cal-day-btn" data-date="${esc(day.date)}">
                <span class="cal-date-num">${esc(String(day.date).slice(8))}</span>
                <span class="cal-count">${count ? fmtNum(count) : "—"}</span>
              </button>
            </td>`;
  }

  function weekRowHtml(week) {
    return `<tr>${(week || []).map(dayCellHtml).join("")}</tr>`;
  }

  function monthHtml(month) {
    if (!month) return "";
    const head = DAY_NAMES.map((d) => `<th>${d}</th>`).join("");
    const body = (month.weeks || []).map(weekRowHtml).join("");
    return `
      <div class="cal-month">
        <h3>${esc(month.label)}</h3>
        <div class="table-wrap cal-table-wrap">
          <table class="cal-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }

  function renderDetail(day, payload) {
    const box = document.getElementById("photographer-calendar-detail");
    if (!box) return;
    if (!day) {
      box.innerHTML = `<div class="muted">Click a day with events to see assignment-grade coverage.</div>`;
      return;
    }
    const events = (payload.events || []).filter((e) => e.date === day);
    if (!events.length) {
      box.innerHTML = `<div class="muted">No assignment-grade events on ${esc(day)}.</div>`;
      return;
    }
    const rows = events
      .slice(0, 30)
      .map((e) => {
        const why = (e.why_selected || []).slice(0, 3).join(", ");
        const when = e.start_date_time || day;
        const src = e.source?.dataset || "—";
        const map = e.map_link
          ? `<a href="${esc(e.map_link)}" target="_blank" rel="noopener noreferrer">Map</a>`
          : esc(e.coordinate_status || "list_only");
        return `<tr>
          <td>${esc(when)}</td>
          <td>${esc(e.title)}</td>
          <td>${esc(e.borough || "—")}</td>
          <td>${esc(String(e.display_location || "—").slice(0, 80))}</td>
          <td>${esc(src)}</td>
          <td>${esc(e.lane)} · ${esc(e.assignment_score)}</td>
          <td>${esc(why)}</td>
          <td>${map}</td>
        </tr>`;
      })
      .join("");
    box.innerHTML = `
      <div class="notice ok"><strong>${esc(day)}</strong> — ${fmtNum(events.length)} assignment events ·
        <a href="${esc(fieldDeskUrl(day))}" target="_blank" rel="noopener noreferrer">Open Field Desk map for this day</a>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>When</th><th>Title</th><th>Borough</th><th>Location</th><th>Source</th><th>Lane/score</th><th>Why</th><th>Pin</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  }

  function render(root, branch, payload) {
    const go = (payload.go_shoot_these || []).slice(0, 20);
    const months = payload.months || [];
    root.innerHTML = `
      <style>
        .cal-grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
        .cal-table{min-width:0;width:100%}
        .cal-table th,.cal-table td{text-align:center;padding:6px 4px}
        .cal-day-btn{width:100%;min-height:52px;border:1px solid var(--line);border-radius:10px;background:#0f172a;color:inherit;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
        .cal-day.has-events .cal-day-btn{border-color:rgba(96,165,250,.55);background:rgba(96,165,250,.12)}
        .cal-day-btn:hover{outline:2px solid var(--accent)}
        .cal-date-num{font-weight:750}
        .cal-count{font-size:12px;color:var(--muted)}
        .cal-empty{opacity:.35}
      </style>
      <div class="notice violet">Photographer Assignment Calendar ${esc(VERSION)} — premium/operator money days for the next ~2 months. Read-only. Not a public-map publish control.</div>
      <div class="notice ok">Loaded from <code>${esc(branch)}</code>. ${esc(payload.premium_label || "")} · window ${esc(payload.window_start)} → ${esc(payload.window_end)} · ${fmtNum(payload.total_events)} events across ${fmtNum(payload.days_with_coverage)} days.</div>
      <div class="grid">
        <div class="stat"><div class="label">Assignment events (2 mo)</div><div class="value">${esc(fmtNum(payload.total_events))}</div></div>
        <div class="stat"><div class="label">Days with coverage</div><div class="value">${esc(fmtNum(payload.days_with_coverage))}</div></div>
        <div class="stat"><div class="label">map_ready</div><div class="value">${esc(fmtNum((payload.coordinate_status_counts || {}).map_ready))}</div></div>
        <div class="stat"><div class="label">list_only</div><div class="value">${esc(fmtNum((payload.coordinate_status_counts || {}).list_only))}</div></div>
      </div>
      <div class="cal-grid">${months.map(monthHtml).join("")}</div>
      <h3>Day detail</h3>
      <div id="photographer-calendar-detail" class="muted">Click a day with events to see assignment-grade coverage.</div>
      <h3>Go shoot these (top 20 upcoming)</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Title</th><th>Borough</th><th>Score</th><th>Why</th><th>Desk</th></tr></thead>
        <tbody>
          ${go
            .map(
              (e) => `<tr>
                <td>${esc(e.date)}</td>
                <td>${esc(e.title)}</td>
                <td>${esc(e.borough || "—")}</td>
                <td>${esc(e.assignment_score)}</td>
                <td>${esc((e.why_selected || []).slice(0, 3).join(", "))}</td>
                <td><a href="${esc(fieldDeskUrl(e.date))}" target="_blank" rel="noopener noreferrer">Map day</a></td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table></div>
    `;

    root.querySelectorAll(".cal-day-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dateKey = btn.dataset.date;
        renderDetail(dateKey, payload);
      });
    });
  }

  async function load() {
    const root = document.getElementById("photographer-calendar-view");
    const status = document.getElementById("photographer-calendar-status");
    if (!root) return;
    if (status) status.textContent = "Loading photographer assignment calendar…";
    try {
      const { branch, payload } = await fetchCalendar();
      render(root, branch, payload || {});
      if (status) {
        status.textContent = `Photographer calendar loaded from ${branch} · ${fmtNum(payload.total_events)} events.`;
      }
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load photographer calendar.<br><br>${esc(error?.message || error)}</div>`;
      if (status) status.textContent = "Photographer calendar unavailable.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => load());
  window.NYCIF_PHOTOGRAPHER_CALENDAR = { version: VERSION, load };
})();

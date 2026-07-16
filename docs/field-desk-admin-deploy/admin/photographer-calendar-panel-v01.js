/**
 * Photographer Assignment Calendar (premium/operator) — Money-Day Desk v2.
 * Today/Tomorrow packs + Evently-style 2-month God View. Read-only.
 */
(() => {
  const VERSION = "photographer-calendar-panel-v01";
  const LIVE_FEEDS_BASE = "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds";
  const BRANCH_CANDIDATES = ["main", "cursor/pin-integrity-shoot-day-gate-da92"];
  const CAL_PATH = "data/photographer_assignment_calendar_2mo.json";
  const TODAY_PATH = "data/photographer_money_day_pack_today.json";
  const TOMORROW_PATH = "data/photographer_money_day_pack_tomorrow.json";
  const QUALITY_PATH = "data/photographer_money_day_quality_report.json";
  const VIRAL_PATH = "data/photographer_viral_recurrence_pack_next_14d.json";
  const VIRAL_REPORT_PATH = "data/photographer_viral_recurrence_report.json";
  const PIN_PATH = "data/pin_integrity_gate_report.json";
  const SHOOT_PATH = "data/photographer_shoot_day_certified_pack.json";
  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  }

  function fmtNum(value) {
    return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : "0";
  }

  async function fetchJson(path) {
    let lastError = null;
    for (const branch of BRANCH_CANDIDATES) {
      try {
        const url = `${LIVE_FEEDS_BASE}/${branch}/${path}?v=${Date.now()}`;
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          lastError = new Error(`${branch}/${path}: HTTP ${response.status}`);
          continue;
        }
        return { branch, payload: await response.json() };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error(`Could not load ${path}`);
  }

  function fieldDeskUrl(dateKey, borough) {
    const base = "https://setoxxx.github.io/nycif-field-desk/";
    const params = new URLSearchParams({
      v: "civic-people-facing-v01",
      resetFilters: "1",
      feeds: "main",
      date: dateKey || "",
      mode: "all",
      assignment: "1",
    });
    if (borough) params.set("borough", borough);
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

  function boroughChipsHtml(pack) {
    const chips = (pack.borough_clusters || [])
      .map(
        (c) =>
          `<a class="md-chip" href="${esc(c.field_desk_link || fieldDeskUrl(pack.pack_date, c.borough))}" target="_blank" rel="noopener noreferrer">${esc(c.borough)} · ${fmtNum(c.count)}</a>`
      )
      .join("");
    return chips || `<span class="muted">No map_ready money-day pins</span>`;
  }

  function packCardHtml(pack, heading) {
    if (!pack) {
      return `<div class="md-card"><h3>${esc(heading)}</h3><div class="muted">Pack unavailable.</div></div>`;
    }
    const tops = (pack.go_shoot || [])
      .slice(0, 5)
      .map(
        (e) =>
          `<li><strong>${esc(e.title)}</strong> · ${esc(e.borough || "—")} · score ${esc(e.assignment_score)} · ${esc(e.start_date_time || "time TBD")}</li>`
      )
      .join("");
    return `
      <div class="md-card">
        <h3>${esc(heading)} — ${esc(pack.pack_date)}</h3>
        <div class="muted">${fmtNum(pack.total_events)} money-day · ${fmtNum(pack.map_ready_count)} map_ready</div>
        <div class="md-chips">${boroughChipsHtml(pack)}</div>
        <ol class="md-go">${tops || '<li class="muted">No go-shoot rows</li>'}</ol>
        <p><a href="${esc(pack.field_desk_link || fieldDeskUrl(pack.pack_date))}" target="_blank" rel="noopener noreferrer">Open Field Desk Assignment Mode</a></p>
      </div>`;
  }

  function renderDetail(day, payload) {
    const box = document.getElementById("photographer-calendar-detail");
    if (!box) return;
    if (!day) {
      box.innerHTML = `<div class="muted">Click a day with events to see money-day coverage.</div>`;
      return;
    }
    const events = (payload.events || []).filter((e) => e.date === day);
    if (!events.length) {
      box.innerHTML = `<div class="muted">No money-day events on ${esc(day)}.</div>`;
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
      <div class="notice ok"><strong>${esc(day)}</strong> — ${fmtNum(events.length)} money-day events ·
        <a href="${esc(fieldDeskUrl(day))}" target="_blank" rel="noopener noreferrer">Open Field Desk Assignment Mode</a>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>When</th><th>Title</th><th>Borough</th><th>Location</th><th>Source</th><th>Lane/score</th><th>Why</th><th>Pin</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  }

  function returningHtml(viralPack, viralReport) {
    const magnets = (viralPack && viralPack.crowd_magnets) || [];
    const counts = (viralReport && viralReport.label_counts) || {};
    const rows = magnets.slice(0, 12).map((m) => {
      const prior = m.prior_year_title ? `${m.prior_year_title} (${m.prior_year_date || "?"})` : "—";
      return `<tr>
        <td>${esc(m.date)}</td>
        <td>${esc(m.title)}</td>
        <td>${esc(m.borough || "—")}</td>
        <td>${esc(m.recurrence_label)} · ${esc(m.match_score)}</td>
        <td>${esc(prior)}</td>
        <td><a href="${esc(m.field_desk_link || fieldDeskUrl(m.date))}" target="_blank" rel="noopener noreferrer">Map</a></td>
      </tr>`;
    }).join("");
    return `
      <h3>Returning from last year (next 14 days)</h3>
      <div class="notice ok">Viral recurrence memory — ${fmtNum((viralReport && viralReport.match_count) || 0)} matches · returning_likely ${fmtNum(counts.returning_likely)} · next-14d magnets ${fmtNum((viralPack && viralPack.crowd_magnet_count) || magnets.length)}. FOIL org names join later via sapo_foil_operator_index.json (empty until you paste PDFs).</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Now</th><th>Borough</th><th>Label/score</th><th>Last year</th><th>Desk</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="muted">No recurrence pack loaded yet.</td></tr>'}</tbody>
      </table></div>`;
  }

  function pinIntegrityHtml(pinReport) {
    if (!pinReport) {
      return `<div class="notice warn">Pin integrity report unavailable.</div>`;
    }
    const pass = !!pinReport.qa_pass;
    const badge = pass
      ? `<span class="notice ok">PIN QA PASS</span>`
      : `<span class="notice danger">PIN QA FAIL</span>`;
    return `
      <h3>Pin Integrity (fail-closed)</h3>
      <div class="grid">
        <div class="stat"><div class="label">map_ready certified</div><div class="value">${esc(fmtNum(pinReport.map_ready_after_total))}</div><div class="detail">before ${esc(fmtNum(pinReport.map_ready_before_total))}</div></div>
        <div class="stat"><div class="label">Demotions today</div><div class="value">${esc(fmtNum(pinReport.demotion_count))}</div><div class="detail">Prefer list_only over ocean pins</div></div>
        <div class="stat"><div class="label">Gate</div><div class="value">${pass ? "PASS" : "FAIL"}</div><div class="detail">${badge}</div></div>
      </div>
      <div class="muted detail">Bounds lat ${esc(String((pinReport.bounds || {}).min_lat))}–${esc(String((pinReport.bounds || {}).max_lat))}, lng ${esc(String((pinReport.bounds || {}).min_lng))}–${esc(String((pinReport.bounds || {}).max_lng))}. ZERO bad map_ready required.</div>`;
  }

  function shootDayCardHtml(section, heading) {
    if (!section) {
      return `<div class="md-card"><h3>${esc(heading)}</h3><div class="muted">Certified pack unavailable.</div></div>`;
    }
    const tops = (section.go_shoot_certified || [])
      .slice(0, 6)
      .map(
        (e) =>
          `<li><strong>${esc(e.title)}</strong> · ${esc(e.borough || "—")} · ${esc(e.recurrence_label || "money-day")}${e.certified_pin ? " · certified" : ""}</li>`
      )
      .join("");
    const needs = fmtNum(section.needs_location_count);
    return `
      <div class="md-card">
        <h3>${esc(heading)} — ${esc(section.date)}</h3>
        <div class="muted">${fmtNum(section.certified_pin_count)} certified pins · ${needs} needs location (list only — never fake pins)</div>
        <div class="md-chips">${(section.borough_clusters || [])
          .map(
            (c) =>
              `<a class="md-chip" href="${esc(c.field_desk_link || fieldDeskUrl(section.date, c.borough))}" target="_blank" rel="noopener noreferrer">${esc(c.borough)} · ${fmtNum(c.count)}</a>`
          )
          .join("") || '<span class="muted">No certified pins</span>'}</div>
        <ol class="md-go">${tops || '<li class="muted">No certified go-shoot rows</li>'}</ol>
        <p><a href="${esc(section.field_desk_link || fieldDeskUrl(section.date))}" target="_blank" rel="noopener noreferrer">Open Field Desk Assignment Mode</a></p>
      </div>`;
  }

  function render(root, branch, payload, todayPack, tomorrowPack, quality, viralPack, viralReport, pinReport, shootPack) {
    const go = (payload.go_shoot_these || []).slice(0, 20);
    const months = payload.months || [];
    const removed = quality?.delta_vs_baseline?.events_removed;
    root.innerHTML = `
      <style>
        .cal-grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
        .md-packs{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));margin:12px 0}
        .md-card{border:1px solid rgba(148,163,184,.28);border-radius:12px;padding:12px;background:rgba(15,23,42,.35)}
        .md-chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
        .md-chip{display:inline-block;padding:6px 10px;border-radius:999px;border:1px solid rgba(96,165,250,.45);color:#e2e8f0;text-decoration:none;font-size:12px}
        .md-go{margin:8px 0 0;padding-left:18px;display:grid;gap:6px}
        .cal-table{min-width:0;width:100%}
        .cal-table th,.cal-table td{text-align:center;padding:6px 4px}
        .cal-day-btn{width:100%;min-height:52px;border:1px solid var(--line);border-radius:10px;background:#0f172a;color:inherit;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
        .cal-day.has-events .cal-day-btn{border-color:rgba(96,165,250,.55);background:rgba(96,165,250,.12)}
        .cal-day-btn:hover{outline:2px solid var(--accent)}
        .cal-date-num{font-weight:750}
        .cal-count{font-size:12px;color:var(--muted)}
        .cal-empty{opacity:.35}
      </style>
      <div class="notice violet">Photographer Money-Day Desk ${esc(VERSION)} — premium/operator. Read-only. Not a WordPress publish control.</div>
      <div class="notice ok">Loaded from <code>${esc(branch)}</code>. ${esc(payload.premium_label || "")} · ${fmtNum(payload.total_events)} money-day events / ${fmtNum(payload.days_with_coverage)} days${removed != null ? ` · removed ${fmtNum(removed)} vs #173 baseline` : ""}.</div>
      ${pinIntegrityHtml(pinReport)}
      <div class="md-packs">
        ${shootDayCardHtml(shootPack && shootPack.today, "SHOOT DAY CERTIFIED — TODAY")}
        ${shootDayCardHtml(shootPack && shootPack.tomorrow, "SHOOT DAY CERTIFIED — TOMORROW")}
      </div>
      <div class="md-packs">
        ${packCardHtml(todayPack, "TODAY — GO SHOOT")}
        ${packCardHtml(tomorrowPack, "TOMORROW — GO SHOOT")}
      </div>
      <div class="grid">
        <div class="stat"><div class="label">Money-day events (2 mo)</div><div class="value">${esc(fmtNum(payload.total_events))}</div></div>
        <div class="stat"><div class="label">Days with coverage</div><div class="value">${esc(fmtNum(payload.days_with_coverage))}</div></div>
        <div class="stat"><div class="label">map_ready</div><div class="value">${esc(fmtNum((payload.coordinate_status_counts || {}).map_ready))}</div></div>
        <div class="stat"><div class="label">list_only</div><div class="value">${esc(fmtNum((payload.coordinate_status_counts || {}).list_only))}</div></div>
      </div>
      ${returningHtml(viralPack, viralReport)}
      <div class="cal-grid">${months.map(monthHtml).join("")}</div>
      <h3>Day detail</h3>
      <div id="photographer-calendar-detail" class="muted">Click a day with events to see money-day coverage.</div>
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
    if (status) status.textContent = "Loading photographer money-day desk…";
    try {
      const [cal, today, tomorrow, quality, viral, viralReport, pin, shoot] = await Promise.all([
        fetchJson(CAL_PATH),
        fetchJson(TODAY_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(TOMORROW_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(QUALITY_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(VIRAL_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(VIRAL_REPORT_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(PIN_PATH).catch(() => ({ branch: "none", payload: null })),
        fetchJson(SHOOT_PATH).catch(() => ({ branch: "none", payload: null })),
      ]);
      render(
        root,
        cal.branch,
        cal.payload || {},
        today.payload,
        tomorrow.payload,
        quality.payload,
        viral.payload,
        viralReport.payload,
        pin.payload,
        shoot.payload
      );
      if (status) {
        status.textContent = `Money-day desk loaded from ${cal.branch} · ${fmtNum(cal.payload.total_events)} events · pin QA ${pin.payload && pin.payload.qa_pass ? "PASS" : "CHECK"}.`;
      }
    } catch (error) {
      root.innerHTML = `<div class="notice danger">Could not load photographer calendar.<br><br>${esc(error?.message || error)}</div>`;
      if (status) status.textContent = "Photographer calendar unavailable.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => load());
  window.NYCIF_PHOTOGRAPHER_CALENDAR = { version: VERSION, load };
})();

(function () {
  const OVERLAYS = {
    active5pm: {
      id: 'active5pm',
      checkboxId: 'approvedOverlayActive5pm',
      label: "🔥 It's 5PM Somewhere",
      shortLabel: "It's 5PM Somewhere",
      url: './data/nycif_active_nightlife_feed.json',
      icon: '🔥',
      className: 'nycif-approved-marker-active',
      zIndexOffset: 930,
      note: 'Public-record activity signal only. Not proof of crowd size, popularity, wrongdoing, violation, or unsafe conditions. Verify before publication or field assignment.'
    },
    legalCannabis: {
      id: 'legalCannabis',
      checkboxId: 'approvedOverlayLegalCannabis',
      label: '✅ Legal Cannabis Dispensaries',
      shortLabel: 'Legal Cannabis Dispensaries',
      url: './data/nycif_legal_cannabis_dispensaries.json',
      icon: '✅',
      className: 'nycif-approved-marker-cannabis',
      zIndexOffset: 920,
      note: 'Official NYS registered adult-use cannabis retail dealer record; confirm current OCM/license/open status before publication.'
    },
    correlation: {
      id: 'correlation',
      checkboxId: 'approvedOverlayCorrelation',
      label: '🔎 Smoke/Vape/Cannabis Correlation',
      shortLabel: 'Smoke/Vape/Cannabis Correlation',
      url: './data/nycif_smoke_vape_cannabis_correlation.json',
      icon: '🔎',
      className: 'nycif-approved-marker-correlation',
      zIndexOffset: 910,
      note: 'Complaint activity near regulated location. Not proof of causation, illegal activity, or wrongdoing.'
    }
  };

  const state = Object.fromEntries(Object.keys(OVERLAYS).map(key => [key, {
    loaded: false,
    rows: [],
    pins: [],
    layer: null
  }]));

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }

  function numberFrom(value) {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function fmt(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString() : '';
  }

  function isNYCoord(lat, lng) {
    return Number.isFinite(lat) && Number.isFinite(lng) && lat >= 40.4774 && lat <= 40.9176 && lng >= -74.2591 && lng <= -73.7004;
  }

  function setStatus(text) {
    const status = document.getElementById('status');
    if (status) status.textContent = text;
  }

  function topCounts(items) {
    if (!Array.isArray(items)) return '';
    return items.map(item => `${item.value || item.subtype || item.label || 'unknown'} (${item.count || 0})`).join(', ');
  }

  function installStyles() {
    if (document.getElementById('nycif-approved-overlays-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-approved-overlays-style';
    style.textContent = `
      .nycif-approved-overlays-block { display: grid; gap: 8px; }
      .nycif-approved-overlays-note { margin: 8px 0 0; font-size: 11px; line-height: 1.35; color: rgba(255,255,255,.72); }
      .nycif-approved-marker { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 999px; border: 2px solid rgba(255,255,255,.94); box-shadow: 0 9px 22px rgba(0,0,0,.34); color: #fff; font-size: 16px; }
      .nycif-approved-marker-active { background: #b91c1c; }
      .nycif-approved-marker-cannabis { background: #166534; }
      .nycif-approved-marker-correlation { background: #4338ca; }
      .nycif-approved-popup { min-width: 220px; max-width: 310px; padding: 12px 14px; border-radius: 16px; background: #fff; font: 500 12px/1.35 system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; color: #111827; box-shadow: 0 18px 45px rgba(15,23,42,.16); }
      .nycif-approved-popup .tag { display: inline-flex; border-radius: 999px; padding: 3px 7px; background: rgba(15,23,42,.09); color: #111827; font-size: 10px; font-weight: 900; text-transform: uppercase; letter-spacing: .04em; }
      .nycif-approved-popup h2 { margin: 7px 0 5px; color: #0f172a; font-size: 15px; line-height: 1.15; }
      .nycif-approved-popup p { margin: 4px 0; color: #111827; }
      .nycif-approved-popup strong { color: #0f172a; }
      .nycif-approved-popup .note { color: #4b5563; font-size: 11px; }
    `;
    document.head.appendChild(style);
  }

  function ensureControls() {
    const panel = document.getElementById('layersPanel');
    if (!panel || document.getElementById('approvedPublicOverlaysBlock')) return;

    const block = document.createElement('div');
    block.id = 'approvedPublicOverlaysBlock';
    block.className = 'nycif-approved-overlays-block';
    block.innerHTML = `
      <hr>
      <p class="panel-label">Public data layers</p>
      <label class="check"><input type="checkbox" id="${OVERLAYS.active5pm.checkboxId}"> <span>${OVERLAYS.active5pm.label}</span></label>
      <label class="check"><input type="checkbox" id="${OVERLAYS.legalCannabis.checkboxId}"> <span>${OVERLAYS.legalCannabis.label}</span></label>
      <label class="check"><input type="checkbox" id="${OVERLAYS.correlation.checkboxId}"> <span>${OVERLAYS.correlation.label}</span></label>
      <p class="nycif-approved-overlays-note">Complaint and correlation layers are public-record signals, not proof of wrongdoing, causation, safety conditions, or verified crowd size.</p>
    `;
    panel.appendChild(block);

    Object.entries(OVERLAYS).forEach(([key, config]) => {
      const checkbox = document.getElementById(config.checkboxId);
      if (!checkbox) return;
      checkbox.addEventListener('change', () => toggleOverlay(key, checkbox.checked));
    });
  }

  function normalizePin(row, index, key) {
    const lat = Number.parseFloat(row.lat);
    const lng = Number.parseFloat(row.lng);
    if (!isNYCoord(lat, lng)) return null;

    if (key === 'active5pm') {
      return {
        id: row.id || `active5pm-${index}`,
        title: row.title || 'Active 5PM feed candidate',
        label: row.subtype_label || row.subtype || 'Public activity signal',
        address: row.address || '',
        borough: row.borough || '',
        trendTier: row.trend_tier || '',
        trendScore: row.trend_score ?? '',
        feedBucket: row.feed_bucket || '',
        lastComplaintDate: row.last_complaint_date || '',
        complaints30d100ft: row.complaints_30d_100ft ?? '',
        complaints90d100ft: row.complaints_90d_100ft ?? '',
        complaints365d100ft: row.complaints_365d_100ft ?? '',
        lat,
        lng
      };
    }

    if (key === 'legalCannabis') {
      return {
        id: row.id || row.raw_source_id || row.license_number || `legal-cannabis-${index}`,
        title: row.title || row.dba_name || row.legal_name || 'Registered cannabis retail dealer',
        label: row.license_type || 'Registered adult-use cannabis retail dealer',
        address: row.address || '',
        borough: row.borough || '',
        licenseStatus: row.license_status || 'Registered',
        licenseNumber: row.license_number || row.ocm_license_number || row.raw_source_id || '',
        dataNote: row.data_note || OVERLAYS.legalCannabis.note,
        lat,
        lng
      };
    }

    return {
      id: row.id || row.raw_source_id || `correlation-${index}`,
      title: row.title || 'Smoke/vape/cannabis correlation candidate',
      label: row.license || row.license_type || row.location_kind || 'Regulated-location signal',
      address: row.address || '',
      borough: row.borough || '',
      locationKind: row.location_kind || '',
      signalScore: row.signal_score ?? '',
      signalTier: row.signal_tier || '',
      lastComplaintDate: row.last_complaint_date || '',
      complaints365d100ft: row.complaints_365d_100ft ?? '',
      complaints365d250ft: row.complaints_365d_250ft ?? '',
      complaints365d500ft: row.complaints_365d_500ft ?? '',
      topComplaintSubtypes: topCounts(row.top_complaint_subtypes),
      topComplaintDescriptors: topCounts(row.top_complaint_descriptors),
      lat,
      lng
    };
  }

  function popupHtml(pin, key) {
    const config = OVERLAYS[key];
    if (key === 'active5pm') {
      return `<article class="nycif-approved-popup"><div class="tag">${esc(config.shortLabel)}</div><h2>${esc(pin.title)}</h2>${pin.label ? `<p><strong>${esc(pin.label)}</strong></p>` : ''}${pin.address ? `<p>${esc(pin.address)}</p>` : ''}${pin.borough ? `<p>${esc(pin.borough)}</p>` : ''}${pin.feedBucket ? `<p><strong>Signal bucket:</strong> ${esc(pin.feedBucket)}</p>` : ''}${pin.trendTier ? `<p><strong>Signal tier:</strong> ${esc(pin.trendTier)}</p>` : ''}${pin.trendScore !== '' ? `<p><strong>Signal score:</strong> ${esc(fmt(pin.trendScore))}</p>` : ''}${pin.lastComplaintDate ? `<p><strong>Last complaint date:</strong> ${esc(pin.lastComplaintDate)}</p>` : ''}<p><strong>Nearby complaints:</strong> 30d ${esc(fmt(pin.complaints30d100ft))} / 90d ${esc(fmt(pin.complaints90d100ft))} / 365d ${esc(fmt(pin.complaints365d100ft))}</p><p class="note">${esc(config.note)}</p></article>`;
    }

    if (key === 'legalCannabis') {
      return `<article class="nycif-approved-popup"><div class="tag">${esc(config.shortLabel)}</div><h2>${esc(pin.title)}</h2>${pin.label ? `<p><strong>${esc(pin.label)}</strong></p>` : ''}${pin.licenseStatus ? `<p><strong>Status:</strong> ${esc(pin.licenseStatus)}</p>` : ''}${pin.licenseNumber ? `<p><strong>License/record:</strong> ${esc(pin.licenseNumber)}</p>` : ''}${pin.address ? `<p>${esc(pin.address)}</p>` : ''}${pin.borough ? `<p>${esc(pin.borough)}</p>` : ''}<p class="note">${esc(pin.dataNote || config.note)}</p></article>`;
    }

    return `<article class="nycif-approved-popup"><div class="tag">${esc(config.shortLabel)}</div><h2>${esc(pin.title)}</h2>${pin.label ? `<p><strong>${esc(pin.label)}</strong></p>` : ''}${pin.locationKind ? `<p><strong>Location kind:</strong> ${esc(pin.locationKind)}</p>` : ''}${pin.address ? `<p>${esc(pin.address)}</p>` : ''}${pin.borough ? `<p>${esc(pin.borough)}</p>` : ''}${pin.signalScore !== '' ? `<p><strong>Signal score:</strong> ${esc(fmt(pin.signalScore))}</p>` : ''}${pin.signalTier ? `<p><strong>Signal tier:</strong> ${esc(pin.signalTier)}</p>` : ''}${pin.lastComplaintDate ? `<p><strong>Last complaint date:</strong> ${esc(pin.lastComplaintDate)}</p>` : ''}<p><strong>Complaints 365d:</strong> 100ft ${esc(fmt(pin.complaints365d100ft))} / 250ft ${esc(fmt(pin.complaints365d250ft))} / 500ft ${esc(fmt(pin.complaints365d500ft))}</p>${pin.topComplaintSubtypes ? `<p><strong>Top subtypes:</strong> ${esc(pin.topComplaintSubtypes)}</p>` : ''}${pin.topComplaintDescriptors ? `<p><strong>Top descriptors:</strong> ${esc(pin.topComplaintDescriptors)}</p>` : ''}<p class="note">${esc(config.note)}</p></article>`;
  }

  function markerFor(pin, key) {
    const config = OVERLAYS[key];
    const icon = window.L.divIcon({
      className: `${config.className}-shell`,
      html: `<div class="nycif-approved-marker ${config.className}">${config.icon}</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -18]
    });
    return window.L.marker([pin.lat, pin.lng], {
      icon,
      title: pin.title,
      zIndexOffset: config.zIndexOffset
    }).bindPopup(popupHtml(pin, key), { maxWidth: 330, minWidth: 240 });
  }

  async function loadOverlay(key) {
    const config = OVERLAYS[key];
    const record = state[key];
    if (record.loaded) return record;

    setStatus(`Loading ${config.shortLabel}…`);
    const response = await fetch(`${config.url}?cache=${Date.now()}`, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`${config.shortLabel} HTTP ${response.status}`);
    const rows = await response.json();
    record.rows = Array.isArray(rows) ? rows : [];
    record.pins = record.rows.map((row, index) => normalizePin(row, index, key)).filter(Boolean);
    record.loaded = true;
    return record;
  }

  async function toggleOverlay(key, enabled) {
    const map = window.NYCIF_MAIN_MAP;
    const config = OVERLAYS[key];
    const record = state[key];
    if (!map || !window.L) {
      setStatus('Map is still loading. Try again in a moment.');
      return;
    }

    if (!enabled) {
      if (record.layer) map.removeLayer(record.layer);
      setStatus(`${config.shortLabel} hidden.`);
      return;
    }

    try {
      await loadOverlay(key);
      if (!record.layer) {
        record.layer = window.L.layerGroup(record.pins.map(pin => markerFor(pin, key)));
      }
      record.layer.addTo(map);
      setStatus(`${config.shortLabel} loaded · ${record.pins.length.toLocaleString()} marker${record.pins.length === 1 ? '' : 's'} · public-record layer`);
    } catch (error) {
      console.error(error);
      const checkbox = document.getElementById(config.checkboxId);
      if (checkbox) checkbox.checked = false;
      setStatus(`${config.shortLabel} failed: ${error.message}`);
    }
  }

  function boot() {
    if (!window.L) return;
    installStyles();
    ensureControls();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

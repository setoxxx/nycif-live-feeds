(() => {
  const SCHEMA_VERSION = '1.0';
  const DEFAULT_TIMEZONE = 'America/New_York';
  const NYC = { minLat: 40.4774, maxLat: 40.9176, minLng: -74.2591, maxLng: -73.7004 };
  const CATEGORY_ALIASES = {
    sports: 'sports',
    fitness: 'fitness',
    'fitness and wellness': 'fitness',
    parks: 'parks',
    'parks and recreation': 'parks',
    'parks & recreation': 'parks',
    arts: 'arts',
    'arts and culture': 'arts',
    market: 'market',
    'markets and fairs': 'market',
    civic: 'civic',
    'civic and neighborhood': 'civic',
    government: 'government',
    'government and hearings': 'government',
    education: 'education',
    'education and training': 'education',
    family: 'family',
    'kids and family': 'family',
    services: 'services',
    'benefits and services': 'services',
    environment: 'environment',
    volunteer: 'volunteer',
    jobs: 'jobs',
    'jobs and careers': 'jobs',
    housing: 'housing',
    'housing and tenant assistance': 'housing',
    'housing and tenant help': 'housing',
    general: 'general'
  };

  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim();

  function boroughLabel(value) {
    const raw = Array.isArray(value) ? value[0] : value;
    const key = norm(raw);
    const map = {
      mn: 'Manhattan', manhattan: 'Manhattan',
      bk: 'Brooklyn', brooklyn: 'Brooklyn',
      qn: 'Queens', q: 'Queens', queens: 'Queens',
      bx: 'Bronx', bronx: 'Bronx',
      si: 'Staten Island', 'staten island': 'Staten Island'
    };
    if (map[key]) return map[key];
    const text = String(raw ?? '').trim();
    return text || null;
  }

  function validNycCoords(lat, lng) {
    const latN = Number.parseFloat(lat);
    const lngN = Number.parseFloat(lng);
    const ok = Number.isFinite(latN) && Number.isFinite(lngN)
      && latN >= NYC.minLat && latN <= NYC.maxLat
      && lngN >= NYC.minLng && lngN <= NYC.maxLng;
    return ok ? { lat: latN, lng: lngN, valid: true } : { lat: null, lng: null, valid: false };
  }

  function inferCategory(row, preferDirect) {
    const direct = CATEGORY_ALIASES[norm(row.category)];
    if (preferDirect && direct) return direct;
    const categories = Array.isArray(row.categories) ? row.categories.join(' ') : (row.categories || '');
    const text = norm([row.category, categories, row.title, row.name, row.event_type, row.type, row.event_agency, row.location, row.display_location].filter(Boolean).join(' '));
    if (/job fair|career fair|employment|workforce|hiring/.test(text)) return 'jobs';
    if (/tenant|housing|property owner|landlord|homeowner|rent assistance|housing ambassador/.test(text)) return 'housing';
    if (/hearing|public meeting|community board|city government|government office|council meeting/.test(text)) return 'government';
    if (/benefit|resource fair|outreach|clinic|health screening|social service|food assistance|legal help/.test(text)) return 'services';
    if (/education|training|class|workshop|lecture|literacy|school program/.test(text)) return 'education';
    if (/kids and family|kids|children|family|youth program|storytime/.test(text)) return 'family';
    if (/volunteer|it'?s my park|stewardship|service project/.test(text)) return 'volunteer';
    if (/environment|ecology|climate|cleanup|compost|recycling|conservation|gardening|nature walk/.test(text)) return 'environment';
    if (/yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|shape up nyc|lap swim/.test(text)) return 'fitness';
    if (/athletic|softball|baseball|basketball|soccer|football|hockey|tennis|lacrosse|cricket|volleyball|kickball|rugby|marathon|5k|race|sport/.test(text)) return 'sports';
    if (/cultural|music|concert|arts?|dance|theater|theatre|film|performance|exhibit|museum|summerstage/.test(text)) return 'arts';
    if (/market|greenmarket|vendor|fair|feast|food festival|pop[- ]?up/.test(text)) return 'market';
    if (/parade|march|rally|vigil|ceremony|memorial|street and neighborhood|block party|open street|civic|community event/.test(text)) return 'civic';
    if (/parks? & recreation|park|playground|pool|recreation|garden|beach/.test(text)) return 'parks';
    return direct || 'general';
  }

  function isSchemaEvent(row) {
    return row
      && typeof row === 'object'
      && Object.prototype.hasOwnProperty.call(row, 'latitude')
      && Object.prototype.hasOwnProperty.call(row, 'longitude')
      && row.source
      && typeof row.source === 'object'
      && Object.prototype.hasOwnProperty.call(row.source, 'dataset');
  }

  function projectEvent(row, index, dataLayer) {
    if (isSchemaEvent(row) && row.timezone && row.category) {
      const coords = validNycCoords(row.latitude, row.longitude);
      const nycif = { ...(row.nycif || {}) };
      if (!nycif.data_layer) nycif.data_layer = dataLayer;
      if (!nycif.coordinate_status) nycif.coordinate_status = coords.valid ? 'map_ready' : 'list_only';
      if (dataLayer === 'review_supplemental') {
        nycif.production_feed = false;
        nycif.promotion_allowed = false;
        nycif.manual_review_status = nycif.manual_review_status || 'pending';
      }
      const idBase = String(row.id || `${dataLayer}:${row.source?.dataset || 'unknown'}:${row.source?.source_event_id || index}`);
      return {
        id: idBase,
        title: String(row.title || 'Untitled event'),
        category: CATEGORY_ALIASES[norm(row.category)] || inferCategory(row, dataLayer === 'approved_staged'),
        start_date_time: row.start_date_time ?? null,
        end_date_time: row.end_date_time ?? null,
        timezone: String(row.timezone || DEFAULT_TIMEZONE),
        borough: boroughLabel(row.borough),
        location: row.location == null || row.location === '' ? null : String(row.location),
        latitude: coords.lat,
        longitude: coords.lng,
        significance: row.significance ?? null,
        source: {
          dataset: row.source.dataset == null ? null : String(row.source.dataset),
          source_event_id: row.source.source_event_id == null ? null : String(row.source.source_event_id)
        },
        nycif
      };
    }

    const preferDirect = dataLayer === 'approved_staged';
    let coords;
    if (dataLayer === 'review_supplemental') {
      coords = validNycCoords(
        row.lat ?? row.latitude ?? row.proposed_lat,
        row.lng ?? row.longitude ?? row.proposed_lng
      );
    } else {
      coords = validNycCoords(row.latitude ?? row.lat, row.longitude ?? row.lng);
    }

    const nested = row.source && typeof row.source === 'object' ? row.source : null;
    const dataset = nested?.dataset ?? row.source_dataset ?? null;
    const sourceEventId = nested?.source_event_id ?? row.source_event_id ?? null;
    let base = row.id ? String(row.id) : `${dataLayer === 'review_supplemental' ? 'review_supplemental:' : ''}${dataset || 'unknown'}:${sourceEventId || index}`;
    if (dataLayer === 'review_supplemental' && row.id && !String(row.id).startsWith('review_supplemental:')) {
      base = `review_supplemental:${row.id}`;
    }
    const day = (() => {
      const direct = String(row.date || '').slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct;
      const start = String(row.start_date_time || row.start || '');
      const m = start.match(/^(\d{4}-\d{2}-\d{2})/);
      return m ? m[1] : '';
    })();
    const id = day ? `${base}@${day}` : base;

    const nycif = dataLayer === 'review_supplemental'
      ? {
          data_layer: dataLayer,
          coordinate_status: coords.valid ? 'map_ready' : 'list_only',
          production_feed: false,
          promotion_allowed: false,
          manual_review_status: row.manual_review_status || 'pending',
          location_cache_modified: !!row.location_cache_modified,
          public_map_modified: !!row.public_map_modified,
          staged_feed_modified: !!row.staged_feed_modified,
          event_date: day || null
        }
      : {
          data_layer: dataLayer,
          coordinate_status: coords.valid ? 'map_ready' : 'list_only',
          production_feed: true,
          promotion_allowed: null,
          manual_review_status: null,
          location_cache_modified: false,
          public_map_modified: false,
          staged_feed_modified: false,
          event_date: day || null
        };

    return {
      id: String(id),
      title: String(row.title || row.name || row.search_label || 'Untitled event'),
      category: inferCategory(row, preferDirect),
      start_date_time: row.start_date_time || row.start || null,
      end_date_time: row.end_date_time || row.end || null,
      timezone: String(row.timezone || DEFAULT_TIMEZONE),
      borough: boroughLabel(row.borough || row.event_borough),
      location: String(row.location || row.display_location || row.address || '') || null,
      latitude: coords.lat,
      longitude: coords.lng,
      significance: row.significance ?? null,
      source: {
        dataset: dataset == null ? null : String(dataset),
        source_event_id: sourceEventId == null ? null : String(sourceEventId)
      },
      nycif
    };
  }

  function projectEnvelope(payload, dataLayer, generatedAtUtc) {
    const rows = Array.isArray(payload) ? payload : (payload?.events || []);
    const events = rows.map((row, index) => projectEvent(row, index, dataLayer));
    return {
      schema_version: SCHEMA_VERSION,
      generated_at_utc: generatedAtUtc || payload?.generated_at_utc || new Date().toISOString(),
      total: events.length,
      next_cursor: payload && Object.prototype.hasOwnProperty.call(payload, 'next_cursor') ? payload.next_cursor : null,
      events
    };
  }

  function extractEvents(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.events)) return payload.events;
    return [];
  }

  window.NYCIF_EVENT_FEED_SCHEMA_V1 = {
    SCHEMA_VERSION,
    DEFAULT_TIMEZONE,
    projectEvent,
    projectEnvelope,
    extractEvents,
    isSchemaEvent,
    validNycCoords,
    boroughLabel
  };
})();

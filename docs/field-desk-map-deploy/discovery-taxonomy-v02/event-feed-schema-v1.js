(() => {
  const SCHEMA_VERSION = '1.0';
  const DEFAULT_TIMEZONE = 'America/New_York';
  const NYC = { minLat: 40.4774, maxLat: 40.9176, minLng: -74.2591, maxLng: -73.7004 };
  const CATEGORY_ALIASES = {
    sports: 'sports', fitness: 'fitness', 'fitness and wellness': 'fitness',
    parks: 'parks', 'parks and recreation': 'parks', 'parks & recreation': 'parks',
    'parks / outdoors': 'parks', 'parks / recreation': 'parks',
    arts: 'arts', 'arts and culture': 'arts', 'arts / performance': 'arts',
    market: 'market', 'markets and fairs': 'market', 'street fairs / markets': 'market',
    parade: 'civic', civic: 'civic', 'civic and neighborhood': 'civic', 'parades / civic': 'civic',
    government: 'government', 'government and hearings': 'government', 'government / meetings': 'government',
    education: 'education', 'education and training': 'education', 'classes / workshops': 'education',
    family: 'family', 'kids and family': 'family', 'kids / family': 'family',
    services: 'services', 'benefits and services': 'services', 'health / benefits': 'services',
    environment: 'environment', 'environment / nature': 'environment',
    volunteer: 'volunteer', 'volunteer opportunities': 'volunteer',
    jobs: 'jobs', 'jobs and careers': 'jobs', 'jobs / career': 'jobs',
    housing: 'housing', 'housing and tenant assistance': 'housing',
    'housing and tenant help': 'housing', 'housing / tenant help': 'housing',
    tours: 'tours', 'tours / history': 'tours',
    general: 'general'
  };
  const EVENT_TYPE_MAP = {
    parade: 'civic',
    'athletic race / tour': 'sports',
    'farmers market': 'market',
    'block party': 'civic',
    'street event': 'civic',
    'religious event': 'civic',
    'sport - youth': 'sports',
    'sport - adult': 'sports'
  };
  const KEYWORD_RULES = [
    ['jobs', /job fair|career fair|employment|workforce|hiring/],
    ['housing', /\btenant\b|housing ambassador|rent assistance|landlord|homeowner|property owner clinic/],
    ['government', /hearing|public meeting|community board|city government|government office|council meeting/],
    ['tours', /\btour\b|historic walk|heritage walk|walking tour/],
    ['sports', /sport - youth|sport - adult|athletic race|triathlon|duathlon|marathon|\b5k\b|\b10k\b|criterium|world cup|fifa|fan zone|softball|baseball|basketball|soccer|football|hockey|tennis|volleyball/],
    ['fitness', /yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|shape up nyc|lap swim/],
    ['civic', /\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b|\bprocession\b|baraat|street and neighborhood|block party|open street|\bcivic\b|unity walk/],
    ['services', /benefit|resource fair|outreach|clinic|health screening|social service|food assistance|legal help/],
    ['education', /education|training|workshop|lecture|literacy|school program|\bclass\b/],
    ['family', /kids and family|\bkids\b|children|youth program|storytime/],
    ['volunteer', /volunteer|stewardship|service project|my park/],
    ['environment', /environment|ecology|climate|cleanup|compost|recycling|conservation|gardening|nature walk/],
    ['arts', /cultural|music|concert|\barts?\b|dance|theater|theatre|film|performance|exhibit|museum|summerstage|feast/],
    ['market', /market|greenmarket|farmers market|vendor|fair|food festival|pop[- ]?up|merchandise/],
    ['parks', /parks? & recreation|\bpark\b|playground|pool|recreation|garden|beach/]
  ];

  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g, ' ').trim();
  const hasOwn = (obj, key) => Object.hasOwn(obj, key);

  function normalizeInterests(category, rawInterests) {
    const list = Array.isArray(rawInterests)
      ? rawInterests.map(v => CATEGORY_ALIASES[norm(v)] || norm(v)).filter(Boolean)
      : [];
    const cat = CATEGORY_ALIASES[norm(category)] || category || 'general';
    if (!list.length) {
      return [cat];
    }
    if (!list.includes(cat)) {
      list.unshift(cat);
    }
    return [...new Set(list)];
  }

  function normalizeTags(rawTags) {
    if (!Array.isArray(rawTags)) {
      return [];
    }
    return rawTags.map(v => norm(v)).filter(Boolean);
  }

  function normalizeEventRole(value) {
    const role = norm(value);
    const allowed = new Set([
      'public_event',
      'supporting_permit',
      'street_closure',
      'transportation_operation',
      'maintenance_or_closure',
      'private_or_reserved_activity'
    ]);
    return allowed.has(role) ? role : 'public_event';
  }

  function normalizeSignificance(value, nycif) {
    const sig = norm(value);
    if (sig === 'major' || sig === 'featured' || sig === 'standard') {
      return sig;
    }
    if (nycif?.is_major) {
      return 'major';
    }
    return 'standard';
  }

  function normalizeDisplayDisposition(row, nycif, coords, eventRole) {
    const direct = nycif?.display_disposition || row.display_disposition;
    const allowed = new Set([
      'standalone_public_event',
      'grouped_under_public_event',
      'list_only',
      'maintenance_or_closure',
      'private_or_reserved_activity',
      'invalid_rejected'
    ]);
    if (allowed.has(direct)) {
      return direct;
    }
    if (!coords.valid || nycif?.coordinate_status === 'list_only') {
      return 'list_only';
    }
    if (eventRole === 'maintenance_or_closure') {
      return 'maintenance_or_closure';
    }
    if (eventRole === 'private_or_reserved_activity') {
      return 'private_or_reserved_activity';
    }
    if (row.parent_event_id) {
      return 'grouped_under_public_event';
    }
    return 'standalone_public_event';
  }

  function boroughLabel(value) {
    const raw = Array.isArray(value) ? value[0] : value;
    const key = norm(raw);
    const map = {
      mn: 'Manhattan', manhattan: 'Manhattan', bk: 'Brooklyn', brooklyn: 'Brooklyn',
      qn: 'Queens', q: 'Queens', queens: 'Queens', bx: 'Bronx', bronx: 'Bronx',
      si: 'Staten Island', 'staten island': 'Staten Island'
    };
    if (map[key]) return map[key];
    const text = String(raw ?? '').trim();
    return text || null;
  }

  function validNycCoords(lat, lng) {
    const latN = Number.parseFloat(lat);
    const lngN = Number.parseFloat(lng);
    if (!Number.isFinite(latN) || !Number.isFinite(lngN)) return { lat: null, lng: null, valid: false };
    if (Math.abs(latN) < 1e-12 && Math.abs(lngN) < 1e-12) return { lat: null, lng: null, valid: false };
    const ok = latN >= NYC.minLat && latN <= NYC.maxLat && lngN >= NYC.minLng && lngN <= NYC.maxLng;
    return ok ? { lat: latN, lng: lngN, valid: true } : { lat: null, lng: null, valid: false };
  }

  function preserveDate(row) {
    const direct = String(row.date || '').slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct;
    const start = String(row.start_date_time || row.start || '');
    const match = /^(\d{4}-\d{2}-\d{2})/.exec(start);
    return match ? match[1] : '';
  }

  function inferCategory(row, preferDirect) {
    const direct = CATEGORY_ALIASES[norm(row.category)];
    if (preferDirect && direct && direct !== 'general') return direct;
    const eventType = EVENT_TYPE_MAP[norm(row.event_type || row.type)];
    if (eventType) return eventType;
    const categories = Array.isArray(row.categories) ? row.categories.join(' ') : (row.categories || '');
    const text = norm([row.category, categories, row.title, row.name, row.event_type, row.type, row.event_agency, row.street_closure_type, row.location, row.display_location].filter(Boolean).join(' '));
    for (const [slug, pattern] of KEYWORD_RULES) {
      if (pattern.test(text)) return slug;
    }
    if (direct && direct !== 'general') return direct;
    return 'general';
  }

  function isSchemaEvent(row) {
    return !!(row && typeof row === 'object' && hasOwn(row, 'latitude') && hasOwn(row, 'longitude') && row.source && typeof row.source === 'object' && hasOwn(row.source, 'dataset'));
  }

  function coordKeyLists(dataLayer) {
    if (dataLayer === 'review_supplemental') {
      return {
        latKeys: ['latitude', 'lat', 'proposed_lat'],
        lngKeys: ['longitude', 'lng', 'proposed_lng']
      };
    }
    return { latKeys: ['latitude', 'lat'], lngKeys: ['longitude', 'lng'] };
  }

  function firstCoordValue(row, keys) {
    for (const key of keys) {
      if (row[key] != null) {
        return row[key];
      }
    }
    return null;
  }

  function resolveSourceFields(row) {
    const nested = row.source && typeof row.source === 'object' ? row.source : null;
    return {
      dataset: nested?.dataset ?? row.source_dataset ?? null,
      sourceEventId: nested?.source_event_id ?? row.source_event_id ?? null
    };
  }

  function buildLegacyBaseId(row, index, dataLayer, dataset, sourceEventId) {
    let base = row.id ? String(row.id) : `${dataset || 'unknown'}:${sourceEventId || index}`;
    if (dataLayer === 'review_supplemental' && !base.startsWith('review_supplemental:')) {
      base = `review_supplemental:${base}`;
    }
    return base;
  }

  function buildLegacySourceObject(dataset, sourceEventId) {
    return {
      dataset: dataset == null ? null : String(dataset),
      source_event_id: sourceEventId == null ? null : String(sourceEventId)
    };
  }

  function buildLegacyNycifBlock(row, dataLayer, day, coords, category, eventRole, significance, displayDisposition) {
    const review = dataLayer === 'review_supplemental';
    return {
      data_layer: dataLayer,
      coordinate_status: coords.valid ? 'map_ready' : 'list_only',
      display_disposition: displayDisposition,
      production_feed: !review,
      promotion_allowed: review ? false : null,
      manual_review_status: review ? (row.manual_review_status || 'pending') : null,
      event_date: day || null,
      event_type: row.event_type || row.type || null,
      event_agency: row.event_agency || null,
      is_major: significance === 'major'
    };
  }

  function projectLegacy(row, index, dataLayer) {
    const preferDirect = dataLayer === 'approved_staged';
    const { latKeys, lngKeys } = coordKeyLists(dataLayer);
    const coords = validNycCoords(firstCoordValue(row, latKeys), firstCoordValue(row, lngKeys));
    const { dataset, sourceEventId } = resolveSourceFields(row);
    const base = buildLegacyBaseId(row, index, dataLayer, dataset, sourceEventId);
    const day = preserveDate(row);
    const id = day ? `${base}@${day}` : base;
    const category = inferCategory(row, preferDirect);
    const eventRole = normalizeEventRole(row.event_role);
    const significance = normalizeSignificance(row.significance, row.nycif);
    const parentEventId = row.parent_event_id == null ? null : String(row.parent_event_id);
    const eventGroupId = row.event_group_id == null ? id : String(row.event_group_id);
    const interests = normalizeInterests(category, row.interests);
    const tags = normalizeTags(row.tags);
    const nycifDraft = row.nycif || {};
    const displayDisposition = normalizeDisplayDisposition(row, nycifDraft, coords, eventRole);
    return {
      id: String(id),
      event_group_id: eventGroupId,
      parent_event_id: parentEventId,
      title: String(row.title || row.name || row.search_label || 'Untitled event'),
      category,
      interests,
      tags,
      event_role: eventRole,
      significance,
      start_date_time: row.start_date_time || row.start || null,
      end_date_time: row.end_date_time || row.end || null,
      timezone: String(row.timezone || DEFAULT_TIMEZONE),
      borough: boroughLabel(row.borough || row.event_borough),
      location: String(row.location || row.display_location || row.address || '') || null,
      latitude: coords.lat,
      longitude: coords.lng,
      source: buildLegacySourceObject(dataset, sourceEventId),
      nycif: buildLegacyNycifBlock(row, dataLayer, day, coords, category, eventRole, significance, displayDisposition)
    };
  }

  function projectSchemaRow(row, index, dataLayer) {
    const coords = validNycCoords(row.latitude, row.longitude);
    const category = CATEGORY_ALIASES[norm(row.category)] || inferCategory(row, dataLayer === 'approved_staged');
    const eventRole = normalizeEventRole(row.event_role);
    const significance = normalizeSignificance(row.significance, row.nycif);
    const interests = normalizeInterests(category, row.interests);
    const tags = normalizeTags(row.tags);
    const parentEventId = row.parent_event_id == null ? null : String(row.parent_event_id);
    const eventGroupId = row.event_group_id == null
      ? String(row.id || `${dataLayer}:${row.source?.dataset || 'unknown'}:${row.source?.source_event_id || index}`)
      : String(row.event_group_id);
    const nycif = { ...(row.nycif || {}) };
    if (!nycif.data_layer) nycif.data_layer = dataLayer;
    if (!nycif.coordinate_status) nycif.coordinate_status = coords.valid ? 'map_ready' : 'list_only';
    nycif.display_disposition = normalizeDisplayDisposition(row, nycif, coords, eventRole);
    if (dataLayer === 'review_supplemental') {
      nycif.production_feed = false;
      nycif.promotion_allowed = false;
      nycif.manual_review_status = nycif.manual_review_status || 'pending';
    }
    if (significance === 'major') {
      nycif.is_major = true;
    }
    return {
      id: String(row.id || `${dataLayer}:${row.source?.dataset || 'unknown'}:${row.source?.source_event_id || index}`),
      event_group_id: eventGroupId,
      parent_event_id: parentEventId,
      title: String(row.title || 'Untitled event'),
      category,
      interests,
      tags,
      event_role: eventRole,
      significance,
      start_date_time: row.start_date_time ?? null,
      end_date_time: row.end_date_time ?? null,
      timezone: String(row.timezone || DEFAULT_TIMEZONE),
      borough: boroughLabel(row.borough),
      location: row.location == null || row.location === '' ? null : String(row.location),
      latitude: coords.lat,
      longitude: coords.lng,
      source: {
        dataset: row.source.dataset == null ? null : String(row.source.dataset),
        source_event_id: row.source.source_event_id == null ? null : String(row.source.source_event_id)
      },
      nycif
    };
  }

  function projectEvent(row, index, dataLayer) {
    if (isSchemaEvent(row) && row.timezone && row.category) {
      return projectSchemaRow(row, index, dataLayer);
    }
    return projectLegacy(row, index, dataLayer);
  }

  function projectEnvelope(payload, dataLayer, generatedAtUtc) {
    const rows = Array.isArray(payload) ? payload : (payload?.events || []);
    const events = rows.map((row, index) => projectEvent(row, index, dataLayer));
    return {
      schema_version: SCHEMA_VERSION,
      generated_at_utc: generatedAtUtc || payload?.generated_at_utc || new Date().toISOString(),
      total: hasOwn(payload || {}, 'total') ? Number(payload.total) || events.length : events.length,
      next_cursor: hasOwn(payload || {}, 'next_cursor') ? payload.next_cursor : null,
      events
    };
  }

  function safeExternalUrl(value) {
    if (value == null) return null;
    const text = String(value).trim();
    if (!text) return null;
    if (!/^https?:\/\//i.test(text)) return null;
    let url;
    try {
      url = new URL(text);
    } catch {
      return null;
    }
    if (url.protocol === 'javascript:' || url.protocol === 'data:') return null;
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
    return url.href;
  }

  window.NYCIF_EVENT_FEED_SCHEMA_V1 = {
    SCHEMA_VERSION,
    DEFAULT_TIMEZONE,
    projectEvent,
    projectEnvelope,
    extractEvents: payload => (Array.isArray(payload) ? payload : (payload?.events || [])),
    isSchemaEvent,
    validNycCoords,
    boroughLabel,
    safeExternalUrl,
    inferCategory,
    normalizeInterests
  };
})();

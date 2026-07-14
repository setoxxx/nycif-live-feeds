/**
 * Event significance v01 — deterministic, evidence-based Gold/Silver/Bronze.
 * Cannot be purchased. Sponsorship/payment fields are ignored.
 */
export const SIGNIFICANCE_VERSION = 'event-significance-v01';
export const SIGNIFICANCE_INTEGRITY =
  'Event significance is evidence-based and cannot be purchased.';

const CANONICAL_TIERS = new Set(['Gold', 'Silver', 'Bronze']);

const EXCLUDE_TITLE =
  /^(closed|closure|maintenance|facility closed|field closed|cancelled|canceled)$/i;
const EXCLUDE_TEXT =
  /\b(maintenance day|routine practice|miscellaneous permit|generic field reservation|closed facility)\b/i;

const GOLD_TITLE =
  /\b(world cup|fifa|marathon|pride parade|thanksgiving day parade|new year'?s eve|nye ball|macys|macy's|presidential|inauguration|major festival)\b/i;
const SILVER_TITLE =
  /\b(parade|festival|street fair|block party|concert|criterium|fan zone|race|tour|carnival|film festival)\b/i;
const BRONZE_TITLE =
  /\b(market|farmers market|plaza partner|open street|street event|production event|health fair|open culture)\b/i;

function num(value) {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

function textBlob(event) {
  return [
    event.title,
    event.event_type,
    event.type,
    event.category?.key || event.category,
    event.major_reason,
    event.crowd_level,
    event.lane,
    event.nypd_notice
  ]
    .map(v => String(v || ''))
    .join(' ')
    .toLowerCase();
}

function durationHours(event) {
  const start = event.start_date_time || event.start;
  const end = event.end_date_time || event.end;
  if (!start || !end) return 0;
  const a = Date.parse(start);
  const b = Date.parse(end);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return 0;
  return (b - a) / 3600000;
}

function isExcludedGeneric(event) {
  const title = String(event.title || '').trim();
  if (EXCLUDE_TITLE.test(title)) return true;
  const blob = textBlob(event);
  if (EXCLUDE_TEXT.test(blob)) return true;
  const et = String(event.event_type || event.type || '').toLowerCase();
  if (/^sport - (youth|adult)$/.test(et) && !event.street_closure_type) {
    // Ordinary league/reservation rows stay untiered unless other evidence appears later.
    return !event.photo_pick && !event.photoPick && !event.field_default && num(event.expected_crowd_score) < 200;
  }
  return false;
}

/**
 * @param {object} event
 * @returns {{ tier: 'Gold'|'Silver'|'Bronze'|null, score: number, source: string, reasons: string[] }}
 */
export function classifyEventSignificance(event = {}) {
  const reasons = [];
  const rawTier = [
    event.significance_tier,
    event.significanceTier,
    event.tier
  ]
    .map(v => (v == null ? '' : String(v).trim()))
    .filter(Boolean);

  for (const candidate of rawTier) {
    const normalized =
      candidate.charAt(0).toUpperCase() + candidate.slice(1).toLowerCase();
    if (CANONICAL_TIERS.has(normalized)) {
      return {
        tier: normalized,
        score: normalized === 'Gold' ? 100 : normalized === 'Silver' ? 70 : 40,
        source: `${SIGNIFICANCE_VERSION}+canonical`,
        reasons: [`Feed provided significance_tier=${normalized}`]
      };
    }
  }

  // Explicitly ignore purchase / sponsorship / advertiser identity.
  void event.sponsored;
  void event.is_sponsored;
  void event.paid_tier;
  void event.advertiser;
  void event.sponsor;
  void event.payment_status;
  void event.organizer;

  if (isExcludedGeneric(event)) {
    return {
      tier: null,
      score: 0,
      source: SIGNIFICANCE_VERSION,
      reasons: ['Excluded as routine reservation, maintenance, closed, or ordinary practice']
    };
  }

  let score = 0;
  const title = String(event.title || '');
  const eventType = String(event.event_type || event.type || '');
  const blob = textBlob(event);
  const closure = String(event.street_closure_type || '').trim();
  const hours = durationHours(event);
  const crowdScore = num(event.expected_crowd_score);
  const priorityScore = num(event.priority_score);
  const crowdLevel = String(event.crowd_level || '').toLowerCase();
  const cat = String(event.category?.key || event.category || '').toLowerCase();

  if (GOLD_TITLE.test(title) || GOLD_TITLE.test(eventType)) {
    score += 55;
    reasons.push('Title/type matches major citywide or landmark event patterns');
  } else if (SILVER_TITLE.test(title) || SILVER_TITLE.test(eventType)) {
    score += 32;
    reasons.push('Title/type matches civic/festival/parade/fair patterns');
  } else if (BRONZE_TITLE.test(title) || BRONZE_TITLE.test(eventType)) {
    score += 14;
    reasons.push('Title/type matches public market or partner event patterns');
  }

  if (/parade/i.test(eventType)) {
    score += 28;
    reasons.push(`Event type is Parade`);
  } else if (/block party/i.test(eventType)) {
    score += 22;
    reasons.push('Event type is Block Party');
  } else if (/farmers market|street fair|athletic race|street event|plaza/i.test(eventType)) {
    score += 16;
    reasons.push(`Event type indicates public gathering (${eventType})`);
  } else if (/production event|open culture|health fair/i.test(eventType)) {
    score += 12;
    reasons.push(`Cultural/production event type (${eventType})`);
  } else if (/special event/i.test(eventType)) {
    score += 4;
    reasons.push('Special Event permit type');
  }

  if (/full street closure/i.test(closure)) {
    score += 30;
    reasons.push('Full street closure scheduled');
  } else if (/sidewalk and street|sidewalk and curb/i.test(closure)) {
    score += 22;
    reasons.push(`Significant street/sidewalk closure (${closure})`);
  } else if (/pedestrian plaza/i.test(closure)) {
    score += 18;
    reasons.push('Pedestrian plaza impact');
  } else if (closure && closure !== 'N/A') {
    score += 10;
    reasons.push(`Street/public-way impact (${closure})`);
  }

  if (hours >= 8) {
    score += 16;
    reasons.push(`Long duration (${hours.toFixed(1)} hours)`);
  } else if (hours >= 4) {
    score += 10;
    reasons.push(`Multi-hour duration (${hours.toFixed(1)} hours)`);
  } else if (hours >= 2) {
    score += 4;
    reasons.push(`Extended duration (${hours.toFixed(1)} hours)`);
  }

  if (crowdScore >= 1000) {
    score += 40;
    reasons.push(`Very high expected crowd score (${crowdScore})`);
  } else if (crowdScore >= 400) {
    score += 28;
    reasons.push(`High expected crowd score (${crowdScore})`);
  } else if (crowdScore >= 150) {
    score += 16;
    reasons.push(`Elevated expected crowd score (${crowdScore})`);
  } else if (crowdScore >= 50) {
    score += 8;
    reasons.push(`Moderate expected crowd score (${crowdScore})`);
  }

  if (priorityScore >= 80) {
    score += 20;
    reasons.push(`High priority_score (${priorityScore})`);
  } else if (priorityScore >= 40) {
    score += 10;
    reasons.push(`Elevated priority_score (${priorityScore})`);
  }

  if (crowdLevel === 'very_high') {
    score += 30;
    reasons.push('Crowd level very_high');
  } else if (crowdLevel === 'high') {
    score += 22;
    reasons.push('Crowd level high');
  } else if (crowdLevel === 'medium_high') {
    score += 14;
    reasons.push('Crowd level medium_high');
  } else if (crowdLevel === 'medium') {
    score += 6;
    reasons.push('Crowd level medium');
  }

  if (event.major_reason) {
    score += 12;
    reasons.push(`Major-reason note: ${String(event.major_reason).slice(0, 80)}`);
  }
  if (event.photo_pick === true || event.photoPick === true) {
    score += 14;
    reasons.push('Marked photo_pick / camera-friendly');
  }
  if (event.field_default === true) {
    score += 10;
    reasons.push('Included in major/field assignment set');
  }
  if (event.assignment_feed === 'major' || event._from_major_feed === true) {
    score += 8;
    reasons.push('Present on major assignment feed');
  }
  if (cat === 'parade' || cat === 'market' || cat === 'arts') {
    score += 6;
    reasons.push(`Public-facing category (${cat})`);
  }

  // Conservative thresholds — ordinary special-event permits stay largely untiered.
  let tier = null;
  if (score >= 85) tier = 'Gold';
  else if (score >= 50) tier = 'Silver';
  else if (score >= 28) tier = 'Bronze';

  if (!tier) {
    return {
      tier: null,
      score,
      source: SIGNIFICANCE_VERSION,
      reasons: reasons.length
        ? reasons
        : ['Insufficient public-significance evidence for a tier']
    };
  }

  return {
    tier,
    score,
    source: SIGNIFICANCE_VERSION,
    reasons: reasons.length ? reasons : [`Score ${score} met ${tier} threshold`]
  };
}

export function significanceBadgeHtml(significance, esc = s => String(s ?? '')) {
  if (!significance?.tier) return '';
  const tier = significance.tier;
  const label =
    tier === 'Gold' ? 'Gold significance' : tier === 'Silver' ? 'Silver significance' : 'Bronze significance';
  return `<span class="tier-badge tier-badge--${tier.toLowerCase()}" title="${esc(label)}"><span class="sr-only">${esc(label)}: </span>${esc(tier)}</span>`;
}

import assert from 'node:assert/strict';
import { classifyEventSignificance, SIGNIFICANCE_INTEGRITY } from '../event-significance-v01.js';
import { eventDateKey } from '../map-date-key-v01.js';

function test(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test('canonical significance_tier overrides fallback', () => {
  const result = classifyEventSignificance({
    title: 'Ordinary pick-up game',
    event_type: 'Sport - Adult',
    significance_tier: 'Gold',
    sponsored: true,
    paid_tier: 'ignore-me'
  });
  assert.equal(result.tier, 'Gold');
  assert.match(result.source, /canonical/);
  assert.ok(result.reasons.length >= 1);
});

test('paid/sponsored fields do not create tiers', () => {
  const base = { title: 'closed', event_type: 'Special Event' };
  const a = classifyEventSignificance(base);
  const b = classifyEventSignificance({
    ...base,
    sponsored: true,
    is_sponsored: true,
    paid_tier: 'Gold',
    advertiser: 'Acme',
    sponsor: 'Acme',
    payment_status: 'paid',
    organizer: 'Paid Org'
  });
  assert.deepEqual(a, b);
  assert.equal(a.tier, null);
});

test('maintenance and closed remain untiered', () => {
  assert.equal(classifyEventSignificance({ title: 'closed', event_type: 'Special Event' }).tier, null);
  assert.equal(
    classifyEventSignificance({ title: 'Bowling Greens - Maintenance Day - Closed All Day', event_type: 'Special Event' }).tier,
    null
  );
});

test('world cup / street closure evidence can reach Gold', () => {
  const result = classifyEventSignificance({
    title: 'World Cup Celebration',
    event_type: 'Street Event',
    street_closure_type: 'Full Street Closure',
    start_date_time: '2026-07-14T12:00:00',
    end_date_time: '2026-07-14T16:00:00',
    category: 'market'
  });
  assert.equal(result.tier, 'Gold');
  assert.ok(result.reasons.length >= 1);
});

test('ordinary youth sport stays untiered', () => {
  const result = classifyEventSignificance({
    title: 'Baseball - 12 and Under (Little League)',
    event_type: 'Sport - Youth',
    category: 'sports'
  });
  assert.equal(result.tier, null);
});

test('every returned tier includes reasons and integrity statement exists', () => {
  const result = classifyEventSignificance({
    title: 'Evening of Jazz',
    event_type: 'Block Party',
    street_closure_type: 'Full Street Closure',
    category: 'parade'
  });
  assert.ok(['Gold', 'Silver', 'Bronze'].includes(result.tier));
  assert.ok(result.reasons.length >= 1);
  assert.match(SIGNIFICANCE_INTEGRITY, /cannot be purchased/i);
});

test('row.date wins over UTC-shifted start_date_time', () => {
  const key = eventDateKey(
    { date: '2026-07-14', start_date_time: '2026-07-15T03:00:00.000Z' },
    new Date('2026-07-15T03:00:00.000Z')
  );
  assert.equal(key, '2026-07-14');
});

test('invalid date falls back to start local dateKey', () => {
  const start = new Date(2026, 6, 16, 9, 0, 0);
  const key = eventDateKey({ date: 'not-a-date', start_date_time: '2026-07-16T13:00:00.000Z' }, start);
  assert.equal(key, '2026-07-16');
});

console.log('All map restore unit tests passed.');

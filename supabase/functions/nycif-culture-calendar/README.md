# `nycif-culture-calendar` (deployed, gated)

Public Culture / help-calendar reader. Deployed with `verify_jwt=false` like
`nycif-culture-places` and `nycif-native-map-feed`. Gates stay off until
Phase C6.

## Purpose

8-day Culture calendar for the native app: **today + next 7 days** in
`America/New_York`, same chip pattern as `nycif-native-map-feed`
Now / Tonight / 7 Days, but Culture-sorted.

Row kinds: worship services, cultural festivals, ASPCA Community Medicine
van days, community clinics, plus rolling public-help:

| Chip | Emoji | `occurrence_kind` |
| --- | --- | --- |
| Blood | 🩸 | `blood_drive` |
| Mobile clinic | 🏥 | `mobile_clinic`, `resource_van` |
| Jobs | 💼 | `job_fair`, `workshop` |
| College | 🎓 | same kinds, `source_family=cuny` |
| Pet care | 🐾 | `pet_mobile` |

Help-layer gates (`help_calendar_publication_enabled`, `blood_layer_enabled`,
…) default false.

ASPCA / waitlist programs: `waitlist_gated=true`, `pin_policy=zip_area_only`
or `list_only`. Do not emit a street pin until a public site exists.

## Response

```json
{
  "authority": "nycif-culture-calendar",
  "schema_version": "culture-calendar-v1",
  "calendar_publication_enabled": false,
  "help_calendar_publication_enabled": false,
  "timezone": "America/New_York",
  "today": "2026-09-06",
  "window_days": 8,
  "tonight_window": {
    "start": "17:00:00",
    "end_inclusive": "23:59:59",
    "timezone": "America/New_York"
  },
  "chips": [
    { "id": "now", "label": "Now" },
    { "id": "tonight", "label": "Tonight" },
    { "id": "seven", "label": "7 Days" }
  ],
  "occurrences": []
}
```

Query: `?mode=now|tonight|seven` (default `seven`).

Overlap rules copy `nycif-native-map-feed`:

- Now / today: overlap with today midnight–tomorrow midnight ET
- Tonight: `start_at` in 17:00–23:59:59 ET today
- 7 Days: overlap today through today+7

## Fail-closed

- `calendar_publication_enabled` false ⇒ `occurrences: []`
- Exclude pending / sample / rejected
- `map_ready` only with certified NYC coords and `pin_policy=certified_pin`
- Do not write these rows into `event_occurrences`

## Security

Service role in the function only. No `service_role` in iOS. RLS deny-all.
GET/HEAD/OPTIONS. `verify_jwt=false` (publishable / anon key, same as other
Culture readers).

## iOS

`CultureService.fetchCalendar()` treats HTTP 200 + gate false as empty, not
as a missing function. HTTP 404 remains “not shipped yet.”

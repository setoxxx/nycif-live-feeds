# iOS EventService checklist — native map feed

Product contract locked 2026-09-05:

- Phone reads **only** the Edge Function. Never GitHub raw JSON, Pages, or WordPress.
- Chips are separate fetches: Now / Tonight / 7 Days.
- `event_reader_rolling_v1` stays open-ended for newsroom/search.
- Civic events are a daily batch. Do **not** subscribe Realtime on `event_occurrences`.
- Keep Realtime isolated to frequency / radio channels.
- Catch-up must **not** expire rows missing from today’s city snapshot.
- Protected files stay untouched: `data/location_cache.json`, `data/nycif_staged_live_events.json`, `data/staged_live_manifest.json`, `data/previous_staged_live_events_snapshot.json`.

Verified live against project `oggwpvdirkrnzoolparx` on 2026-09-05 ~09:23 America/New_York.

## 1. Endpoint

Base (us-west-2 project, function JWT verification **off** because the function uses the service role server-side):

```
https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-native-map-feed
```

| Chip | Request | Window |
|---|---|---|
| Now | `GET .../nycif-native-map-feed?mode=now` | Today ET overlap |
| Tonight | `GET .../nycif-native-map-feed?mode=tonight` | Today 18:00–23:59 ET |
| 7 Days | `GET .../nycif-native-map-feed?mode=seven` | Tomorrow through today+7 |
| One future day | `GET .../nycif-native-map-feed?mode=day&date=YYYY-MM-DD` | That ET calendar day, must be one of the `days[]` dates |

Aliases: `mode=7d` is treated as `seven`. Anything else falls back to `now`.

HEAD is supported (same cache headers, empty body). OPTIONS is CORS preflight.

## 2. Headers

Send the **anon** key. Do not embed the service-role key in the app.

```
GET /functions/v1/nycif-native-map-feed?mode=now HTTP/2
Host: oggwpvdirkrnzoolparx.supabase.co
apikey: <SUPABASE_ANON_KEY>
Authorization: Bearer <SUPABASE_ANON_KEY>
Accept: application/json
```

`verify_jwt` is currently false on this function, so a missing JWT still returns 200. Still send `apikey`. That is the product rule: anon key + Edge Function, never a direct PostgREST read of `event_occurrences`.

Do **not** query `event_occurrences` or `event_reader_rolling_v1` from the phone. Those surfaces are larger than the map window and include rows the Edge Function hides (citywide, cancelled titles, borough/coord mismatch, multi-site Parks).

## 3. Live sizes (2026-09-05 morning ET)

| Mode | HTTP | Events | Mapped | List-only | Bytes | Notes |
|---|---|---|---|---|---|---|
| `now` | 200 | 987 | 840 | 147 | ~714 KB | Today overlap |
| `tonight` | 200 | 0 | 0 | 0 | ~3 KB | Expected before 18:00 ET |
| `seven` | 200 | 996 | 928 | 68 | ~694 KB | Starts tomorrow |

Cache headers from the function:

```
Cache-Control: public, max-age=20, s-maxage=20, stale-while-revalidate=40
```

A 714 KB JSON decode should be well under a second on device. If Xcode still sits for ~60s, EventService is still pointing at a GitHub / static file. Search the target for:

- `raw.githubusercontent.com`
- `github.com/setoxxx`
- `nycif_all_radar`
- `nycif_staged_live`
- `setoxxx.github.io`
- `nycinfocus.com/map`

Those URLs are not the product path.

## 4. Envelope (`schema_version = NYCIF_NATIVE_MAP_FEED_V5`)

Top-level keys the phone should decode:

| Field | Type | Use |
|---|---|---|
| `schema_version` | String | Fail closed if unexpected major |
| `authority` | String | Expect `supabase_event_reader_rolling_v1` |
| `runtime_dependency` | String | Expect `supabase_only` |
| `generated_at` | ISO-8601 | Cache timestamp |
| `timezone` | String | Always `America/New_York` |
| `mode` | String | Echo of resolved mode |
| `selected_date` | String? | Set only for `mode=day` |
| `window_start` | `YYYY-MM-DD` | Inclusive ET date |
| `window_end_exclusive` | `YYYY-MM-DD` | Exclusive ET date |
| `tonight_window` | object | `{start:"18:00:00", end_inclusive:"23:59:59", timezone}` |
| `chip_rows` | object | `primary`, `night`, `seven` |
| `days` | array | Next 7 days with `total` / `mapped` / `list_only` |
| `mode_counts` | object | Counts for now / tonight / seven |
| `event_count` | Int | `events.count` |
| `mapped_event_count` | Int | Pins |
| `list_only_event_count` | Int | List rows with null coords |
| `events` | array | Payload |

Night chips (`It's 5 PM Somewhere`, dispensaries, liquor) are **aux layers**, not civic events. Do not mix them into `EventService`. They have their own Edge Functions.

## 5. Event row → Swift / MapKit

```swift
struct NativeMapFeed: Decodable {
    let schemaVersion: String
    let authority: String
    let generatedAt: Date
    let timezone: String
    let mode: String
    let windowStart: String
    let windowEndExclusive: String
    let eventCount: Int
    let mappedEventCount: Int
    let listOnlyEventCount: Int
    let events: [NativeMapEvent]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case authority
        case generatedAt = "generated_at"
        case timezone, mode
        case windowStart = "window_start"
        case windowEndExclusive = "window_end_exclusive"
        case eventCount = "event_count"
        case mappedEventCount = "mapped_event_count"
        case listOnlyEventCount = "list_only_event_count"
        case events
    }
}

struct NativeMapEvent: Decodable, Identifiable {
    let id: String                 // 64-char SHA-256 occurrence_id
    let title: String
    let startAt: Date?
    let endAt: Date?
    let timezone: String
    let borough: String?
    let locationId: String?
    let location: String?          // display_location
    let latitude: Double?
    let longitude: Double?
    let category: String
    let subtype: String?
    let mapped: Bool
    let certifiedPin: Bool
    let mapEligibilityState: String
    let locationAuthority: String?
    let displayDisposition: String
    let isMajor: Bool
    let photoPick: Bool
    let significance: String?
    let sourceDataset: String?
    let sourceEventId: String?
    let publicURL: URL?

    enum CodingKeys: String, CodingKey {
        case id, title, timezone, borough, location, latitude, longitude
        case category, subtype, mapped, significance
        case startAt = "start_at"
        case endAt = "end_at"
        case locationId = "location_id"
        case certifiedPin = "certified_pin"
        case mapEligibilityState = "map_eligibility_state"
        case locationAuthority = "location_authority"
        case displayDisposition = "display_disposition"
        case isMajor = "is_major"
        case photoPick = "photo_pick"
        case sourceDataset = "source_dataset"
        case sourceEventId = "source_event_id"
        case publicURL = "public_url"
    }
}
```

MapKit rule — plot a pin **only** when all of these are true:

- `mapped == true`
- `certifiedPin == true`
- `mapEligibilityState == "MAP_READY"`
- `latitude` and `longitude` are non-nil finite Doubles

Otherwise keep the row on the list. List-only rows already have `latitude`/`longitude` = `null` (feast example on 2026-09-05: *Feast of SS. Crocifisso*). Do not geocode them on device.

```swift
extension NativeMapEvent {
    var mapCoordinate: CLLocationCoordinate2D? {
        guard mapped, certifiedPin, mapEligibilityState == "MAP_READY",
              let lat = latitude, let lng = longitude,
              lat.isFinite, lng.isFinite else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lng)
    }
}
```

`id` is stable. Use it as `MKAnnotation` identity so a refresh does not rebuild every pin.

ISO timestamps are timestamptz (`2026-09-04T16:00:00+00:00`). Decode with `ISO8601DateFormatter` including fractional seconds as a fallback. Display in `America/New_York`, not the device zone, unless the user has opted into local time.

## 6. EventService behavior

Recommended first-paint sequence:

1. Cold launch: fetch `mode=now` only. Render list + pins.
2. Warm the other chips in the background after first paint (`tonight`, then `seven`).
3. Chip tap: if that mode is already cached and `generated_at` is from the current ET calendar day, show cache; else refetch that mode only.
4. Pull-to-refresh: refetch the **visible** mode, not all three.
5. On ET midnight crossing: drop disk cache. Windows are date-based in New York, not the phone’s zone.

Empty `tonight` before 18:00 ET is valid. Show the empty state, do not fall back to GitHub.

HTTP 503 body `{ "error": "native_map_feed_unavailable" }` means keep the last good cache and surface a retry. Do not swap in a static file.

## 7. App config (Xcode)

Store in a build setting / `.xcconfig` / Info.plist, not hardcoded in six files:

```
NYCIF_SUPABASE_URL = https://oggwpvdirkrnzoolparx.supabase.co
NYCIF_SUPABASE_ANON_KEY = <anon publishable key>
NYCIF_NATIVE_MAP_FEED = /functions/v1/nycif-native-map-feed
```

ATS: HTTPS only. No exception domains needed for `supabase.co`.

## 8. QA in Xcode

- [ ] Charles / Instruments: first map screen performs **one** GET to `nycif-native-map-feed?mode=now`.
- [ ] No request to `github.com`, `githubusercontent.com`, or `nycinfocus.com/map`.
- [ ] First decode + pin render under ~2s on a physical device after TLS.
- [ ] 840 pins today (2026-09-05 morning snapshot) have finite coords; 147 list rows have nil coords.
- [ ] Tapping Tonight before 18:00 ET shows 0 rows, not a spinner-of-death.
- [ ] Tapping 7 Days fetches `mode=seven` and does not include today’s Now set as the primary window (`window_start` is tomorrow).
- [ ] A list-only feast row never appears as an `MKPointAnnotation`.
- [ ] Radio / freq Realtime socket stays on its own channel and is not opened by `EventService`.
- [ ] Airplane mode after a successful fetch still shows the last cached Now list.

## 9. What this repo will not do for the phone

- No new 8:00 PM weekday GitHub Action.
- No 8-day JSON artifact under `data/`.
- No Realtime publication on `event_occurrences`.
- No catch-up expire.
- No writes to protected GPS files.

Optional follow-up (not required for the load-time fix): `supabase/migrations/20260905140000_native_map_feed_epoch_optional.sql` on this branch. Draft only. Not applied. Not added to `supabase_realtime`. Catch-up is not wired to it.

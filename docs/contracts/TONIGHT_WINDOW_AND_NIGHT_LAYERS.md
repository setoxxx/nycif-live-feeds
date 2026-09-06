# Tonight window and night layers

Status: production contract
Runtime: Supabase `oggwpvdirkrnzoolparx`
Public client: `nycif-native-map-feed` with a publishable/anon key. Never `service_role`.

## Tonight events

Tonight is **today's late-afternoon and evening starts** in `America/New_York`.

| Bound | Value |
|---|---|
| Start | `17:00:00` America/New_York |
| End | tomorrow midnight exclusive |
| Rule | `start_at >= today 17:00 ET AND start_at < tomorrow 00:00 ET` |

This matches:

- `nycif-field-desk` `isTonightEvent` (`hour >= 17`)
- iOS `NYCCalendar.startsTonightOrLater` (`hour >= 17`)
- The locked "It's 5 PM Somewhere" Tonight aux chip

Do **not** define Tonight as an overlap window. Overlap pulls multi-day street permits that started weeks earlier.

Do **not** start Tonight at 18:00. That drops the 5pm Parks / civic hour Howard reported missing.

SQL authority:

- `public.nycif_native_map_feed_rows(p_mode => 'tonight')`
- `public.nycif_native_map_feed_stats()` → `tonight`

The Edge Function must read those SQL tonight rows. It must not re-derive Tonight by taking `mode=now` rows and filtering hours in JavaScript.

## Night layers (not events)

Dispensaries, liquor stores, and It's 5 PM Somewhere are **Tonight auxiliary overlays**. They are not `event_occurrences` and must not be merged into the canonical event corpus.

Locked chips (also the iOS `SecondaryChip` set):

| id | Label | Endpoint |
|---|---|---|
| `5pm` | It's 5 PM Somewhere | `nycif-night-layers?layer=5pm` |
| `dispensary` | Legal Cannabis Shops / Dispensaries | `nycif-night-layers?layer=dispensary` |
| `liquor` | Liquor Stores | `nycif-night-layers?layer=liquor` |

The native feed exposes them on `chip_rows.night` / `tonight_aux_layers` with a public `url`. iOS already renders those chips under Tonight; tap should fetch the GeoJSON with the publishable key, not show "Coming next".

They are **not** hamburger/menu special collections. `nycif-special-calendars` / `event_collections` remain NYFW-style calendars.

Refresh stays on `nycif-night-layer-refresh` into `nycif_night_layer_cache`. A failed refresh must leave last-known-good GeoJSON.

## Safety

- No `location_cache.json` writes
- No WordPress map publish
- No `service_role` in public clients
- Street permits stay off the map unless they already meet the official pin contract

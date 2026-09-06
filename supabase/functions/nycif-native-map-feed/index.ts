import { createClient } from "npm:@supabase/supabase-js@2.45.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const db = createClient(SUPABASE_URL, SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, authorization, apikey",
};

const NIGHT_LAYER_BASE = `${SUPABASE_URL.replace(/\/$/, "")}/functions/v1/nycif-night-layers`;

const NIGHT_AUX_LAYER_DEFS = [
  { id: "5pm", label: "It's 5 PM Somewhere", chip_label: "5 P.M. Somewhere", emoji: "🍹", layer: "5pm" },
  { id: "dispensary", label: "Legal Cannabis Shops", chip_label: "Dispensaries", emoji: "🌿", layer: "dispensary" },
  { id: "liquor", label: "Liquor Stores", chip_label: "Liquor Stores", emoji: "🍸", layer: "liquor" },
];

const TONIGHT_WINDOW = {
  start: "17:00:00",
  end_inclusive: "23:59:59",
  timezone: "America/New_York",
  rule: "start_at >= today 17:00 America/New_York and start_at < tomorrow midnight",
};

const PRIMARY_CHIPS = [
  { id: "now", label: "Now" },
  { id: "tonight", label: "Tonight" },
  { id: "seven", label: "7 Days" },
];

function json(body: unknown, status = 200, head = false) {
  return new Response(head ? null : JSON.stringify(body), {
    status,
    headers: {
      ...cors,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200
        ? "public, max-age=20, s-maxage=20, stale-while-revalidate=40"
        : "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const weekdayFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "long",
});

const shortWeekdayFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
});

const monthDayFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  month: "short",
  day: "numeric",
});

function dayKey(date: Date): string {
  return dayFormatter.format(date);
}

function addDays(day: string, offset: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return dayFormatter.format(new Date(Date.UTC(y, m - 1, d + offset, 16, 0, 0)));
}

function utcForDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 16, 0, 0));
}

function nextSevenDays(today: string) {
  return Array.from({ length: 7 }, (_, index) => {
    const date = addDays(today, index + 1);
    const when = utcForDay(date);
    const weekday = weekdayFormatter.format(when);
    return {
      date,
      weekday,
      weekday_short: shortWeekdayFormatter.format(when),
      label: `${weekday} ${monthDayFormatter.format(when)}`,
    };
  });
}

function explicitCancelled(title: unknown): boolean {
  return /^\s*(CANCELED|CANCELLED)\s*:/i.test(String(title ?? ""));
}

function validUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text) return null;
  try {
    const parsed = new URL(text);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? text : null;
  } catch {
    return null;
  }
}

function eventDates(row: Record<string, unknown>) {
  const start = new Date(String(row.start_at ?? "").replace(" ", "T"));
  if (!Number.isFinite(start.getTime())) return null;

  let end = row.end_at
    ? new Date(String(row.end_at).replace(" ", "T"))
    : new Date(start.getTime() + 3 * 60 * 60 * 1000);

  if (!Number.isFinite(end.getTime()) || end < start) end = start;

  return {
    startDay: dayKey(start),
    endDay: dayKey(end),
  };
}

function overlapsDay(row: Record<string, unknown>, day: string): boolean {
  const d = eventDates(row);
  return !!d && d.startDay <= day && d.endDay >= day;
}

function overlapsSeven(row: Record<string, unknown>, first: string, last: string): boolean {
  const d = eventDates(row);
  return !!d && d.startDay <= last && d.endDay >= first;
}

function coordsMatchBorough(lat: number, lng: number, borough: unknown): boolean {
  const name = String(borough ?? "").trim().toLowerCase();
  if (name === "manhattan") return lat >= 40.67 && lat <= 40.89 && lng >= -74.05 && lng <= -73.90;
  if (name === "brooklyn") return lat >= 40.55 && lat <= 40.75 && lng >= -74.06 && lng <= -73.82;
  if (name === "queens") return lat >= 40.53 && lat <= 40.82 && lng >= -73.98 && lng <= -73.69;
  if (name === "bronx") return lat >= 40.77 && lat <= 40.93 && lng >= -73.95 && lng <= -73.74;
  if (name === "staten island") return lat >= 40.47 && lat <= 40.66 && lng >= -74.27 && lng <= -74.03;
  return true;
}

function isMapped(row: Record<string, unknown>): boolean {
  const lat = Number(row.lat);
  const lng = Number(row.lng);
  return row.certified_pin === true
    && row.map_eligibility_state === "MAP_READY"
    && Number.isFinite(lat)
    && Number.isFinite(lng)
    && lat >= 40.45 && lat <= 40.95
    && lng >= -74.30 && lng <= -73.65
    && coordsMatchBorough(lat, lng, row.borough);
}

function toPublicEvent(row: Record<string, unknown>) {
  const mapped = isMapped(row);
  return {
    id: String(row.occurrence_id ?? ""),
    title: String(row.title ?? "Untitled event"),
    start_at: row.start_at ?? null,
    end_at: row.end_at ?? null,
    timezone: String(row.timezone ?? "America/New_York"),
    borough: row.borough ?? null,
    location_id: row.location_id ?? null,
    location: row.display_location ?? null,
    latitude: mapped ? Number(row.lat) : null,
    longitude: mapped ? Number(row.lng) : null,
    category: row.public_category ?? "general",
    subtype: row.public_subtype ?? null,
    mapped,
    certified_pin: mapped,
    map_eligibility_state: row.map_eligibility_state ?? (mapped ? "MAP_READY" : "LIST_ONLY"),
    location_authority: row.location_authority ?? null,
    display_disposition: row.display_disposition ?? (mapped ? "MAP" : "LIST_ONLY"),
    is_major: row.is_major === true,
    photo_pick: row.photo_pick === true,
    significance: row.significance ?? null,
    source_dataset: row.source_dataset ?? null,
    source_event_id: row.source_event_id ?? null,
    public_url: validUrl(row.public_url),
  };
}

function stats(rows: Record<string, unknown>[]) {
  const mapped = rows.reduce((n, row) => n + (isMapped(row) ? 1 : 0), 0);
  return { total: rows.length, mapped, list_only: rows.length - mapped };
}

function normalizeMode(value: string): "now" | "tonight" | "seven" | "day" {
  const mode = value.toLowerCase();
  if (mode === "tonight") return "tonight";
  if (mode === "seven" || mode === "7d") return "seven";
  if (mode === "day") return "day";
  return "now";
}

function nightLayers(
  counts: Record<string, { feature_count: number | null; source_refreshed_at: string | null }>,
) {
  return NIGHT_AUX_LAYER_DEFS.map((layer) => ({
    ...layer,
    url: `${NIGHT_LAYER_BASE}?layer=${encodeURIComponent(layer.layer)}`,
    auth: "publishable",
    feature_count: counts[layer.layer]?.feature_count ?? null,
    source_refreshed_at: counts[layer.layer]?.source_refreshed_at ?? null,
  }));
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (req.method !== "GET" && req.method !== "HEAD") {
    return json({ error: "method_not_allowed" }, 405, req.method === "HEAD");
  }

  const url = new URL(req.url);
  const mode = normalizeMode(String(url.searchParams.get("mode") ?? "now"));
  const today = dayKey(new Date());
  const days = nextSevenDays(today);
  const requestedDay = String(url.searchParams.get("date") ?? "");
  const selectedDay = days.some((day) => day.date === requestedDay) ? requestedDay : "";
  const sevenFirst = days[0].date;
  const sevenLast = days[6].date;

  try {
    const [nowResult, tonightResult, sevenResult, statsResult, layerResult] = await Promise.all([
      db.rpc("nycif_native_map_feed_rows", { p_mode: "now" }),
      db.rpc("nycif_native_map_feed_rows", { p_mode: "tonight" }),
      db.rpc("nycif_native_map_feed_rows", { p_mode: "seven" }),
      db.rpc("nycif_native_map_feed_stats"),
      db.from("nycif_night_layer_cache").select("layer, feature_count, source_refreshed_at"),
    ]);

    if (nowResult.error) throw nowResult.error;
    if (tonightResult.error) throw tonightResult.error;
    if (sevenResult.error) throw sevenResult.error;

    const nowRows = ((nowResult.data ?? []) as Record<string, unknown>[])
      .filter((row) => !explicitCancelled(row.title) && overlapsDay(row, today));
    const tonightRows = ((tonightResult.data ?? []) as Record<string, unknown>[])
      .filter((row) => !explicitCancelled(row.title));
    const sevenRows = ((sevenResult.data ?? []) as Record<string, unknown>[])
      .filter((row) => !explicitCancelled(row.title) && overlapsSeven(row, sevenFirst, sevenLast));
    const dayRows = selectedDay ? sevenRows.filter((row) => overlapsDay(row, selectedDay)) : sevenRows;

    const selected = mode === "tonight"
      ? tonightRows
      : mode === "seven"
        ? sevenRows
        : mode === "day"
          ? dayRows
          : nowRows;

    const dayCounts = days.map((day) => ({
      ...day,
      ...stats(sevenRows.filter((row) => overlapsDay(row, day.date))),
    }));

    const layerCounts: Record<string, { feature_count: number | null; source_refreshed_at: string | null }> = {};
    for (const row of (layerResult.data ?? []) as Array<Record<string, unknown>>) {
      layerCounts[String(row.layer)] = {
        feature_count: typeof row.feature_count === "number" ? row.feature_count : null,
        source_refreshed_at: row.source_refreshed_at ? String(row.source_refreshed_at) : null,
      };
    }
    const auxLayers = nightLayers(layerCounts);

    return json({
      schema_version: "NYCIF_NATIVE_MAP_FEED_V6",
      authority: "supabase_event_reader_rolling_v1",
      runtime_dependency: "supabase_only",
      generated_at: new Date().toISOString(),
      timezone: "America/New_York",
      mode: mode === "day" && selectedDay ? "day" : mode,
      selected_date: selectedDay || null,
      window_start: mode === "seven" || mode === "day" ? sevenFirst : today,
      window_end_exclusive: mode === "seven" || mode === "day" ? addDays(today, 8) : addDays(today, 1),
      tonight_window: TONIGHT_WINDOW,
      toggle: {
        tonight: mode === "tonight",
        seven: mode === "seven" || mode === "day",
      },
      chip_rows: {
        primary: PRIMARY_CHIPS,
        night: auxLayers,
        seven: dayCounts.map((day) => ({
          id: day.date,
          date: day.date,
          label: day.weekday_short,
          sublabel: day.label.replace(day.weekday + " ", ""),
          weekday: day.weekday,
        })),
      },
      days: dayCounts,
      tonight_aux_layers: auxLayers,
      night_layers_endpoint: NIGHT_LAYER_BASE,
      mode_counts: {
        now: stats(nowRows),
        tonight: stats(tonightRows),
        seven: stats(sevenRows),
      },
      stats: statsResult.data ?? null,
      event_count: selected.length,
      mapped_event_count: stats(selected).mapped,
      list_only_event_count: stats(selected).list_only,
      events: selected.map(toPublicEvent),
    }, 200, req.method === "HEAD");
  } catch (error) {
    console.error("native map feed query failed", error);
    return json({ error: "native_map_feed_unavailable" }, 503, req.method === "HEAD");
  }
});

import { createClient } from "npm:@supabase/supabase-js@2.45.0";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const db = createClient(SUPABASE_URL, SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,HEAD,OPTIONS",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
};

const TIMEZONE = "America/New_York";
const SCHEMA_VERSION = "culture-calendar-v1";
const NYC_LAT = { min: 40.45, max: 40.95 };
const NYC_LNG = { min: -74.3, max: -73.65 };

const CHIPS = [
  { id: "now", label: "Now" },
  { id: "tonight", label: "Tonight" },
  { id: "seven", label: "7 Days" },
];

const TONIGHT_WINDOW = {
  start: "17:00:00",
  end_inclusive: "23:59:59",
  timezone: TIMEZONE,
};

const HELP_LAYERS = [
  { id: "blood", label: "Blood", emoji: "🩸", kinds: ["blood_drive"] },
  {
    id: "mobile_clinic",
    label: "Mobile clinic",
    emoji: "🏥",
    kinds: ["mobile_clinic", "resource_van", "community_clinic"],
  },
  { id: "jobs", label: "Jobs", emoji: "💼", kinds: ["job_fair", "workshop"] },
  { id: "college", label: "College", emoji: "🎓", families: ["cuny", "college"] },
  { id: "pet", label: "Pet care", emoji: "🐾", kinds: ["pet_mobile", "aspca_van"] },
] as const;

const dayFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function json(body: unknown, status = 200, head = false) {
  return new Response(head ? null : JSON.stringify(body), {
    status,
    headers: {
      ...cors,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200
        ? "public, max-age=120, s-maxage=120, stale-while-revalidate=300"
        : "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function flag(value: unknown): boolean {
  return value === true;
}

function dayKey(date: Date): string {
  return dayFormatter.format(date);
}

function addDays(day: string, offset: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return dayFormatter.format(new Date(Date.UTC(y, m - 1, d + offset, 16, 0, 0)));
}

function eventDates(row: Record<string, unknown>) {
  const start = new Date(String(row.start_at ?? "").replace(" ", "T"));
  if (!Number.isFinite(start.getTime())) return null;
  let end = row.end_at
    ? new Date(String(row.end_at).replace(" ", "T"))
    : new Date(start.getTime() + 3 * 60 * 60 * 1000);
  if (!Number.isFinite(end.getTime()) || end < start) end = start;
  return { start, end, startDay: dayKey(start), endDay: dayKey(end) };
}

function overlapsDay(row: Record<string, unknown>, day: string): boolean {
  const d = eventDates(row);
  return !!d && d.startDay <= day && d.endDay >= day;
}

function overlapsSeven(row: Record<string, unknown>, first: string, last: string): boolean {
  const d = eventDates(row);
  return !!d && d.startDay <= last && d.endDay >= first;
}

function isTonight(row: Record<string, unknown>, today: string): boolean {
  const d = eventDates(row);
  if (!d) return false;
  const hour = new Intl.DateTimeFormat("en-US", {
    timeZone: TIMEZONE,
    hour: "2-digit",
    hourCycle: "h23",
  }).format(d.start);
  return d.startDay === today && Number(hour) >= 17;
}

function normalizeMode(value: string): "now" | "tonight" | "seven" {
  const mode = value.toLowerCase();
  if (mode === "tonight") return "tonight";
  if (mode === "now") return "now";
  return "seven";
}

function inNyc(lat: number, lng: number): boolean {
  return lat >= NYC_LAT.min && lat <= NYC_LAT.max && lng >= NYC_LNG.min && lng <= NYC_LNG.max;
}

function helpEnabled(settings: Record<string, unknown>, id: string): boolean {
  if (!flag(settings.help_calendar_publication_enabled)) return false;
  if (id === "blood") return flag(settings.blood_layer_enabled);
  if (id === "mobile_clinic") return flag(settings.mobile_clinic_layer_enabled);
  if (id === "jobs") return flag(settings.jobs_layer_enabled);
  if (id === "college") return flag(settings.college_layer_enabled);
  if (id === "pet") return flag(settings.pet_care_layer_enabled);
  return false;
}

function helpLayers(settings: Record<string, unknown>, counts: Record<string, number>) {
  const layers: Record<string, { enabled: boolean; emoji: string; count: number; label: string }> = {};
  for (const layer of HELP_LAYERS) {
    layers[layer.id] = {
      enabled: helpEnabled(settings, layer.id),
      emoji: layer.emoji,
      count: counts[layer.id] ?? 0,
      label: layer.label,
    };
  }
  return layers;
}

function chipFor(row: Record<string, unknown>) {
  const family = String(row.source_family ?? "").trim().toLowerCase();
  if (family === "cuny" || family === "college") {
    return { chip_id: "college", chip_label: "College", emoji: "🎓" };
  }
  const kind = String(row.occurrence_kind ?? row.calendar_kind ?? "");
  for (const layer of HELP_LAYERS) {
    if ("kinds" in layer && layer.kinds.includes(kind)) {
      return { chip_id: layer.id, chip_label: layer.label, emoji: layer.emoji };
    }
  }
  return {
    chip_id: row.chip_id ?? "other",
    chip_label: row.chip_label ?? "Culture",
    emoji: row.emoji ?? "📅",
  };
}

function helpChipId(row: Record<string, unknown>): string {
  return String(chipFor(row).chip_id);
}

function toPublicOccurrence(row: Record<string, unknown>) {
  const lat = Number(row.lat);
  const lng = Number(row.lng);
  const certified = row.map_ready === true
    && String(row.pin_policy ?? "") === "certified_pin"
    && row.waitlist_gated !== true
    && Number.isFinite(lat)
    && Number.isFinite(lng)
    && inNyc(lat, lng);
  const chip = chipFor(row);
  return {
    occurrence_id: String(row.occurrence_id ?? ""),
    title: String(row.title ?? ""),
    start_at: row.start_at ?? null,
    end_at: row.end_at ?? null,
    timezone: String(row.timezone ?? TIMEZONE),
    borough: row.borough ?? null,
    display_location: row.display_location ?? row.address ?? null,
    address: row.address ?? null,
    lat: certified ? lat : null,
    lng: certified ? lng : null,
    map_ready: certified,
    zip_codes: Array.isArray(row.zip_codes) ? row.zip_codes : [],
    waitlist_gated: row.waitlist_gated === true,
    pin_policy: certified ? "certified_pin" : String(row.pin_policy ?? "list_only"),
    occurrence_kind: row.occurrence_kind ?? row.calendar_kind ?? null,
    calendar_kind: row.calendar_kind ?? null,
    chip_id: chip.chip_id,
    chip_label: chip.chip_label,
    emoji: chip.emoji,
    source_name: row.source_name ?? null,
    source_dataset: row.source_dataset ?? null,
    source_event_id: row.source_event_id ?? null,
    source_family: row.source_family ?? null,
    is_sample: row.is_sample === true,
    review_status: row.review_status ?? null,
    public_url: row.public_url ?? null,
  };
}

function publishable(row: Record<string, unknown>): boolean {
  if (row.is_sample === true) return false;
  if (String(row.review_status ?? "").toUpperCase() !== "ACCEPTED") return false;
  if (row.promotion_allowed !== true) return false;
  const status = String(row.manual_review_status ?? "").toLowerCase();
  if (status && status !== "approved" && status !== "accepted") return false;
  const title = String(row.title ?? "").trim();
  return !!title && !!row.start_at;
}

function gatedBody(
  settings: Record<string, unknown>,
  today: string,
  occurrences: ReturnType<typeof toPublicOccurrence>[] = [],
) {
  const counts: Record<string, number> = {};
  for (const row of occurrences) {
    const id = String(row.chip_id ?? "");
    counts[id] = (counts[id] ?? 0) + 1;
  }
  const calendarOn = flag(settings.calendar_publication_enabled);
  return {
    authority: "nycif-culture-calendar",
    schema_version: SCHEMA_VERSION,
    calendar_publication_enabled: calendarOn,
    help_calendar_publication_enabled: flag(settings.help_calendar_publication_enabled),
    timezone: TIMEZONE,
    today,
    window_days: 8,
    note: calendarOn
      ? "ACCEPTED + promotion_allowed Culture calendar rows only. Samples and pending rows stay off."
      : "Culture calendar stays gated until calendar_publication_enabled is flipped after Phase C6.",
    tonight_window: TONIGHT_WINDOW,
    chips: CHIPS,
    help_layers: helpLayers(settings, calendarOn ? counts : {}),
    blood_layer_enabled: helpEnabled(settings, "blood"),
    mobile_clinic_layer_enabled: helpEnabled(settings, "mobile_clinic"),
    jobs_layer_enabled: helpEnabled(settings, "jobs"),
    college_layer_enabled: helpEnabled(settings, "college"),
    pet_care_layer_enabled: helpEnabled(settings, "pet"),
    occurrences: calendarOn ? occurrences : [],
  };
}

async function loadSettings(): Promise<Record<string, unknown>> {
  const { data, error } = await db
    .from("culture_reader_settings")
    .select("*")
    .eq("id", "v1")
    .maybeSingle();
  if (error) throw error;
  return (data ?? {}) as Record<string, unknown>;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (req.method !== "GET" && req.method !== "HEAD") {
    return json({ error: "method_not_allowed" }, 405, req.method === "HEAD");
  }

  const url = new URL(req.url);
  const mode = normalizeMode(String(url.searchParams.get("mode") ?? "seven"));
  const today = dayKey(new Date());
  const sevenLast = addDays(today, 7);

  try {
    const settings = await loadSettings();
    if (!flag(settings.calendar_publication_enabled)) {
      return json(gatedBody(settings, today), 200, req.method === "HEAD");
    }

    const { data, error } = await db
      .from("culture_calendar_occurrence_v1")
      .select(
        "occurrence_id,calendar_kind,occurrence_kind,title,start_at,end_at,timezone,borough,display_location,address,lat,lng,map_ready,zip_codes,waitlist_gated,pin_policy,chip_id,chip_label,emoji,source_name,source_dataset,source_event_id,source_family,public_url,is_sample,review_status,manual_review_status,promotion_allowed",
      )
      .order("start_at", { ascending: true });
    if (error) throw error;

    const rows = ((data ?? []) as Record<string, unknown>[]).filter(publishable).filter((row) => {
      if (mode === "tonight") return isTonight(row, today);
      if (mode === "now") return overlapsDay(row, today);
      return overlapsSeven(row, today, sevenLast);
    }).filter((row) => {
      const chip = helpChipId(row);
      if (HELP_LAYERS.some((layer) => layer.id === chip)) return helpEnabled(settings, chip);
      return true;
    });

    return json(
      gatedBody(settings, today, rows.map(toPublicOccurrence)),
      200,
      req.method === "HEAD",
    );
  } catch (error) {
    console.error("culture calendar query failed", error);
    return json(gatedBody({}, today), 200, req.method === "HEAD");
  }
});

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

const SCHEMA_VERSION = "culture-civic-v1";
const NYC_LAT = { min: 40.45, max: 40.95 };
const NYC_LNG = { min: -74.3, max: -73.65 };

const LAYERS = [
  { id: "nypd", label: "NYPD", emoji: "👮", place_kinds: ["civic_nypd", "nypd"], setting: "nypd_layer_enabled" },
  { id: "fdny", label: "FDNY", emoji: "🚒", place_kinds: ["civic_fdny", "fdny"], setting: "fdny_layer_enabled" },
  { id: "shelter", label: "Shelters", emoji: "🏠", place_kinds: ["shelter", "civic_shelter"], setting: "shelter_layer_enabled" },
  { id: "pet_care", label: "Pet care", emoji: "🐾", place_kinds: ["pet_care", "pet"], setting: "pet_care_layer_enabled" },
] as const;

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

function inNyc(lat: number, lng: number): boolean {
  return lat >= NYC_LAT.min && lat <= NYC_LAT.max && lng >= NYC_LNG.min && lng <= NYC_LNG.max;
}

function layerForKind(placeKind: string) {
  return LAYERS.find((layer) => layer.place_kinds.includes(placeKind));
}

function layerEnabled(settings: Record<string, unknown>, layerId: string): boolean {
  if (!flag(settings.civic_publication_enabled)) return false;
  const layer = LAYERS.find((item) => item.id === layerId);
  return layer ? flag(settings[layer.setting]) : false;
}

function publishable(row: Record<string, unknown>): boolean {
  if (row.is_sample === true) return false;
  if (String(row.review_status ?? "").toUpperCase() !== "ACCEPTED") return false;
  if (row.promotion_allowed !== true) return false;
  if (row.addressable !== true) return false;
  const status = String(row.manual_review_status ?? "").toLowerCase();
  if (status && status !== "approved" && status !== "accepted") return false;
  return String(row.display_name ?? "").trim().length > 0;
}

function toFeature(row: Record<string, unknown>) {
  const lat = Number(row.lat);
  const lng = Number(row.lng);
  const coordsOk = Number.isFinite(lat) && Number.isFinite(lng) && inNyc(lat, lng);
  const plottable = coordsOk && row.map_eligible !== false && row.addressable === true;
  const layer = layerForKind(String(row.place_kind ?? ""));
  const properties = {
    facility_id: String(row.facility_id ?? ""),
    display_name: String(row.display_name ?? ""),
    place_kind: row.place_kind ?? null,
    layer: layer?.id ?? null,
    address: row.address ?? null,
    borough: row.borough ?? null,
    lat: plottable ? lat : null,
    lng: plottable ? lng : null,
    emoji: row.emoji ?? layer?.emoji ?? null,
    addressable: row.addressable === true,
    map_eligible: plottable,
    source_dataset: row.source_dataset ?? null,
    source_facility_id: row.source_facility_id ?? null,
    review_status: row.review_status ?? null,
    is_sample: row.is_sample === true,
  };
  return {
    type: "Feature",
    geometry: plottable ? { type: "Point", coordinates: [lng, lat] } : null,
    properties,
    ...properties,
  };
}

function layerPayload(
  settings: Record<string, unknown>,
  features: ReturnType<typeof toFeature>[],
) {
  const civicOn = flag(settings.civic_publication_enabled);
  const layers: Record<string, { enabled: boolean; emoji: string; count: number; label: string }> = {};
  for (const layer of LAYERS) {
    const enabled = layerEnabled(settings, layer.id);
    const count = civicOn && enabled
      ? features.filter((feature) => feature.layer === layer.id || layer.place_kinds.includes(String(feature.place_kind ?? ""))).length
      : 0;
    layers[layer.id] = {
      enabled,
      emoji: layer.emoji,
      count,
      label: layer.label,
    };
  }
  return layers;
}

function gatedBody(
  settings: Record<string, unknown>,
  features: ReturnType<typeof toFeature>[] = [],
) {
  const civicOn = flag(settings.civic_publication_enabled);
  return {
    authority: "nycif-culture-civic",
    schema_version: SCHEMA_VERSION,
    civic_publication_enabled: civicOn,
    pet_care_layer_enabled: layerEnabled(settings, "pet_care"),
    note: civicOn
      ? "ACCEPTED + addressable civic rows only. Census-only and pending rows stay off."
      : "Civic layers stay gated until civic_publication_enabled is flipped after Phase C6.",
    layers: layerPayload(settings, civicOn ? features : []),
    features: civicOn ? features : [],
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
  const requested = String(url.searchParams.get("layer") ?? "").toLowerCase();
  const layerFilter = LAYERS.find((layer) => layer.id === requested || layer.place_kinds.includes(requested));

  try {
    const settings = await loadSettings();
    if (!flag(settings.civic_publication_enabled)) {
      return json(gatedBody(settings), 200, req.method === "HEAD");
    }

    const { data, error } = await db
      .from("culture_civic_facility_v1")
      .select(
        "facility_id,place_kind,source_dataset,source_facility_id,display_name,address,borough,lat,lng,emoji,addressable,map_eligible,review_status,is_sample,manual_review_status,promotion_allowed",
      )
      .order("display_name", { ascending: true });
    if (error) throw error;

    const features = ((data ?? []) as Record<string, unknown>[])
      .filter(publishable)
      .filter((row) => {
        const layer = layerForKind(String(row.place_kind ?? ""));
        if (!layer) return false;
        if (!layerEnabled(settings, layer.id)) return false;
        if (layerFilter && layer.id !== layerFilter.id) return false;
        return true;
      })
      .map(toFeature);

    return json(gatedBody(settings, features), 200, req.method === "HEAD");
  } catch (error) {
    console.error("culture civic query failed", error);
    return json(gatedBody({}), 200, req.method === "HEAD");
  }
});

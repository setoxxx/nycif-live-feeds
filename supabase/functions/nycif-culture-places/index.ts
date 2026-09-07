import { createClient } from "npm:@supabase/supabase-js:2.45.0";

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

/** PostgREST defaults to 1000 rows/page — page until exhausted or this ceiling. */
const PAGE_SIZE = 1000;
const MAX_PLACES = 5000;

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (req.method !== "GET" && req.method !== "HEAD") {
    return new Response(JSON.stringify({ error: "method_not_allowed" }), {
      status: 405,
      headers: { ...cors, "Content-Type": "application/json; charset=utf-8", Allow: "GET, HEAD, OPTIONS" },
    });
  }

  const url = new URL(req.url);
  const areaId = url.searchParams.get("area_id");

  const { data: settings, error: settingsError } = await db
    .from("culture_reader_settings")
    .select("business_publication_enabled, allow_sample_places")
    .eq("id", "v1")
    .maybeSingle();

  if (settingsError) {
    console.error("culture places settings failed", settingsError);
    return new Response(JSON.stringify({ error: "culture_places_unavailable" }), {
      status: 503,
      headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  }

  const publicationEnabled = settings?.business_publication_enabled === true;
  const allowSample = settings?.allow_sample_places === true;

  // Fail closed: never emit storefront pins while publication is off.
  if (!publicationEnabled) {
    const body = {
      authority: "supabase:culture_place_beta_v1",
      schema_version: "NYCIF_CULTURE_PLACE_BETA_V1",
      contract: "nycif.culture-places.v1",
      business_publication_enabled: false,
      place_count: 0,
      note: "Verified storefront pins stay gated until Culture business discovery review passes. Name-lead labels never publish.",
      places: [] as unknown[],
    };
    return new Response(req.method === "HEAD" ? null : JSON.stringify(body), {
      status: 200,
      headers: {
        ...cors,
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "public, max-age=120, s-maxage=120, stale-while-revalidate=300",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }

  type PlaceRow = {
    business_id: string;
    business_name: string;
    address: string | null;
    community_district: string | null;
    lat: number | null;
    lng: number | null;
    cultural_tags: string[] | null;
    dietary_tags: string[] | null;
    review_status: string | null;
    confidence: string | null;
    area_ids: string[] | null;
    matched_tags: string[] | null;
    reason_codes: string[] | null;
    is_sample: boolean | null;
    feed_version: string | null;
  };

  const selectCols =
    "business_id,business_name,address,community_district,lat,lng,cultural_tags,dietary_tags,review_status,confidence,area_ids,matched_tags,reason_codes,is_sample,feed_version";

  const pages: PlaceRow[] = [];
  let from = 0;
  let truncated = false;

  while (from < MAX_PLACES) {
    const to = Math.min(from + PAGE_SIZE - 1, MAX_PLACES - 1);
    let query = db
      .from("culture_place_beta_v1")
      .select(selectCols)
      .eq("review_status", "ACCEPTED")
      .order("business_name", { ascending: true })
      .range(from, to);

    if (!allowSample) {
      query = query.eq("is_sample", false);
    }
    if (areaId) {
      query = query.contains("area_ids", [areaId]);
    }

    const { data, error } = await query;
    if (error) {
      console.error("culture places failed", error);
      return new Response(JSON.stringify({ error: "culture_places_unavailable" }), {
        status: 503,
        headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
      });
    }

    const batch = (data ?? []) as PlaceRow[];
    pages.push(...batch);
    if (batch.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
    if (from >= MAX_PLACES) {
      truncated = true;
      break;
    }
  }

  const places = pages.filter((p) => {
    const lat = Number(p.lat);
    const lng = Number(p.lng);
    return lat >= 40.45 && lat <= 40.95 && lng >= -74.3 && lng <= -73.65;
  });

  const body = {
    authority: "supabase:culture_place_beta_v1",
    schema_version: "NYCIF_CULTURE_PLACE_BETA_V1",
    contract: "nycif.culture-places.v1",
    feed_version: places[0]?.feed_version ?? null,
    business_publication_enabled: true,
    place_count: places.length,
    max_places_ceiling: MAX_PLACES,
    truncated,
    note: "ACCEPTED evidence-backed places only (paginated past PostgREST 1000 default; ceiling 5000). Samples require allow_sample_places. Name-leads never appear here.",
    places,
  };

  return new Response(req.method === "HEAD" ? null : JSON.stringify(body), {
    status: 200,
    headers: {
      ...cors,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=120, s-maxage=120, stale-while-revalidate=300",
      "X-Content-Type-Options": "nosniff",
    },
  });
});

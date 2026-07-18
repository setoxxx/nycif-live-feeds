#!/usr/bin/env python3
"""Discovery taxonomy v02 shared helpers — extends schema-v1 without destabilizing it."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from schema_v1_common import (  # noqa: E402
    DEFAULT_TIMEZONE,
    ISO_DATE_PREFIX_RE,
    ISO_DATE_RE,
    NYC,
    REPO_ROOT,
    borough_label,
    is_zero_coord_pair,
    norm_text,
    utc_now,
    write_repo_json,
)

CLASSIFICATION_VERSION = "discovery-taxonomy-v02"
CONTRACT_PATH = REPO_ROOT / "data" / "events_discovery_contract_v02.json"
REGISTRY_PATH = REPO_ROOT / "data" / "nycif_known_recurring_major_events.json"

# Loaded once
_CONTRACT: dict[str, Any] | None = None
_REGISTRY: list[dict[str, Any]] | None = None


def load_contract() -> dict[str, Any]:
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return _CONTRACT


def load_registry() -> list[dict[str, Any]]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return _REGISTRY


def valid_categories() -> set[str]:
    return set(load_contract()["categories"])


def valid_roles() -> set[str]:
    return set(load_contract()["event_roles"])


def valid_significance() -> set[str]:
    return set(load_contract()["significance"])


def valid_dispositions() -> set[str]:
    return set(load_contract()["display_dispositions"])


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "rows", "features", "records"):
            val = payload.get(key)
            if isinstance(val, list):
                if key == "features":
                    out = []
                    for feat in val:
                        if not isinstance(feat, dict):
                            continue
                        props = feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
                        geom = feat.get("geometry") if isinstance(feat.get("geometry"), dict) else {}
                        row = dict(props)
                        row["_geojson_geometry"] = geom
                        out.append(row)
                    return out
                return [r for r in val if isinstance(r, dict)]
    return []


def preserve_date(row: dict[str, Any]) -> str | None:
    for key in ("date", "event_date", "start_date", "date_part"):
        direct = str(row.get(key) or "").strip()[:10]
        if ISO_DATE_RE.fullmatch(direct):
            return direct
    for key in ("start_date_time", "start", "end_date_time"):
        match = ISO_DATE_PREFIX_RE.match(str(row.get(key) or "").strip())
        if match:
            return match.group(1)
    return None


def classification_blob(row: dict[str, Any]) -> str:
    parts = []
    for key in (
        "title",
        "name",
        "event_name",
        "search_label",
        "category",
        "categories",
        "event_type",
        "type",
        "event_agency",
        "agency_name",
        "street_closure_type",
        "description",
        "short_description",
        "location",
        "display_location",
        "intake_type",
    ):
        val = row.get(key)
        if isinstance(val, list):
            parts.extend(str(v) for v in val if v)
        elif val:
            parts.append(str(val))
    return norm_text(" ".join(parts))


def raw_categories(row: dict[str, Any]) -> list[str]:
    cats = row.get("categories")
    if isinstance(cats, list):
        return [str(c) for c in cats if str(c).strip()]
    if isinstance(cats, str) and cats.strip():
        return [cats.strip()]
    if row.get("category") not in (None, ""):
        return [str(row.get("category"))]
    return []


def valid_nyc_coords(lat: Any, lng: Any) -> tuple[float | None, float | None, bool]:
    if lat is None or lng is None or lat == "" or lng == "":
        return None, None, False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, None, False
    if is_zero_coord_pair(lat_f, lng_f):
        return None, None, False
    ok = (
        NYC["min_lat"] <= lat_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lng_f <= NYC["max_lng"]
    )
    if not ok:
        return None, None, False
    return lat_f, lng_f, True


_PERMIT_COORD_RESOLVER: Any = None


def _permit_coord_resolver() -> Any:
    """Lazy read-only GeoSearch cache resolver for permit location text."""
    global _PERMIT_COORD_RESOLVER
    if _PERMIT_COORD_RESOLVER is not False and _PERMIT_COORD_RESOLVER is not None:
        return _PERMIT_COORD_RESOLVER
    try:
        from coverage_gap_utils import resolve_supplemental_coordinates
        from nyc_location_gazetteer import GAZETTEER_PATH, GEOSEARCH_CACHE_PATH, NYCLocationGazetteer
        from nyc_location_resolver import NYCLocationResolver

        if not GAZETTEER_PATH.exists():
            _PERMIT_COORD_RESOLVER = False
            return None
        gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
        cache_payload = json.loads(GEOSEARCH_CACHE_PATH.read_text(encoding="utf-8"))
        entries = cache_payload.get("entries") if isinstance(cache_payload, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        _PERMIT_COORD_RESOLVER = (
            gazetteer,
            NYCLocationResolver(gazetteer, entries, allow_live_geosearch=False),
            resolve_supplemental_coordinates,
        )
    except Exception:
        _PERMIT_COORD_RESOLVER = False
    return _PERMIT_COORD_RESOLVER if _PERMIT_COORD_RESOLVER is not False else None


def resolve_coords(row: dict[str, Any]) -> tuple[float | None, float | None, bool]:
    pairs = [
        (row.get("latitude"), row.get("longitude")),
        (row.get("lat"), row.get("lng")),
        (row.get("proposed_lat"), row.get("proposed_lng")),
    ]
    for lat, lng in pairs:
        lat_f, lng_f, ok = valid_nyc_coords(lat, lng)
        if ok:
            return lat_f, lng_f, True
    display = (
        row.get("location")
        or row.get("event_location")
        or row.get("display_location")
        or row.get("address")
    )
    if not display:
        return None, None, False
    resolver_bundle = _permit_coord_resolver()
    if not resolver_bundle:
        return None, None, False
    gazetteer, resolver, resolve_supplemental_coordinates = resolver_bundle
    fill = resolve_supplemental_coordinates(
        {
            "title": row.get("title") or row.get("event_name") or row.get("name"),
            "display_location": display,
            "address": display,
            "borough": row.get("borough") or row.get("event_borough"),
        },
        gazetteer,
        parks_overlap={},
        resolver=resolver,
        geoclient=None,
        parks_properties_index={},
    )
    if not fill:
        return None, None, False
    lat_f, lng_f, ok = valid_nyc_coords(fill.get("proposed_lat"), fill.get("proposed_lng"))
    if ok:
        return lat_f, lng_f, True
    return None, None, False


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = nested.get("dataset") or row.get("source_dataset") or row.get("intake_type") or "unknown"
    seid = (
        nested.get("source_event_id")
        or row.get("source_event_id")
        or row.get("source_guid")
        or row.get("id")
        or "missing"
    )
    return str(dataset), str(seid)


def stable_canonical_id(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    dataset, seid = source_parts(row)
    day = preserve_date(row) or "undated"
    base = f"{dataset}:{seid}@{day}"
    if data_layer == "review_supplemental" and not base.startswith("review_supplemental:"):
        return f"review_supplemental:{base}"
    if data_layer == "raw_unlinked":
        return f"raw_unlinked:{base}#{index}"
    return base


# --- Classification ---

PROGRAM_OVERRIDES: list[tuple[str, str, list[str], list[str], str]] = [
    # pattern, category, interests, tags, reason
    (
        r"shape up nyc|senior cardio sculpt|strength in motion",
        "fitness",
        ["fitness"],
        ["fitness-class", "parks-program"],
        "high_confidence_program_override_shape_up",
    ),
    (
        r"\bfifa\b|world cup|fan zone|fan festival|fwc2026",
        "sports",
        ["sports"],
        ["fifa", "world-cup"],
        "high_confidence_fifa_world_cup",
    ),
]

KEYWORD_PRIMARY: list[tuple[str, str, str]] = [
    ("jobs", r"job fair|career fair|employment|workforce|hiring", "keyword_jobs"),
    (
        "housing",
        r"\btenant\b|housing ambassador|rent assistance|landlord|homeowner|property owner clinic|hpd housing",
        "keyword_housing",
    ),
    (
        "government",
        r"hearing|public meeting|community board|city council|land-use hearing|government hearing",
        "keyword_government",
    ),
    (
        "volunteer",
        r"volunteer|stewardship|it's my park|community service|park cleanup|tree care|food-distribution volunteer",
        "keyword_volunteer",
    ),
    (
        "tours",
        r"guided tour|walking tour|historical tour|architecture tour|cemetery tour|gallery tour|public-art tour|heritage walk|hart island tour",
        "keyword_tours",
    ),
    (
        "sports",
        r"sport - youth|sport - adult|athletic race|triathlon|duathlon|marathon|\b5k\b|\b10k\b|criterium|softball|baseball|basketball|soccer|football|hockey|tennis|volleyball",
        "keyword_sports",
    ),
    (
        "fitness",
        r"yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|running group|walking group|lap swim",
        "keyword_fitness",
    ),
    (
        "civic",
        r"\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b|\bprocession\b|baraat|block party|open street|feast",
        "keyword_civic",
    ),
    (
        "arts",
        r"movie screening|film|cinema|concert|live music|performance|theater|theatre|gallery|exhibition|comedy|dance performance|summerstage|outdoor movie|ghostbusters|painting|visual art|\bart class\b",
        "keyword_arts",
    ),
    (
        "market",
        r"farmers market|green ?market|street fair|merchandise fair|food festival|vendor fair",
        "keyword_market",
    ),
    (
        "environment",
        r"environment|ecology|climate|compost|recycling|conservation|gardening|nature walk|cleanup",
        "keyword_environment",
    ),
    (
        "parks",
        r"parks? & recreation|\bpark\b|playground|recreation|beach|bowling green|maintenance day",
        "keyword_parks",
    ),
    ("services", r"benefit|resource fair|outreach|health screening|social service|clinic", "keyword_services"),
]

# Official NYC Street Activity Permit types → discovery category.
# Keep this aligned with scripts/build_comprehensive_event_feed.py NYC_TYPE_CATEGORY
# so the map lanes and the coverage report agree. "media" is the film/production/
# press family (operator money-shots lane) that has no home in the older taxonomy.
EVENT_TYPE_MAP = {
    "open culture": ("arts", ["arts"], "event_type_open_culture"),
    "public program/exhibitions": ("arts", ["arts"], "event_type_public_program"),
    "concert": ("arts", ["arts"], "event_type_concert"),
    "single block festival": ("arts", ["arts"], "event_type_single_block_festival"),
    "street festival": ("arts", ["arts"], "event_type_street_festival"),
    "athletic-charitable": ("sports", ["sports"], "event_type_athletic_charitable"),
    "athletic race / tour": ("sports", ["sports"], "event_type_athletic_race"),
    "athletic race/tour": ("sports", ["sports"], "event_type_athletic_race"),
    "marathon": ("sports", ["sports"], "event_type_marathon"),
    "sport - youth": ("sports", ["sports"], "event_type_sport_youth"),
    "sport - adult": ("sports", ["sports"], "event_type_sport_adult"),
    "farmers market": ("market", ["market"], "event_type_farmers_market"),
    "sidewalk sale": ("market", ["market"], "event_type_sidewalk_sale"),
    "block party": ("civic", ["civic"], "event_type_block_party"),
    "parade": ("civic", ["civic"], "event_type_parade"),
    "play streets": ("civic", ["civic"], "event_type_play_streets"),
    "street event": ("civic", ["civic"], "event_type_street_event"),
    "open street partner event": ("civic", ["civic"], "event_type_open_street_partner"),
    "religious event": ("civic", ["civic"], "event_type_religious_event"),
    "rally": ("civic", ["civic"], "event_type_rally"),
    "stationary demonstration": ("civic", ["civic"], "event_type_stationary_demonstration"),
    "clean-up": ("environment", ["environment"], "event_type_clean_up"),
    "health fair": ("services", ["services"], "event_type_health_fair"),
    "mobile unit": ("services", ["services"], "event_type_mobile_unit"),
    "plaza event": ("parks", ["parks"], "event_type_plaza_event"),
    "plaza partner event": ("parks", ["parks"], "event_type_plaza_partner"),
    "dcas prep/shoot/wrap permit": ("media", ["media"], "event_type_dcas_shoot"),
    "press conference": ("media", ["media"], "event_type_press_conference"),
    "production event": ("media", ["media"], "event_type_production_event"),
    "red carpet event": ("media", ["media"], "event_type_red_carpet"),
    "rigging permit": ("media", ["media"], "event_type_rigging"),
    "shooting permit": ("media", ["media"], "event_type_shooting"),
    "theater load in and load outs": ("media", ["media"], "event_type_theater_load"),
}

CATEGORY_ALIASES = {
    "sports": "sports",
    "fitness": "fitness",
    "fitness and wellness": "fitness",
    "parks": "parks",
    "parks and recreation": "parks",
    "parks & recreation": "parks",
    "arts": "arts",
    "arts and culture": "arts",
    "market": "market",
    "markets and fairs": "market",
    "parade": "civic",
    "civic": "civic",
    "education": "education",
    "family": "family",
    "kids and family": "family",
    "volunteer": "volunteer",
    "tours": "tours",
    "government": "government",
    "services": "services",
    "jobs": "jobs",
    "housing": "housing",
    "environment": "environment",
    "media": "media",
    "film": "media",
    "film / production": "media",
    "production": "media",
    "general": "general",
}


def infer_interests(category: str, text: str, tags: list[str]) -> list[str]:
    interests = {category}
    if re.search(r"kids|children|family|storytime|toddler|youth program|all ages|parent and child", text):
        interests.add("family")
    if re.search(r"class|workshop|training|lesson|lecture|book club|learn to|beginner|instruction", text):
        interests.add("education")
    if re.search(r"\bpark\b|playground|outdoors|outdoor", text) and category in {
        "fitness",
        "arts",
        "volunteer",
        "family",
        "education",
    }:
        interests.add("parks")
    if category == "volunteer" and re.search(r"cleanup|environment|tree|nature", text):
        interests.add("environment")
        interests.add("parks")
    if category == "civic" and re.search(r"fair|festival|feast|market|vendor", text):
        interests.add("market")
    if "parks-program" in tags:
        interests.add("parks")
    ordered = [c for c in load_contract()["categories"] if c in interests]
    return ordered or [category]


def infer_tags(category: str, text: str, event_role: str) -> list[str]:
    tags: list[str] = []
    checks = [
        ("running", r"running|5k|10k|marathon"),
        ("outdoor", r"outdoor|outdoors|\bpark\b"),
        ("free", r"\bfree\b"),
        ("kids", r"kids|children|toddler"),
        ("family-friendly", r"family|all ages"),
        ("film", r"movie|film|cinema|screening"),
        ("workshop", r"workshop|class|lesson"),
        ("cleanup", r"cleanup|clean-up"),
        ("fifa", r"fifa|world cup|fwc2026"),
        ("fan-zone", r"fan zone|fan festival"),
        ("transportation", r"bus|shuttle|transportation|loading|staging"),
        ("street-closure", r"street closure|full closure|street closed"),
        ("maintenance", r"maintenance|closed all day|field closed"),
        ("parade", r"parade|procession|march"),
        ("religious", r"religious|feast|mass|baraat"),
        ("fitness-class", r"yoga|zumba|pilates|shape up|cardio|workout"),
    ]
    for tag, pattern in checks:
        if re.search(pattern, text):
            tags.append(tag)
    if event_role != "public_event":
        tags.append(event_role.replace("_", "-"))
    # dedupe preserve order
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def infer_event_role(row: dict[str, Any], text: str) -> tuple[str, str]:
    event_type = norm_text(row.get("event_type") or row.get("type"))
    closure = norm_text(row.get("street_closure_type"))
    public_activation = bool(
        re.search(
            r"\bparade\b|\bmarch\b|festival|feast|fair|concert|ceremony|race|5k|marathon|"
            r"fan zone|fan festival|watch party|block party|procession|rally|vigil",
            text,
        )
        or event_type
        in {
            "parade",
            "farmers market",
            "block party",
            "athletic race / tour",
            "street event",
            "religious event",
            "plaza partner event",
            "plaza event",
            "open street partner event",
            "open culture",
        }
    )
    if re.search(r"maintenance|closed all day|field closed|facility closed", text) and not public_activation:
        return "maintenance_or_closure", "role_maintenance_signal"
    if re.search(
        r"bus operations|shuttle|transportation operation|loading zone|staging area",
        text,
    ) and not re.search(r"fan festival|fan zone|watch party|parade", text):
        return "transportation_operation", "role_transportation_signal"
    if (
        re.search(r"street closure|full closure|curb lane|sidewalk closure", text)
        or closure
        in {
            "full street closure",
            "sidewalk closure",
            "curb lane closure",
        }
    ) and not public_activation:
        return "street_closure", "role_street_closure"
    if re.search(r"private|reservation|reserved|by invitation", text) and not re.search(
        r"public|parade|festival|concert|market", text
    ):
        return "private_or_reserved_activity", "role_private_or_reserved"
    if event_type in {"production event"} and not public_activation:
        return "supporting_permit", "role_production_supporting"
    if re.search(r"permit only|supporting permit", text) and not public_activation:
        return "supporting_permit", "role_explicit_supporting"
    return "public_event", "role_default_public_event"


def _classified(
    *,
    category: str,
    interests: list[str],
    tags: list[str],
    event_role: str,
    reason: str,
    confidence: str,
    raw_category: str | None,
    raw_cats: list[str],
    role_reason: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "interests": interests,
        "tags": tags[:12],
        "event_role": event_role,
        "classification_reason": reason,
        "classification_confidence": confidence,
        "raw_category": raw_category,
        "raw_categories": raw_cats,
        "role_reason": role_reason,
    }


RELIGIOUS_FEAST_PATTERN = (
    r"\bfeast\b|giglio|san gennaro|mount carmel|mt\.?\s*carmel|church feast"
)


def classify_record(row: dict[str, Any]) -> dict[str, Any]:
    text = classification_blob(row)
    raw_cats = raw_categories(row)
    raw_category = raw_cats[0] if raw_cats else None
    event_role, role_reason = infer_event_role(row, text)

    # Religious neighborhood feasts trump generic permit types like Street Festival.
    if re.search(RELIGIOUS_FEAST_PATTERN, text):
        tags = list(
            dict.fromkeys(
                ["religious", "feast", "festival", "annual"] + infer_tags("civic", text, event_role)
            )
        )[:12]
        interests = infer_interests("civic", text, tags)
        for interest in ("civic", "market"):
            if interest not in interests:
                interests.insert(0, interest)
        return _classified(
            category="civic",
            interests=interests,
            tags=tags,
            event_role=event_role,
            reason="high_confidence_religious_feast_before_event_type",
            confidence="high",
            raw_category=raw_category,
            raw_cats=raw_cats,
            role_reason=role_reason,
        )

    # 0 Official NYC permit type wins first.
    # Staged rows often carry a coarse/wrong category (e.g. Production Event
    # labeled "market"), and title overrides like FIFA must not steal film/
    # production permits into sports. Special Event is intentionally absent
    # from EVENT_TYPE_MAP so program/keyword rules still refine those.
    mapped = EVENT_TYPE_MAP.get(norm_text(row.get("event_type") or row.get("type")))
    if mapped:
        cat, interest_seed, reason = mapped
        tags = infer_tags(cat, text, event_role)
        interests = infer_interests(cat, text, tags)
        for interest in interest_seed:
            if interest not in interests:
                interests.insert(0, interest)
        return _classified(
            category=cat,
            interests=interests,
            tags=tags,
            event_role=event_role,
            reason=reason,
            confidence="high",
            raw_category=raw_category,
            raw_cats=raw_cats,
            role_reason=role_reason,
        )

    # 1-4 high confidence program overrides
    for pattern, cat, interests, tags, reason in PROGRAM_OVERRIDES:
        if re.search(pattern, text):
            if cat == "sports" and re.search(r"bus|shuttle|transportation|street closure|loading", text):
                event_role = (
                    "transportation_operation"
                    if re.search(r"bus|shuttle|transportation|loading|staging", text)
                    else "street_closure"
                    if re.search(r"street closure|closure", text)
                    else "supporting_permit"
                )
            interests_final = list(interests)
            if re.search(r"\bpark\b|outdoor", text) and "parks" not in interests_final:
                interests_final.append("parks")
            tags_final = list(tags) + infer_tags(cat, text, event_role)
            return _classified(
                category=cat,
                interests=interests_final,
                tags=tags_final,
                event_role=event_role,
                reason=reason,
                confidence="high",
                raw_category=raw_category,
                raw_cats=raw_cats,
                role_reason=role_reason,
            )

    # 4 high-confidence semantic overrides (before raw source category)
    semantic_overrides = [
        (
            "tours",
            r"guided tour|walking tour|historical tour|architecture tour|cemetery tour|gallery tour|public gallery tour|public-art tour|heritage walk|hart island tour",
            ["tours"],
            [],
            "high_confidence_semantic_tours",
        ),
        (
            "jobs",
            r"job fair|career fair|hiring event|employment fair|workforce event",
            ["jobs"],
            [],
            "high_confidence_semantic_jobs",
        ),
        (
            "housing",
            r"tenant resource fair|housing ambassador|rent assistance|property-owner clinic|landlord clinic|hpd housing|tenant-rights workshop|hpd outreach|housing resources",
            ["housing"],
            [],
            "high_confidence_semantic_housing",
        ),
        (
            "government",
            r"public hearing|community board meeting|city council meeting|agency meeting|government hearing|land-use hearing",
            ["government"],
            [],
            "high_confidence_semantic_government",
        ),
        (
            "volunteer",
            r"\bvolunteer\b|stewardship|it's my park|park cleanup|tree care|food-distribution volunteer",
            ["volunteer"],
            [],
            "high_confidence_semantic_volunteer",
        ),
        (
            "family",
            r"story ?time|kids excursion|children'?s programming|\bkids\b|\bchildren\b|toddler|family day|family program|parent and child",
            ["family"],
            ["kids", "family-friendly"],
            "high_confidence_semantic_family",
        ),
        (
            "education",
            r"bike safety class|\blesson\b|literacy|after[- ]school|homework help|learn to\b|"
            r"(?<!painting )(?<!art )(?<!arts )\bworkshop\b",
            ["education"],
            ["workshop"],
            "high_confidence_semantic_education",
        ),
        (
            "civic",
            r"\bfeast\b|giglio|san gennaro|mount carmel|mt\.?\s*carmel|church feast",
            ["civic", "market"],
            ["religious", "feast", "festival", "annual"],
            "high_confidence_semantic_religious_feast",
        ),
        (
            "arts",
            r"street festival|summerstage|outdoor movie|film festival",
            ["arts"],
            [],
            "high_confidence_semantic_festival_arts",
        ),
    ]
    for cat, pattern, interests, tags, reason in semantic_overrides:
        if re.search(pattern, text):
            tags_final = list(tags) + infer_tags(cat, text, event_role)
            interests_final = infer_interests(cat, text, tags_final)
            for interest in interests:
                if interest not in interests_final:
                    interests_final.insert(0, interest)
            return {
                "category": cat,
                "interests": interests_final,
                "tags": tags_final[:12],
                "event_role": event_role,
                "classification_reason": reason,
                "classification_confidence": "high",
                "raw_category": raw_category,
                "raw_categories": raw_cats,
                "role_reason": role_reason,
            }

    # 5 specific authoritative source category if specific
    # (EVENT_TYPE_MAP already applied at step 0 for known NYC permit types.)
    direct = CATEGORY_ALIASES.get(norm_text(raw_category))
    if direct and direct != "general":
        tags = infer_tags(direct, text, event_role)
        interests = infer_interests(direct, text, tags)
        return _classified(
            category=direct,
            interests=interests,
            tags=tags,
            event_role=event_role,
            reason="authoritative_source_category",
            confidence="medium",
            raw_category=raw_category,
            raw_cats=raw_cats,
            role_reason=role_reason,
        )

    # 6 keyword fallback
    for cat, pattern, reason in KEYWORD_PRIMARY:
        if re.search(pattern, text):
            tags = infer_tags(cat, text, event_role)
            interests = infer_interests(cat, text, tags)
            return _classified(
                category=cat,
                interests=interests,
                tags=tags,
                event_role=event_role,
                reason=reason,
                confidence="medium",
                raw_category=raw_category,
                raw_cats=raw_cats,
                role_reason=role_reason,
            )

    tags = infer_tags("general", text, event_role)
    return _classified(
        category="general",
        interests=["general"],
        tags=tags,
        event_role=event_role,
        reason="fallback_general_no_documented_rule",
        confidence="low",
        raw_category=raw_category,
        raw_cats=raw_cats,
        role_reason=role_reason,
    )


def _registry_title_norm(value: Any) -> str:
    text = norm_text(value)
    return re.sub(r"\bmt\b", "mount", text)


def match_recurring_registry(row: dict[str, Any]) -> tuple[dict[str, Any] | None, int, list[str]]:
    text = classification_blob(row)
    borough = borough_label(row.get("borough") or row.get("event_borough"))
    event_type = norm_text(row.get("event_type") or row.get("type"))
    for entry in load_registry():
        signals = []
        aliases = [_registry_title_norm(a) for a in entry.get("aliases") or []]
        title = _registry_title_norm(
            row.get("title") or row.get("name") or row.get("event_name") or row.get("search_label")
        )
        if any(alias and (alias in title or title in alias) for alias in aliases):
            signals.append("recognized_alias")
        # Alias is mandatory — prevents generic parade/borough false matches.
        if "recognized_alias" not in signals:
            continue
        if entry.get("borough") and borough and norm_text(entry["borough"]) == norm_text(borough):
            signals.append("matching_borough")
        if entry.get("category") and CATEGORY_ALIASES.get(norm_text(row.get("category"))) == entry["category"]:
            signals.append("matching_category")
        if entry.get("category") == "civic" and ("parade" in event_type or "parade" in title):
            signals.append("matching_event_type")
        if entry.get("category") == "sports" and re.search(r"race|marathon|athletic|fifa|world cup", title + " " + event_type):
            signals.append("matching_event_type")
        agency = norm_text(row.get("event_agency") or row.get("agency_name"))
        if agency and entry.get("key") == "fifa-world-cup-fan-festival" and "nypd" in agency:
            signals.append("matching_source_agency")
        need = int(entry.get("minimum_match_signals") or 2)
        if len(signals) >= need:
            return entry, len(signals), signals
    return None, 0, []


def write_json(rel: str, payload: Any) -> None:
    write_repo_json(rel, payload)


def dump_md(rel: str, text: str) -> None:
    path = REPO_ROOT / rel
    if not str(path.resolve()).startswith(str(REPO_ROOT.resolve())):
        raise ValueError("md path escape")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

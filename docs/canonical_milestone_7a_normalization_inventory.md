# Canonical Milestone 7-A: Normalization and Identity Inventory

Milestone: Canonical Milestone 7-A
Baseline SHA: `8796d64ea628007327e715f0995c16e6ab071c78` (Canonical Milestone 6 merge)
Status: complete inventory of every normalization and identity implementation in the repository at the baseline, categorized as **active**, **historical**, or **fixture-only**.

Search basis (executed against the full tree): `def norm(`, `def normalize(`, `def norm_text(`, `def slug(`, `def _clean_text(`, `def group_key(`, `def stable_key(`, `def stable_event_identity(`, `def candidate_keys(`, `def row_location(`, `def event_cemsids(`, `stable_identity_key`, `candidate_identity`, `candidate_identity_key`, `review_rank`.

## A. Active `scripts/` pipeline

### A1. `norm()` — legacy normalization profile (9 bit-identical copies)

| # | File | Line |
|---|---|---|
| 1 | `scripts/build_gps_repository.py` | 60 |
| 2 | `scripts/build_gps_review_groups.py` | 64 |
| 3 | `scripts/build_gps_geocoding_filled_proposals.py` | 64 |
| 4 | `scripts/audit_feed_anomalies.py` | 48 |
| 5 | `scripts/audit_row_disposition.py` | 62 |
| 6 | `scripts/build_location_cache.py` | 50 |
| 7 | `scripts/build_staged_production_feed.py` | 64 |
| 8 | `scripts/build_test_enriched_feed.py` | 115 |
| 9 | `scripts/sync_nyc_open_data.py` | 95 |

Exact algorithm (verified identical in all nine files):

```python
def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
```

- **Case behavior:** Unicode-aware `str.lower()`.
- **Punctuation behavior:** every run of characters outside `[a-z0-9]` becomes one ASCII space.
- **Ampersand behavior:** treated as punctuation — `"A & B"` → `"a b"`.
- **Whitespace behavior:** collapsed by the same punctuation regex; result stripped.
- **Unicode behavior:** lowercased first, then any non-`[a-z0-9]` character (including accented letters like `é`, curly quotes, em-dashes) is replaced by a space — `"Café"` → `"caf"`.
- **Null behavior:** `str(value or "")` — `None`, `""`, `0`, `0.0`, `False`, empty collections all coerce to `""` → result `""`.
- **Non-string behavior:** any other value passes through `str()` — `5` → `"5"`, `True` → `"true"`, `["A","B"]` → `"a b"` (via the list's `str()` form).
- **Separator format:** single space between surviving tokens.
- **Collection ordering:** n/a (string-level function).
- **Fallback precedence:** n/a.
- **Callers:** grouping keys, location-cache candidate keys, fuzzy-join key sets (`proposal_keys()`/`reference_keys()` in `build_gps_geocoding_filled_proposals.py`), disposition/audit matching, feed-building location matching.
- **Persisted output fields:** embedded inside `group_key`, `location:`/`cemsid:`/`text_date_location:` cache keys.
- **Identity-bearing:** yes (via `group_key` and candidate cache keys).
- **Compatibility requirement:** bit-for-bit.
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::normalize_text_legacy`.

### A2. `norm_text()` / `normalize()` — ampersand normalization profile (3 bit-identical copies)

| # | File | Function | Line |
|---|---|---|---|
| 1 | `scripts/build_gps_manual_approval_staging.py` | `norm_text` | 66 |
| 2 | `scripts/generate_gps_staged_feed_integration_match_diagnostic.py` | `normalize` | 65 |
| 3 | `scripts/apply_gps_staged_feed_integration_update.py` | `normalize` | 39 |

Exact algorithm (behaviorally identical in all three; #1 splits the first line in two statements):

```python
text = str(value or "").lower().replace("&", " and ")
text = re.sub(r"[^a-z0-9]+", " ", text)
return re.sub(r"\s+", " ", text).strip()
```

- **Ampersand behavior:** `&` → `" and "` **before** punctuation stripping — `"A & B"` → `"a and b"`. This is the sole behavioral difference from Profile A1.
- **Whitespace behavior:** the trailing `\s+` collapse is redundant after the punctuation regex but present in all three copies; preserved as-is.
- All other behaviors (case, punctuation, Unicode, null, non-string): identical to A1.
- **Callers:** `stable_key()` display fallback; `stable_event_identity()`; fuzzy site/facility matching (`canonical_facility`, `borough_of`) in the staged-feed diagnostic/update scripts.
- **Persisted output fields:** embedded inside `stable_identity_key` (`display:` form) and `stable_event_identity`.
- **Identity-bearing:** yes.
- **Compatibility requirement:** bit-for-bit; must NOT be collapsed with A1 (any `&`-bearing value would change identity).
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::normalize_text_with_ampersand`.

### A3. `group_key(row)` — review-group identity

- **File:** `scripts/build_gps_review_groups.py:105`.
- **Exact algorithm:** `f"{norm(borough(row))}|{norm(location(row))}"` with `borough()` = `str(row.get("borough") or row.get("event_borough") or "").strip()` and `location()` = `str(row.get("display_location") or row.get("location") or row.get("event_location") or "").strip()` — **no `address` fallback**.
- **Separator format:** single `|` between borough and location components; a row with neither yields `"|"`.
- **Fallback precedence:** borough → event_borough; display_location → location → event_location.
- **Callers/consumers:** every artifact from `gps_review_location_groups.json` through `gps_manual_approval_queue.json`, review sheets, and staging; `stable_key()` consumes the persisted `group_key` field.
- **Persisted output field:** `group_key`.
- **Identity-bearing:** yes.
- **Compatibility requirement:** bit-for-bit.
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::build_group_key`.

### A4. `stable_key(row)` — registry-side stable identity

- **File:** `scripts/build_gps_manual_approval_staging.py:73`.
- **Exact algorithm:**

```python
group_key = str(row.get("group_key") or "").strip().lower()
if group_key:
    return f"group:{group_key}"
return f"display:{norm_text(row.get('display_location'))}"
```

- **Case behavior (group branch):** stripped and lowercased but **not** re-normalized — punctuation inside an existing `group_key` survives.
- **Fallback precedence:** persisted `group_key` field, else `display_location` through the ampersand profile; a blank `display_location` yields the literal `"display:"`.
- **Persisted output field:** `stable_identity_key` (this exact field name from this stage onward: reviewed approval artifact, Phase 2E dry-run/readiness, and write-back onto staged events as `promoted_cache_key` → `stable_identity_key`).
- **Identity-bearing:** yes.
- **Compatibility requirement:** bit-for-bit.
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::build_stable_identity_key`.

### A5. `stable_event_identity(row)` — staged-event natural key (2 bit-identical copies)

- **Files:** `scripts/generate_gps_staged_feed_integration_match_diagnostic.py:274` and `scripts/apply_gps_staged_feed_integration_update.py:67` (copy-pasted, not imported — the exact duplication M7-B will remove).
- **Exact algorithm:** pipe-join of five components:
  1. `str(row.get("source_event_id") or row.get("event_id") or row.get("id") or "")` — unnormalized;
  2. `normalize(row_location(row))` — ampersand profile;
  3. `",".join(sorted(event_cemsids(row)))` — sorted, deduplicated (set);
  4. `str(row.get("date") or "")` — **raw**, not reduced to a `YYYY-MM-DD` key;
  5. `str(row.get("start_date_time") or "")`.
- **Supporting accessors (also 2 bit-identical copies each):**
  - `row_location(row)` (`...match_diagnostic.py:87`, `...update.py:54`): `str(display_location or location or event_location or "")` — **no strip, no address fallback**.
  - `event_cemsids(row)` (`...match_diagnostic.py:265`, `...update.py:58`): list → `{str(item) for item in raw if str(item)}` (items **not stripped**); other truthy scalar → one-element set; a comma-separated string is **not split** (unlike A6's `split_ids`).
- **Collection ordering behavior:** input CEMSID list order is irrelevant (sorted set); duplicates collapse.
- **Persisted output field:** `stable_event_identity` (diagnostic → adjudication → update, per `docs/gps_pipeline_data_flow.md`).
- **Identity-bearing:** yes.
- **Compatibility requirement:** bit-for-bit.
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::build_stable_event_identity` (+ `row_location`, `event_cemsids`).

### A6. `candidate_keys(row)` — location-cache candidate keys

- **File:** `scripts/build_gps_repository.py:119`.
- **Exact algorithm:** ordered list of `(key, key_type)` pairs:
  1. `event_id:{source_event_id}` when `str(source_event_id or event_id or "").strip()` is non-blank;
  2. `cemsid:{norm(borough)}:{cemsid}` per `split_ids(source_cemsid or cemsid)` entry, in input order — CEMSID values themselves are **not normalized**; `split_ids` strips list items and comma-splits strings (contrast A5's `event_cemsids`);
  3. `location:{norm(borough)}:{norm(location_text)}` when `location_text` (precedence display_location → location → event_location → **address**, stripped) is non-blank;
  4. `text_date_location:{norm(title_text)}:{norm(borough)}:{norm(location_text)}:{date_key}` only when title (title → event_name → name), location, and `date_key` (leading `YYYY-MM-DD` of date → start_date_time → start) are all non-blank.
- **Fallback precedence:** as itemized above; note the `address` fallback and the `name` title fallback exist **only** in this lineage.
- **Persisted output:** raw dict keys of `data/location_cache.json` entries (plus `key_type`/`key_value` payload fields).
- **Duplicate handling (caller-side, not part of key derivation):** first-writer-wins silent skip in `add_entries()` — the known Milestone 6 gap; **unchanged by M7-A** (duplicate-key enforcement is M7-B/M7-C scope, not authorized here).
- **Identity-bearing:** yes.
- **Compatibility requirement:** bit-for-bit.
- **Category:** active.
- **Shared-helper mapping:** `scripts/gps_identity.py::build_repository_candidate_keys`.

### A7. Transient fuzzy-join key sets (not persisted as identity)

- `proposal_keys()` / `reference_keys()` (`scripts/build_gps_geocoding_filled_proposals.py:96/106`): `{norm(value) for value in values if norm(value)}` over selected row fields — used to join proposals against manual/Parks reference data; results are **not persisted as identity fields**.
- `canonical_facility()` / `site_facility_pairs()` / `same_site()` / `same_facility()` (staged-feed diagnostic): RapidFuzz-based matching built on the A2 profile; produces match decisions, not identity strings.
- **Compatibility requirement:** these remain in their callers; not part of the M7-A helper surface (documented so M7-B knows they exist and are display/matching logic, not identity).
- **Category:** active (matching support).

## B. Historical (`tools/registry/xri_g6`–`xri_g11`)

- **Normalization:** `slug()` (`tools/registry/xri_g7_fixture_candidate_normalizer.py:138`): strip → lower → `[^a-z0-9]+` → `-` → strip `-`; empty result becomes the literal `"missing"`. Dash-separated — distinct from every active profile.
- **Identity:** `candidate_identity_key()` (`xri_g7:158`): SHA-256 over a 5-part pipe-joined basis (`source_dataset_id`, `stable_source_key`, slugged title, slugged event_start, slugged location), truncated to 16 hex chars, formatted `xri-g7:{dataset}:{digest}`. Consumed by `xri_g8`–`xri_g11` fixture prototypes only.
- **Case/punctuation/null behavior:** as `slug()` above; `stable_source_key()` falls back source_record_id → source_location_id → source_category_id → slugged title/location/category.
- **Callers:** `xri_g7`–`xri_g11` only. **No `scripts/` pipeline code reads or writes these keys.**
- **Identity-bearing:** yes, within the historical prototype vocabulary only.
- **Compatibility requirement:** must remain untouched (verified by test group H: golden literal `xri-g7:tvpk-puvk:fd36d36de1a31946` for a fixed record).
- **Category:** historical.
- **M7-A/M7-B disposition:** intentionally separate; never a migration target.

## C. Fixture-only (`tools/registry/xri_g40`–`xri_g44`)

- **Normalization:** `_clean_text()` (`xri_g41:54`, with narrower copies in `xri_g42:33` and `xri_g43:45`): `" ".join(str(value).strip().split())` — whitespace-collapse only; **no case-folding, no punctuation handling**. Materially weaker than every active profile by design (documented in Milestone 6).
- **Identity:** caller-supplied 3-tuple `(group_key, display_location, candidate_identity)` — never derived, never hashed.
- **`review_rank` handling:** tagged `review_rank_identity_use: forbidden_display_only` at parse (`xri_g40`/`xri_g41`); `xri_g42`/`xri_g43` raise at runtime if the tag is missing; unit-tested (`test_xri_g41...::test_review_rank_is_not_identity`).
- **Callers:** `xri_g40`–`xri_g44` and their tests only.
- **Identity-bearing:** yes, within the fixture-only reference vocabulary only.
- **Compatibility requirement:** must remain untouched (verified by test group H: `_clean_text` behavior pinned and shown distinct from both active profiles).
- **Category:** fixture-only.
- **M7-A/M7-B disposition:** intentionally separate; never a migration target.

## D. Duplication and difference findings

1. **Nine bit-identical `norm()` copies** (A1) — pure duplication; M7-B migration target → `normalize_text_legacy`.
2. **Three bit-identical ampersand-profile copies** (A2: one `norm_text`, two `normalize`) — pure duplication; M7-B migration target → `normalize_text_with_ampersand`.
3. **Two bit-identical `stable_event_identity`/`row_location`/`event_cemsids` triples** (A5) — the diagnostic ↔ update copy-paste; M7-B migration target → `build_stable_event_identity`/`row_location`/`event_cemsids`.
4. **A1 vs A2 differ only in ampersand expansion** — must never be collapsed; both are preserved as separate profiles in the helper.
5. **Three distinct location-precedence accessors** exist and must never be merged:
   - grouping (`location()`, A3): display_location → location → event_location, **stripped**, no address;
   - repository (`location_text()`, A6): adds the **address** fallback, stripped;
   - staged-feed (`row_location()`, A5): no address, **not stripped** (whitespace-only stays truthy at the accessor level, unlike A6 where whitespace-only strips to falsy and suppresses the location key).
6. **Two distinct CEMSID readers** exist and must never be merged: `split_ids` (A6 — strips, comma-splits strings, preserves order) vs `event_cemsids` (A5 — no strip, no comma-split, set semantics).
7. **`_clean_text` (C) is intentionally weaker** than the active profiles (no fold, no punctuation strip): a value differing only in case or punctuation is a *different* identity component in the fixture vocabulary but the *same* under every active profile. Intentional; not a defect; not a migration target.
8. **`slug` (B) is dash-separated with a `"missing"` sentinel** — unlike anything active. Intentional; historical only.

## E. `review_rank` and positional-identity survey (verbatim requirement)

- `review_rank` is **created exactly once**: `scripts/build_gps_manual_review_sheet.py:104` (1-based position in a priority-sorted list; the field also appears in that file's CSV column list, line 33).
- **Display-only at every consumer:**
  - `build_gps_manual_approval_staging.py` — matches findings by `norm_text(display_location)` only; carries `review_rank_original_from_findings` as informational; docstring states rank-only findings are not trusted.
  - `xri_g40`/`xri_g41` — tag `review_rank_identity_use: forbidden_display_only`.
  - `xri_g42`/`xri_g43` — raise a `FixtureOnly*Error` if `review_rank` appears without the tag.
  - Tests: `test_xri_g41...::test_review_rank_is_not_identity`, plus Milestone 6's drift suite, plus the new M7-A test group F (`test_review_rank_never_affects_identity`, `test_review_rank_is_never_read` — the recorder proves no helper function even *reads* the key).
- **Row position must never be identity** in: all A3–A6 builders (none read position), the xri_g40–g44 contracts (contractual prohibition), and the latent `recommended_approve_rows`/`do_not_approve_rows` position arrays in `data/gps_manual_approval_review_findings.json` (still written, still **never read** by any consumer — unchanged, deferred M7 follow-up per Milestone 6; positional-array changes are explicitly out of M7-A scope).
- The shared helper takes **no `review_rank` input and no row-position input** by construction.

## F. Bit-for-bit compatibility obligations assumed by `scripts/gps_identity.py`

| Helper function | Preserves (source of truth) | Proven by |
|---|---|---|
| `normalize_text_legacy` | `norm()` ×9 (A1) | test groups A, I (oracle + golden literals) |
| `normalize_text_with_ampersand` | `norm_text()`/`normalize()` ×3 (A2) | test groups A, I |
| `build_group_key` | `group_key()` (A3) | test groups B, I |
| `build_stable_identity_key` | `stable_key()` (A4) | test groups C, I |
| `build_stable_event_identity` | `stable_event_identity()` ×2 (A5) | test groups D, F, I |
| `row_location` | `row_location()` ×2 (A5) | test group D |
| `event_cemsids` | `event_cemsids()` ×2 (A5) | test group D |
| `build_repository_candidate_keys` | `candidate_keys()` (A6) | test groups E, I |

Golden compatibility result at baseline: **0 unexplained identity changes** across the full test matrix (`test_zero_identity_changes_across_full_matrix`).

## G. M7-B migration map (documented, NOT executed in M7-A)

| Target caller | Replaces | With |
|---|---|---|
| `build_gps_repository.py` | local `norm`, `candidate_keys` (+`split_ids`/`date_key`/accessors if promoted) | `normalize_text_legacy`, `build_repository_candidate_keys` |
| `build_gps_review_groups.py` | local `norm`, `group_key` | `normalize_text_legacy`, `build_group_key` |
| `build_gps_geocoding_filled_proposals.py` | local `norm` | `normalize_text_legacy` |
| `build_gps_manual_approval_staging.py` | local `norm_text`, `stable_key` | `normalize_text_with_ampersand`, `build_stable_identity_key` |
| `generate_gps_staged_feed_integration_match_diagnostic.py` | local `normalize`, `row_location`, `event_cemsids`, `stable_event_identity` | helper equivalents |
| `apply_gps_staged_feed_integration_update.py` | local `normalize`, `row_location`, `event_cemsids`, `stable_event_identity` | helper equivalents |
| `audit_feed_anomalies.py`, `audit_row_disposition.py`, `build_location_cache.py`, `build_staged_production_feed.py`, `build_test_enriched_feed.py`, `sync_nyc_open_data.py` | local `norm` | `normalize_text_legacy` |

Each migration must select the **correct profile** per this inventory — the primary hazard called out in the M7-A risk review is a future caller accidentally migrating an A1 call site onto the ampersand profile (or vice versa). The helper docstrings name their source callers explicitly to prevent that.

**Never migration targets:** `tools/registry/xri_g6`–`xri_g11` (historical), `tools/registry/xri_g40`–`xri_g44` (fixture-only), the transient fuzzy-join/matching helpers (A7), and `review_rank`/positional arrays (prohibited as identity everywhere).

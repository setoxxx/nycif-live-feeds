# Source lineage contract v01

Status: protected proposal contract  
Parent gate: `setoxxx/nycif-web-platform#132`  
Public launch gate: `setoxxx/nycif-web-platform#96`

## Purpose

This contract converts the cross-repository source-lineage audit into a durable Enigma operating layer.

The goal is not to add more pins yet. The goal is to make every source, repository, raw record, generated feed, review queue, public output, map pin, list item, and exclusion traceable, fast, tested, and explainable.

## Target operating model

```text
one source record
→ one dated occurrence
→ correct day/time
→ exact location/pin or intentional list-only status
→ correct category
→ duplicate decision
→ public/review/excluded disposition
→ safe generated output
```

## Source registry

The master machine-readable registry is:

```text
data/source_lineage_registry_v01.json
```

Every entry receives explicit fields for:

- repository ownership
- file/source path
- raw-vs-generated status
- review/staging/public eligibility
- occurrence identity requirement
- location/category/dedupe policy
- performance loading role
- national expansion role
- launch gate status
- safety reason code

## Occurrence identity standard

The minimum occurrence key is:

```text
source_namespace + source_dataset_id + source_record_id + normalized_event_date
```

Where available, implementations should also carry:

- normalized start time
- normalized end time
- timezone
- location fingerprint
- recurrence instance key
- source update timestamp

Source-ID-only matching is not allowed for recurring event feeds because it can hide separate dated occurrences.

## Performance contract

Each runtime or output path must be classified as one of:

- `small_boot_feed`
- `major_default_feed`
- `paginated_approved_feed`
- `paginated_review_feed`
- `admin_only_feed`
- `generated_static_feed`
- `live_api_source`
- `offline_batch_source`
- `cache_or_reference`
- `not_for_runtime_load`

This allows Enigma to stay fast by prebuilding heavy outputs, loading small/default feeds first, using page shards for large outputs, and keeping review/admin files out of public runtime paths.

## Safety boundary

This contract does not authorize:

- public `/map/` change
- homepage change
- navigation change
- theme change
- WordPress production page change
- production feed switch
- approval state change
- `data/location_cache.json` write
- deployment, promotion, merge, or launch

Workflow success means the contract audit ran correctly. It does not mean public launch readiness.

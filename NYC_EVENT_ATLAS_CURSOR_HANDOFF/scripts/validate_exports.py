import csv, sys
from nyc_event_atlas.validate import validate_records
with open(sys.argv[1],encoding='utf-8-sig',newline='') as f: records=list(csv.DictReader(f))
errors=validate_records(records)
if errors:
    print('\n'.join(errors[:200])); raise SystemExit(1)
print(f'validation passed: {len(records)} records')

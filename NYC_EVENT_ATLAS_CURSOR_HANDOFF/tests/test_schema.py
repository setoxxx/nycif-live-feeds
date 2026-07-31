from nyc_event_atlas.schema import EXPORT_COLUMNS
def test_schema_length(): assert len(EXPORT_COLUMNS)==59
def test_schema_unique(): assert len(set(EXPORT_COLUMNS))==59

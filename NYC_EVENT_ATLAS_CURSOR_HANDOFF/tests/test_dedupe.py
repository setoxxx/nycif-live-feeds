from nyc_event_atlas.dedupe import occurrence_key, similarity
def row(name='Feast of Example',date='2026-08-20',venue='Main Street',org='Example Society'):
    return {'EVENT_NAME':name,'START_DATE':date,'VENUE':venue,'FULL_ADDRESS':venue,'ORGANIZER':org,'BOROUGH':'Brooklyn','PERMIT_ID':'Unknown','SERIES_ID':'X'}
def test_occurrence_key_stable(): assert occurrence_key(row())==occurrence_key(row(name='Feast  of Example!'))
def test_similarity_high(): assert similarity(row(),row(name='Example Feast'))>75

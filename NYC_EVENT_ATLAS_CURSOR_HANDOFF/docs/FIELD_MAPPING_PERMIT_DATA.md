# Permit Feed to 59-Column Mapping

| Permit field | Export field | Notes |
|---|---|---|
| event_id | PERMIT_ID | Preserve as text |
| event_name | EVENT_NAME | Reject generic routine sports rows unless editorially relevant |
| start_date_time | START_DATE / START_TIME | Usually permit setup window; record caveat |
| end_date_time | END_DATE / END_TIME | Usually breakdown window; record caveat |
| event_agency | PERMIT_AGENCY | Official permitting agency |
| event_type | CATEGORY/SUBCATEGORY | Use controlled mapping |
| event_borough | BOROUGH | Convert Bronx to The Bronx |
| event_location | VENUE/FULL_ADDRESS/STREET fields | Preserve raw text in notes |
| event_street_side | RESEARCH_NOTES | Do not force into route fields |
| street_closure_type | RESEARCH_NOTES | Valuable for photographer access planning |
| community_board | RESEARCH_NOTES/internal field | Consider adding internal column, not export schema |
| police_precinct | RESEARCH_NOTES/internal field | Consider adding internal column |
| cemsid | SERIES_ID candidate/internal external ID | Useful for grouping repeated permit records |

Set `EVENT_STATUS=Permitted` unless a separate official public event page confirms the program. Set `PRIMARY_SOURCE` to the dataset/API URL and add the E-Apply detail page or organizer page as secondary evidence when available.

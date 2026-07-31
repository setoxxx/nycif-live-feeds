# Current Database Audit

Generated from the cumulative CSV supplied with the project.

## Baseline

- 827 rows
- 59 columns
- 409 series
- 786 Confirmed
- 36 Permitted
- 5 TBA

## Borough distribution

- Manhattan: 295
- Queens: 180
- Brooklyn: 178
- Staten Island: 105
- The Bronx: 65
- Citywide: 4

## Largest categories

- Street Fair: 98
- Film Screening: 73
- Community Program: 63
- Bike Event: 51
- Outdoor Concert: 50
- Family Program: 46
- Seasonal Event: 31
- Food Market: 30
- Farmers Market: 29
- Public Market: 25

## Enrichment gaps

- Coordinates unknown: 784 of 827 (94.8%)
- Nearest subway unknown: 720 (87.1%)
- Nearest bus unknown: 783 (94.7%)
- Permit ID unknown: 791 (95.6%)
- Street endpoints unknown: about 76%
- End time unknown: 244 (29.5%)

## Important data-quality observations

1. The database is strongest for public programs and street fairs, but geospatial enrichment is sparse.
2. Manhattan remains overrepresented relative to The Bronx and Staten Island.
3. Source confidence is high for almost every row, but field-level evidence is not represented in the 59-column export; the internal database should add it.
4. Permit ingestion should materially improve closure, precinct, Community Board and permit-ID coverage.
5. Recurrent sources dominate many rows. Incremental source monitoring will produce better results than repeated broad web searches.

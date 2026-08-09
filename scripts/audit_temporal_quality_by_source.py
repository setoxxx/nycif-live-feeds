#!/usr/bin/env python3
"""Account temporal quality by source family without mutating event truth.

This audit accepts common NYCIF payload shapes (list, {events: []}, GeoJSON
{features: []}, or {records: {...}}), classifies every record through
TemporalQualityV1, and emits deterministic source/reason accounting.

It is an audit/reporting tool only. It never repairs times, changes
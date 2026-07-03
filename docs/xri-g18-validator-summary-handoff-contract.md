# XRI-G18 Validator Summary and Handoff Contract

Phase: XRI-G18

Source phase: XRI-G17  
Source pull request: #25  
Source merge commit SHA: `0e9db5255da676a64d17420ca2b418670ea7539b`

Mode: non-production validator summary and handoff gate only.

This contract summarizes XRI-G13 through XRI-G17 and defines safe handoff requirements for future registry or manual-review work. It is documentation/report-only and must not be used by production runtime, public map runtime, registry import, scheduled workflows, WordPress, geocoding, approval, promotion, publishing, or database behavior.

## Summary

- XRI-G13: manual-review schema prototype only.
- XRI-G14: non-production fixture validator contract only.
- XRI-G15: non-production validator execution only.
- XRI-G16: non-production validator failure-case fixtures only.
- XRI-G17: non-production failure-case validator execution only.

All phases remained fixture, prototype, or report-only. No production behavior, registry database/importer, public map runtime, WordPress behavior, scheduled workflow change, location cache access, live staging, SODA/live fetch, geocoding, candidate approval, candidate promotion, or publishing occurred.

## Handoff requirements

Future registry or manual-review work requires a separate explicit prompt and a new non-production contract. Stable identity matching must use `group_key`, `display_location`, and candidate identity, not `review_rank`. Fail-closed validation must continue. Production, geocoding, promotion, publishing, and registry import remain blocked unless explicitly authorized in a later separate gate. Fixture/report artifacts must not be production runtime input and must not publish to public map, WordPress, feeds, or scheduled workflows.

## Hard prohibitions

XRI-G18 must not modify production feeds, public map runtime, WordPress, `nycinfocus.com/map`, iframe/embed settings, scheduled workflows, or `data/location_cache.json`; must not run live staging, fetch SODA/live data, geocode, approve/promote candidates, create registry database/importer behavior, add runtime publishing behavior, publish anything, or start XRI-G19.

## Proposed next gate

XRI-G19 non-production registry implementation planning gate only, after explicit review and merge approval.

## Review gate

Open a pull request only. Do not merge. Do not start XRI-G19.

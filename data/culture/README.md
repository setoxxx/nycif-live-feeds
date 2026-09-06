# Culture community staging

Scaffold outputs only. **Not public. Not promoted.**

- Howard drops `curated_storefronts.csv` here (copy the template). Until then,
  `import_curated_storefronts.py` exits nonzero and invents nothing.
- Pull scripts write `staging/` and `reports/` locally. Do not commit live SODA
  dumps unless a human asks. Tiny fixtures live under `tests/fixtures/culture/`.
- Do not write `location_cache.json` or WordPress from this folder.
- `cuny_career_source_registry.json` is a documented source list, not events.
  Help-calendar pulls write `staging/` only and stay unpublished.

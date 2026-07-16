PYTHON ?= python
bootstrap:
	$(PYTHON) scripts/bootstrap_db.py

test:
	$(PYTHON) -m pytest -q

validate:
	$(PYTHON) scripts/validate_exports.py NYC_EVENTS_MASTER_CUMULATIVE.csv

permits:
	$(PYTHON) scripts/fetch_permits.py --start 2026-07-16 --end 2026-12-31

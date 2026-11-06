# WebTrak scraper tasks. Run from tools/webtrak. Uses only Python standard library.
PYTHON ?= python3

.PHONY: help test monitors range follow serve quality

help:
	@echo "make test       run unit tests (no network calls)"
	@echo "make monitors   list all LCY noise monitors"
	@echo "make range      show available date range and live delay"
	@echo "make follow     follow NMT6 live (~25 min delayed)"
	@echo "make quality    check the saved NMT6 data for gaps and anything that looks wrong"
	@echo "make serve      web app for downloads and statistics (http://127.0.0.1:8765)"
	@echo "python3 -m webtrak fetch --from 'YYYY-MM-DD HH:MM' --to 'YYYY-MM-DD HH:MM'   fetch a past period"

test:
	$(PYTHON) -m unittest discover tests

monitors:
	$(PYTHON) -m webtrak monitors

range:
	$(PYTHON) -m webtrak range

follow:
	$(PYTHON) -m webtrak follow

serve:
	$(PYTHON) -m webtrak serve

quality:
	$(PYTHON) -m webtrak quality

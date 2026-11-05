# Development tasks for the ADS-B tools. Run from tools/adsb. Everything uses only Python's standard library.
PYTHON ?= python3
DEV_LOGS := data/dev-logs

.PHONY: help test demo dev-serve dev-log dev-status dev-analyse

help:
	@echo "make test         run the tests (made-up data only)"
	@echo "make demo         simulate a day, analyse it and write data/demo/results/viewer.html"
	@echo "make dev-serve    run a fake readsb on port 30154, replaying a simulated day at 10x"
	@echo "make dev-log      run the logger against it, writing to $(DEV_LOGS) (in a second terminal)"
	@echo "make dev-status   the site-visit check, on $(DEV_LOGS)"
	@echo "make dev-analyse  analyse $(DEV_LOGS) into data/dev-results"

test:
	$(PYTHON) -m unittest

demo:
	$(PYTHON) -m adsb simulate demo

dev-serve:
	$(PYTHON) -m adsb simulate serve --speed 10

dev-log:
	$(PYTHON) -m adsb log --config site.dev.json

dev-status:
	-$(PYTHON) -m adsb status --log-dir $(DEV_LOGS)

dev-analyse:
	$(PYTHON) -m adsb analyse --config site.dev.json --logs $(DEV_LOGS) --out data/dev-results

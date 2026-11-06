# OpenSky research database (Trino) tasks. Run from tools/opensky. Needs the virtual environment (make setup).
PYTHON ?= .venv/bin/python

.PHONY: help setup test compare viewer

help:
	@echo "make setup     create .venv and install pyopensky"
	@echo "make test      run the tests (made-up data, no network)"
	@echo "make compare FROM=2026-11-05T08:01Z TO=2026-11-05T11:01Z   OpenSky near NMT6 against WebTrak"
	@echo "make viewer FROM=2026-10-28T00:00Z TO=2026-10-29T00:00Z   OpenSky through adsb analyse, and its viewer"

setup:
	python3 -m venv .venv && .venv/bin/pip install pyopensky

test:
	$(PYTHON) -m unittest discover tests

compare:
	$(PYTHON) -m opensky compare --from $(FROM) --to $(TO) $(ARGS)

# OpenSky positions as logger files, analysed by tools/adsb with NMT6 as the site. DIR defaults to data/<FROM's date>.
DIR ?= data/$(firstword $(subst T, ,$(FROM)))
viewer:
	$(PYTHON) -m opensky logs --from $(FROM) --to $(TO) --out $(DIR)/adsb --replace
	cd ../adsb && python3 -m adsb metars --from $(FROM) --to $(TO) --out ../opensky/$(DIR)/eglc_metars.csv
	cd ../adsb && python3 -m adsb analyse --config ../opensky/nmt6-site.json --logs ../opensky/$(DIR)/adsb --out ../opensky/$(DIR)/results --weather ../opensky/$(DIR)/eglc_metars.csv --all-positions
	@echo "open $(DIR)/results/viewer.html"

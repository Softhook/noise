# OpenSky research database (Trino) tasks. Run from tools/opensky. Needs the virtual environment (make setup).
PYTHON ?= .venv/bin/python

.PHONY: help setup test compare

help:
	@echo "make setup     create .venv and install pyopensky"
	@echo "make test      run the tests (made-up data, no network)"
	@echo "make compare FROM=2026-11-05T08:01Z TO=2026-11-05T11:01Z   OpenSky near NMT6 against WebTrak"

setup:
	python3 -m venv .venv && .venv/bin/pip install pyopensky

test:
	$(PYTHON) -m unittest discover tests

compare:
	$(PYTHON) -m opensky compare --from $(FROM) --to $(TO) $(ARGS)

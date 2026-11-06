# Survey tasks. Run from tools/survey. Standard library only.
PYTHON ?= python3

.PHONY: help test build serve

help:
	@echo "make serve                     the survey app at http://127.0.0.1:8766"
	@echo "make build DEPLOYMENT=2026-11-05   build one deployment's common tables"
	@echo "make build                     build every deployment in ../deployments"
	@echo "make test                      run the tests (made-up data, no network)"

test:
	$(PYTHON) -m unittest discover tests

build:
ifdef DEPLOYMENT
	$(PYTHON) -m survey build --manifest ../deployments/$(DEPLOYMENT).json
else
	for m in ../deployments/*.json; do $(PYTHON) -m survey build --manifest $$m || exit 1; done
endif

serve:
	$(PYTHON) -m survey serve

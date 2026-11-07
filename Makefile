# The noise survey's tasks, from the top of the repository. `make setup` once, then `make help`.
# Everything runs in .venv through the `noise` command (tools/noise/cli.py).

# The Python the environment is made with: 3.11 or later (3.9, macOS's own, is past its end of life)
PYTHON_FOR_VENV ?= python3.12
PYTHON := $(abspath .venv/bin/python)
NOISE := $(abspath .venv/bin/noise)
# All the data: raw/ (as collected or downloaded, written once) and derived/ (rebuildable).
# Set NOISE_DATA to keep it elsewhere, such as an external disk; every tool follows it.
export NOISE_DATA ?= $(CURDIR)/data
RAW := $(NOISE_DATA)/raw
DERIVED := $(NOISE_DATA)/derived

# The Pi, as ssh knows it: adsb-pi.local at home, or 10.42.0.1 on its own hotspot at the garden.
# Add a user if it isn't your laptop's, e.g. make pi-status PI=pi@10.42.0.1
PI ?= adsb-pi.local
SSH := ssh -o ConnectTimeout=10
COLLECT_DIR ?= $(RAW)/adsb/garden
ADSB := tools/adsb

# A period for opensky and opensky-compare, e.g. FROM=2026-11-05T00:00Z TO=2026-11-06T00:00Z
DAY = $(firstword $(subst T, ,$(FROM)))

.PHONY: help setup lock print-data test build serve fleet webtrak webtrak-follow webtrak-quality opensky opensky-compare \
	demo dev-serve dev-log dev-status dev-analyse pi-deploy pi-status pi-journal pi-config pi-collect pi-ssh

help:
	@echo "make setup                 create .venv and install the tools (the noise command), with pyopensky"
	@echo "make lock                  after changing a dependency: record the exact versions in requirements.lock"
	@echo "make test                  every tool's tests (made-up data, no network)"
	@echo
	@echo "The survey (tools/survey):"
	@echo "make build                 analyse what's out of date and build every deployment; DEPLOYMENT=2026-11-05 for one"
	@echo "make serve                 the survey app at http://127.0.0.1:8766"
	@echo "make fleet                 look up new aircraft types in the official registers (online)"
	@echo
	@echo "Getting data (into $(RAW)):"
	@echo "make opensky FROM=2026-11-05T00:00Z TO=2026-11-06T00:00Z   OpenSky's positions and EGLC's METARs for a period (REPLACE=1 to fetch again)"
	@echo "make opensky-compare FROM=... TO=...                       OpenSky near NMT6 against WebTrak"
	@echo "make webtrak               WebTrak's download app at http://127.0.0.1:8765"
	@echo "make webtrak-follow        follow NMT6 live (about 25 minutes behind)"
	@echo "make webtrak-quality       check the saved NMT6 data for gaps and anything that looks wrong"
	@echo
	@echo "The ADS-B logger on a laptop (into $(DERIVED)/adsb):"
	@echo "make demo                  simulate a day, analyse it, and write demo/results/viewer.html"
	@echo "make dev-serve             a fake readsb on port 30154, replaying a simulated day at 10x"
	@echo "make dev-log               the logger against it, writing dev-logs (in a second terminal)"
	@echo "make dev-status            the site-visit check, on dev-logs"
	@echo "make dev-analyse           analyse dev-logs into dev-results"
	@echo
	@echo "On the Pi, from this laptop (PI=$(PI); see tools/adsb/docs/pi-setup.md):"
	@echo "make pi-deploy             copy the code to the Pi and install or update it; ARGS=\"--watchdog --gps --hotspot\" at home, \"--graphs\" for the trial"
	@echo "make pi-status             the site-visit check, and the logger's latest journal lines"
	@echo "make pi-journal            follow the logger's journal; Ctrl-C to stop"
	@echo "make pi-config             edit the Pi's site.json, then turn on and restart the logger"
	@echo "make pi-collect            copy the finished logs to $(COLLECT_DIR) and check their checksums"
	@echo "make pi-ssh                a shell on the Pi"

# An editable install, so the code in tools/ runs where it is (the tools find data/ and the
# deployments from there), with the exact versions in requirements.lock
setup:
	@command -v $(PYTHON_FOR_VENV) >/dev/null || { echo "$(PYTHON_FOR_VENV) not found: brew install python@3.12, or make setup PYTHON_FOR_VENV=python3.11"; exit 1; }
	rm -rf .venv
	$(PYTHON_FOR_VENV) -m venv .venv
	.venv/bin/pip install --quiet --upgrade pip
	.venv/bin/pip install --quiet -c requirements.lock -e ".[opensky]"
	@echo "Installed: .venv/bin/noise (or activate .venv and run noise)"

lock:
	.venv/bin/pip install --quiet -e ".[opensky]"
	.venv/bin/pip freeze --exclude-editable | grep -v "^pip==" > requirements.lock
	@echo "requirements.lock updated; commit it"

# The data folder every tool uses (tested by tools/noise/tests)
print-data:
	@echo $(NOISE_DATA)

# Each tool's tests run from its own folder, as they always have
test:
	cd tools/adsb && $(PYTHON) -m unittest
	cd tools/webtrak && $(PYTHON) -m unittest discover tests
	cd tools/opensky && $(PYTHON) -m unittest discover tests
	cd tools/survey && $(PYTHON) -m unittest discover tests
	cd tools/fusion && $(PYTHON) -m unittest discover tests
	cd tools/noise && $(PYTHON) -m unittest discover tests

# --- the survey ---------------------------------------------------------------------------

build:
	$(NOISE) build $(DEPLOYMENT)

serve:
	$(NOISE) serve

fleet:
	$(NOISE) fleet

# --- getting data -------------------------------------------------------------------------

# OpenSky's positions as logger files, and the METARs that correct their heights. A deployment's
# manifest then names them, and `make build` analyses them.
# Raw data isn't overwritten: a period already fetched is refused, unless REPLACE=1.
opensky:
	@[ -n "$(FROM)" ] && [ -n "$(TO)" ] || { echo "give FROM and TO, e.g. make opensky FROM=2026-11-05T00:00Z TO=2026-11-06T00:00Z"; exit 2; }
	@if [ -z "$(REPLACE)" ] && ls $(RAW)/opensky/$(DAY)/*.jsonl.gz >/dev/null 2>&1; then \
		echo "$(RAW)/opensky/$(DAY) is already fetched; REPLACE=1 to fetch it again"; exit 1; fi
	$(NOISE) opensky logs --from $(FROM) --to $(TO) --out $(RAW)/opensky/$(DAY) $(if $(REPLACE),--replace)
	@if [ -z "$(REPLACE)" ] && [ -e $(RAW)/metars/eglc-$(DAY).csv ]; then echo "keeping $(RAW)/metars/eglc-$(DAY).csv"; \
	else $(NOISE) adsb metars --from $(FROM) --to $(TO) --out $(RAW)/metars/eglc-$(DAY).csv; fi

opensky-compare:
	$(NOISE) opensky compare --from $(FROM) --to $(TO) $(ARGS)

webtrak:
	$(NOISE) webtrak serve

webtrak-follow:
	$(NOISE) webtrak follow

webtrak-quality:
	$(NOISE) webtrak quality

# --- the ADS-B logger on a laptop ---------------------------------------------------------

demo:
	$(NOISE) adsb simulate demo --out $(DERIVED)/adsb/demo

dev-serve:
	$(NOISE) adsb simulate serve --speed 10

# site.dev.json gives the logger's log_dir, data/derived/adsb/dev-logs, relative to tools/adsb
dev-log:
	cd $(ADSB) && $(NOISE) adsb log --config site.dev.json

dev-status:
	-$(NOISE) adsb status --log-dir $(DERIVED)/adsb/dev-logs

dev-analyse:
	$(NOISE) adsb analyse --config $(ADSB)/site.dev.json --logs $(DERIVED)/adsb/dev-logs --out $(DERIVED)/adsb/dev-results

# --- the Pi -------------------------------------------------------------------------------

# Copies only the code, never site.json or logs, so the Pi needs no git or internet to update
pi-deploy:
	rsync -a --delete --exclude __pycache__ --exclude .DS_Store -e "$(SSH)" \
		$(ADSB)/adsb $(ADSB)/deploy $(ADSB)/site.example.json $(PI):adsb-deploy/
	$(SSH) -t $(PI) sudo sh adsb-deploy/deploy/install.sh $(ARGS)

pi-status:
	-$(SSH) -t $(PI) 'adsb status; echo; echo "Logger journal:"; \
		journalctl -u adsb-logger -n 15 --no-pager --output short-iso'

pi-journal:
	$(SSH) -t $(PI) journalctl -u adsb-logger -f

pi-config:
	$(SSH) -t $(PI) 'sudoedit /etc/adsb-logger/site.json && sudo systemctl enable adsb-logger \
		&& sudo systemctl restart adsb-logger \
		&& sleep 5 && journalctl -u adsb-logger -n 5 --no-pager --output short-iso'

pi-collect:
	SSH="$(SSH)" sh $(ADSB)/deploy/collect.sh $(PI) $(COLLECT_DIR)

pi-ssh:
	$(SSH) $(PI)

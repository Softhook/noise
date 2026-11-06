# Development tasks for the ADS-B tools. Run from tools/adsb. Everything uses only Python's standard library.
PYTHON ?= python3
DEV_LOGS := data/dev-logs

# The Pi, as ssh knows it: adsb-pi.local at home, or 10.42.0.1 on its own hotspot at the garden.
# Add a user if it isn't your laptop's, e.g. make pi-status PI=pi@10.42.0.1
PI ?= adsb-pi.local
COLLECT_DIR ?= data/collected
SSH := ssh -o ConnectTimeout=10

.PHONY: help test demo dev-serve dev-log dev-status dev-analyse \
	pi-deploy pi-status pi-journal pi-config pi-collect pi-ssh

help:
	@echo "make test         run the tests (made-up data only)"
	@echo "make demo         simulate a day, analyse it and write data/demo/results/viewer.html"
	@echo "make dev-serve    run a fake readsb on port 30154, replaying a simulated day at 10x"
	@echo "make dev-log      run the logger against it, writing to $(DEV_LOGS) (in a second terminal)"
	@echo "make dev-status   the site-visit check, on $(DEV_LOGS)"
	@echo "make dev-analyse  analyse $(DEV_LOGS) into data/dev-results"
	@echo
	@echo "On the Pi, from this laptop (PI=$(PI); see docs/pi-setup.md):"
	@echo "make pi-deploy     copy the code to the Pi and install or update it; ARGS=\"--gps --hotspot\" at home"
	@echo "make pi-status     the site-visit check, and the logger's latest journal lines"
	@echo "make pi-journal    follow the logger's journal; Ctrl-C to stop"
	@echo "make pi-config     edit the Pi's site.json, then restart the logger"
	@echo "make pi-collect    copy the finished logs to data/collected/ and check their checksums"
	@echo "make pi-ssh        a shell on the Pi"

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

# Copies only the code, never site.json or logs, so the Pi needs no git or internet to update
pi-deploy:
	rsync -a --delete --exclude __pycache__ --exclude .DS_Store -e "$(SSH)" \
		adsb deploy site.example.json $(PI):adsb-deploy/
	$(SSH) -t $(PI) sudo sh adsb-deploy/deploy/install.sh $(ARGS)

pi-status:
	-$(SSH) -t $(PI) 'adsb status; echo; echo "Logger journal:"; \
		journalctl -u adsb-logger -n 15 --no-pager --output short-iso'

pi-journal:
	$(SSH) -t $(PI) journalctl -u adsb-logger -f

pi-config:
	$(SSH) -t $(PI) 'sudoedit /etc/adsb-logger/site.json && sudo systemctl restart adsb-logger \
		&& sleep 5 && journalctl -u adsb-logger -n 5 --no-pager --output short-iso'

pi-collect:
	SSH="$(SSH)" sh deploy/collect.sh $(PI) $(COLLECT_DIR)

pi-ssh:
	$(SSH) $(PI)

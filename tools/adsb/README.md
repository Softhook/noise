# ADS-B flight logger for the Thamesmead noise survey

A Raspberry Pi records every aircraft near the Thamesmead garden. Its log lets us match each noise event from the Acoem Fusion to an aircraft's identity, type, track and height, as the [measurement plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md) requires.

The Pi logs locally, and its clock is set by a USB GPS receiver. Data is collected from it by hand, and nothing is sent to a flight-tracking network or other online service.

**Status:** the logger, analysis, simulator and viewer are written and pass their tests, but only on simulated data. Nothing has been run on the Pi or on real ADS-B data yet. See the [build plan](docs/PLAN.md).

## How it works

```text
On the Pi:
Antenna -> Pro Stick Plus -> readsb --(JSON stream, TCP)--> adsb log -> hourly .jsonl.gz files
                                |                              |
                                +--> tar1090 (live map)         +--> health log every 5 minutes
                                                                    +--> status page every minute (http://<pi>/adsb-status/)
USB GPS -> gpsd -> chrony (sets the Pi's clock)                 adsb status reads it on site visits

Afterwards, on a laptop:
logs + EGLC METARs -> adsb analyse -> flights.csv, positions.csv, summary.txt, viewer.html
```

Everything is one Python package, `adsb`, with one command line. On the laptop it's part of the survey's project, so after `make setup` (at the top of the repository) it's `noise adsb ...`, from any folder:

```bash
adsb log       --config site.json      # on the Pi, run by systemd
adsb status                             # on the Pi, on each site visit
noise adsb analyse   --config site.json --logs LOGS --out RESULTS --weather eglc.csv
noise adsb metars    --from 2026-11-05 --to 2026-11-06 --out data/raw/metars/eglc-2026-11-05.csv
noise adsb simulate  demo | logs | serve
noise adsb traces    --config site.json --out OUT --source NAME INPUT...   # readsb track files to logs
```

You rarely need `analyse` by hand: `make build` runs it on each deployment's ADS-B sources, from their raw logs, whenever they've changed. On the Pi, `deploy/install.sh` installs everything and a plain `adsb` command; see [Setting up the Pi](docs/pi-setup.md). The Pi gets only this package, which uses only the standard library.

The Pi runs headless, and it's run from a laptop, with `make` at the top of the repository. At the garden, the laptop joins the Pi's own Wi-Fi hotspot and uses `PI=10.42.0.1`:

```bash
make pi-deploy     # copy the code to the Pi and install or update it
make pi-status     # the site-visit check
make pi-config     # edit the Pi's site.json
make pi-collect    # copy the finished logs to data/raw/adsb/garden/ and check their checksums
```

## Layout

```text
tools/adsb/
  adsb/                    the package
    __main__.py            the command line; loads each command's module only when it's used
    logger.py        Pi    saves readsb's stream to hourly files, and writes the health log
    status.py        Pi    the site-visit check
    health.py        Pi    reads the health log: clock synchronisation, events, gaps
    geometry.py      Pi    positions relative to the garden, closest-approach maths
    analyse.py             runs the analysis and writes the outputs
    logs.py                finds and reads the hourly log files, including damaged ones
    tracks.py              log records -> positions -> flights
    weather.py             QNH and temperature by time, from METARs or a CSV
    atmosphere.py          QNH and geometric heights, speed of sound
    flight.py              one flight: height source, closest approach, sound delay, path angle, label
    viewer.py              writes viewer.html from viewer_template.html
    common.py              units, numbers and UTC times
    simulate.py            a simulated day with known answers, and a fake readsb
    traces.py              readsb track files (adsb.lol's archive) to hourly log files
  tests/                   unittest tests, on made-up data only
  deploy/                  install script, systemd units and the `adsb` wrapper for the Pi; collect.sh for the laptop
  docs/                    plan, Pi setup, log format, analysis method, the simulated day
  site.example.json        config template; the location is a placeholder, and site.name is what outputs call it
  site.dev.json            config for running the logger on a laptop against the simulator
```

Modules marked **Pi** run on the Raspberry Pi. They must import only the standard library and each other, never the analysis modules, so the Pi needs nothing installed and can't be broken by analysis changes.

## Development

On the Pi it needs Python 3.9 or later and nothing else: all the code uses only the standard library. On the laptop it runs in the project's environment (Python 3.12, `make setup`). The tasks are in the Makefile at the top of the repository (`make help`), and run from there:

```bash
make test          # every tool's tests; this one's take about 4 s
make demo          # simulate a day, analyse it, write data/derived/adsb/demo/results/viewer.html
open data/derived/adsb/demo/results/viewer.html
```

To run the real logger on a laptop, use two terminals:

```bash
make dev-serve     # a fake readsb on port 30154, replaying a simulated day at 10x
make dev-log       # the logger, writing to data/derived/adsb/dev-logs; Ctrl-C to stop
make dev-status    # the site-visit check on those logs
make dev-analyse   # analyse them into data/derived/adsb/dev-results
```

On a laptop, `adsb status` always warns that the clock isn't known to be synchronised, because `chronyc` isn't there.

The tests can also be run on their own, from `tools/adsb`, with `python3 -m unittest`. What the logger collects at the garden is raw data (`data/raw/adsb/garden/`); the demo and dev runs are derived (`data/derived/adsb/`). Git ignores both.

Conventions:

- **Standard library only**, like `tools/fusion`.
- **Logs are only ever read** after the logger writes them. The analysis and simulator never change an input file, and the simulator only replaces a folder it made itself.
- **UTC throughout**, as Unix seconds inside the code and ISO 8601 with `Z` in outputs.
- **Settings** have defaults in `logger.DEFAULTS` and `analyse.DEFAULTS`. The `logger` and `analysis` sections of the config override them.
- **Test against known answers.** The simulator writes `truth.csv`, and `tests/test_simulate.py` checks that the analysis recovers it. Add a quirk to the simulator when real data shows a new kind of fault.

## Documentation

- [Build plan](docs/PLAN.md): requirements, hardware, decisions, build order, risks and open questions
- [Setting up the Pi](docs/pi-setup.md): readsb, the GPS clock, installing the logger and site visits
- [What gets logged](docs/logs.md): log files, the health log and the ADS-B fields we use
- [Analysing the logs](docs/analysis.md): weather data, outputs, how each value is worked out, and the viewer
- [The simulated day](docs/simulation.md): what it contains and how accurately the analysis recovers it
- [adsb.lol's archive](docs/traces.md): other receivers' tracks, as a cross-check on coverage and the clock

## Keep out of this repository

This repository is public. Never commit:

- the garden's coordinates, including in config files, sample logs or screenshots
- flight logs or analysis results

`.gitignore` excludes `site.json` and the `logs/` and `results/` folders in `tools/adsb`, and all of `data/` at the top of the repository, where the collected logs go. Anything published should be summarised, and shouldn't identify individual private aircraft.

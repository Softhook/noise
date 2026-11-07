# Aircraft noise at Thamesmead

Two things live here:

- **The London City approach noise model:** a web page (`index.html`, `js/`, `style.css`, with `p5.js`). Open `index.html` in a browser. Its tests are in `tests/`.
- **The noise survey's tools** (`tools/`): they collect aircraft tracks and noise levels near NMT6 and the garden, and join them in the survey app. The rest of this README is about them.

## Getting started

Needs Python 3.11 or later; `make setup` uses 3.12 (`brew install python@3.12`). The Pi needs only its own Python.

```bash
make setup     # once: .venv, with the noise command and pyopensky
make test      # every tool's tests (made-up data, no network)
make build     # analyse what's out of date, then build every deployment
make serve     # the survey app, at http://127.0.0.1:8766
make help      # everything else: fetching data, the ADS-B logger and the Pi
make lock      # after changing a dependency: pin the exact versions in requirements.lock
```

`make` runs everything through `noise`, a single command for all the tools: `noise build`, `noise serve`, `noise fleet` and `noise sql` for the survey, and `noise adsb ...`, `noise opensky ...`, `noise webtrak ...` or `noise fusion ...` for each tool's own commands. Activate `.venv` (`source .venv/bin/activate`) to run `noise` from any folder.

## Layout

```text
pyproject.toml, Makefile   one project, one environment, one command
tools/
  survey/                  the survey app and build: deployments, linking, aircraft types (the main app)
  adsb/                    the garden's ADS-B logger (runs on the Pi), and the analysis of its logs
  opensky/                 OpenSky's research database, for any period
  webtrak/                 London City's WebTrak: NMT6's levels and the airport's radar
  fusion/                  looking inside the Fusion noise meter's files (noise fusion)
  noise/                   the noise command
data/                      all the data, git-ignored (or wherever NOISE_DATA says)
```

Each tool is its own package, and all but `fusion` have a README. The Pi gets only `tools/adsb`, which uses only Python's standard library. So does everything else, except OpenSky's client, pyopensky.

## The data

Every tool writes into `data/` (or `NOISE_DATA`), never into its own folder: `raw/` for what's fetched (`make pi-collect`, `make opensky`, `make webtrak`), `derived/` for what `make build` works out from it. A period is a deployment, a manifest in [`tools/survey/deployments/`](tools/survey/deployments). The layout and the rules are in [tools/survey/README.md](tools/survey/README.md#where-the-data-lives), and the design in [tools/survey/ARCHITECTURE.md](tools/survey/ARCHITECTURE.md).

Where the work stands, what's waiting on a decision and what's next are in [PROGRESS.md](PROGRESS.md).

The data stays private: the garden's location (`tools/adsb/site.json`, git-ignored) and OpenSky's data under its research terms. Publish only summaries.

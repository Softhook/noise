# Survey: every source in one place

The survey app shows what each source saw on a day, on one page:
- the garden's ADS-B logger
- OpenSky
- WebTrak's radar and NMT6's noise levels
- later, the Fusion

It lays out the tracks, heights and noise around a chosen receptor (NMT6, or the garden), and links the same aircraft across sources. The design is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Status

Part of Phase 0 is built: the manifest, the common tables, the `adsb` and `webtrak` adapters, closest approaches, `link`, the fleet registry with its register lookups (`noise fleet`), the first part of `resolve`, and the survey app (`noise serve`), which shows every source together. `checks`, `match`, the rest of `resolve` and the other lookups are still to do. OpenSky now stands in for the Pi until the Pi has real data. The design, including the parts still to build, is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Viewing a day

From the top of the repository (`make setup` once first):

```bash
make build      # once, and again after fetching more data: analyses what changed, then builds
make serve      # opens http://127.0.0.1:8766
```

Pick a **deployment** and **day**, a **receptor**, and which **sources** to show, in the row at the top. The page then shows:

- **The day at the receptor:** a lane per source, shaded where it has data, with a tick at each pass's closest approach. Under the lanes is the receptor's 1 s sound level, with each noise event's LAmax. Scroll to zoom in time (down to a minute), Shift-scroll or Shift-drag to pan, and double-click for the whole day. Drag across it to choose a time window, which everything below then shows; **Zoom to window** fits the timeline to it. Click a tick to select its pass.
- **Tracks** and **height profile:** scroll to zoom, drag to pan, double-click to reset. Each source has its own colour, and radar tracks are dashed. Clicking a track selects that pass in every source.
- **By aircraft type:** the measure chosen (path angle, ground distance, height or slant distance at the closest approach, or the pass's LAmax), as in the ADS-B viewer, with a row per type and a lane per source in each row, so the sources can be compared type by type. A dot per flight, and a tick at each lane's median. A pass's row is the type its highest-ranked source gives, so it doesn't move when sources disagree. Path angle is fitted to height against distance 3 km either side of the closest approach, as `adsb analyse` does, but for every source, and is signed (negative descending), since departures and arrivals share the page; the 5.5° ILS and 4.49° RNP-AR angles are marked when anything is descending. A hollow dot is at an edge of its source's data, and is left out of the median. It follows the filters and the time window; click a dot to select its pass. The ADS-B viewer's sound delay and QNH-minus-geometric height aren't here: they need the weather and ADS-B-only fields that the common tables don't have.
- **Passes:** one row per aircraft movement that came within the chosen distance of the receptor (3 km to start with), and below the chosen height (3,000 ft), in any source, with each source's distance and height at its closest approach, the height difference between the sources, and the loudest noise event from 5 s before to 40 s after the pass (sound takes a few seconds to arrive, and the clocks may differ a little). An event goes to only one pass: if two passes fall in its time, it goes to the one that came closer to the receptor. That's a guide, not a match: matching events to passes properly is `match`'s job, which is still to be built. A grey value means the closest point was at an edge of that source's data, so the aircraft may have come closer where the source has no positions. The edge is the end of its track (at the edge of OpenSky's box, or when WebTrak's saved data starts or ends mid-pass), or either side of a gap of over 30 s in it. A track is never drawn as a straight line across such a gap when working out the closest approach.
- **Why a source missed a pass:** where a source has no flight in a pass, the table says why. *No data then*, *outside its area* and *above its ceiling* mean it couldn't have seen it. **Missed** means it should have: it had data then, and the aircraft spent at least 20 s inside its area and below its ceiling. That's a gap in its data, or a pass that wasn't linked, and worth looking at. The **Missed, unexplained** tile counts these, and **Unexplained misses only** lists just them.
  - For the ADS-B-family sources, the area is `adsb analyse`'s 15 km around its site, plus the box in the logs' `SOURCE.txt` if they were cut to one (OpenSky's 5 km box around NMT6). The ceiling is `adsb analyse`'s 10,000 ft. Give `max_km` or `ceiling_ft` in the manifest's source entry if its analysis used others.
  - For WebTrak, the area is `max_km` around any receptor, at any height.
  - *When* a source has data comes from the period in `SOURCE.txt`, for OpenSky and adsb.lol. For the garden's logger, it comes from its health log (give `logs` in the manifest), which shows each 5 minutes it was running, connected, receiving and with its clock synchronised. Without a health log, it's `adsb analyse`'s time covered, less its gaps of over 30 minutes. A shorter outage can then look like a miss.

The app only listens on this computer, and only reads built deployments. **Rebuild** on the page reruns the build after you've fetched more data. It runs in the background, since it may analyse logs for minutes, and the page shows its progress and, if it fails, why. A build that `make build` is already running is left to finish.

## Where the data lives

Every tool keeps its data in one local folder, `data/` at the top of the repository, which git ignores. It belongs to no tool, the survey included: the tools stay separate programs, and the survey reads the data from there like any other. To keep it somewhere else, such as an external disk once the WebTrak cache and adsb.lol days grow, set `NOISE_DATA` to that folder; every tool, the Makefile and the Pi's collect script follow it.

This is the one description of it; the other READMEs point here. It's split by one rule. **`raw/`** is what was collected or downloaded, kept as it came. Nothing overwrites it: `make opensky` refuses a period already fetched unless you give `REPLACE=1`, and `make pi-collect` never overwrites a file it has collected. adsb.lol's day archive is converted to hourly logs and then deleted, so those logs are kept in `raw/` as its record. **`derived/`** is everything worked out from it, which can be deleted and made again with `make build` (and, for the demo and WebTrak's per-monitor files, their own commands).

```text
data/
├── raw/
│   ├── adsb/garden/          the garden logger's logs, as collected from the Pi (make pi-collect)
│   ├── adsblol/<day>/        adsb.lol days, converted to hourly logs by adsb traces
│   ├── opensky/<period>/     OpenSky's positions as hourly logs (make opensky), and aircraft-db/
│   ├── metars/               EGLC's METARs, a file per period (make opensky, or adsb metars)
│   └── webtrak/lcy/          WebTrak's chunks, by UTC day, and its monitor list
└── derived/
    ├── deployments/<name>/   a deployment's build: analysis/<source>/ (adsb analyse, and its viewer.html),
    │                         common/ (the tables), build.json
    ├── webtrak/lcy/          each monitor's events, levels and radar, and the WebTrak app's jobs
    ├── opensky/compare/      opensky compare's reports
    └── adsb/                 the simulated demo, and the dev logger's logs and results
```

Each tool writes there by default, so there's nothing to set. Moving the survey to another computer means copying `data/raw/` (and `derived/`, to save rebuilding), plus `tools/adsb/site.json` for the garden.

## Getting data in

Each source is fetched with its own tool, into `data/raw/`. A deployment's manifest names the raw files, and `make build` does the rest: for an ADS-B source, it runs `adsb analyse --all-positions` on the deployment's window of its logs (an hour either side, so flights at the edges are whole). It gives `analyse` only the files it needs for that window, and runs it again only when one of those files, the site config, the weather, the adsb code or the Python version has changed, by content. So a logs folder that grows all survey, like the garden's, never makes an earlier deployment rebuild; copying the data to another folder or computer doesn't either; and a rebuild that changes nothing takes a second.

| Source | Fetch it with | Manifest entry |
|---|---|---|
| Garden ADS-B | `make pi-collect` | `"adsb": {"adapter": "adsb", "logs": "raw/adsb/garden", "site": "../../adsb/site.json", "weather": "raw/metars/eglc-....csv"}` |
| OpenSky | `make opensky FROM=... TO=...` | `"opensky": {"adapter": "adsb", "logs": "raw/opensky/2026-11-05", "site": "../../opensky/nmt6-site.json", "weather": "raw/metars/eglc-2026-11-05.csv"}` |
| adsb.lol | `noise adsb traces` ([how](../adsb/docs/traces.md)) | `"adsblol": {"adapter": "adsb", "logs": "raw/adsblol/2026-11-05", "site": ...}` |
| WebTrak | `make webtrak` (its download app), or `noise webtrak fetch` | `"webtrak": {"adapter": "webtrak", "chunks": "raw/webtrak/lcy", "monitors": {"nmt6": "106"}}` |

`weather` is optional; without it, heights aren't corrected for QNH. An ADS-B source can give `"results"` instead of `site`, for an analysis run by hand, and then nothing is run for it.

A **deployment** is a manifest in [`deployments/`](deployments). It names the period, the receptors and the sources, and it's kept in git. Copy one to add a period, then run `make build DEPLOYMENT=<name>` (or `noise build <name>`). Data paths (`logs`, `weather`, `chunks`) are relative to the data folder, so a manifest is unchanged when the data moves; other paths (a `site`, the garden's `config`) are relative to the manifest. A source set to `null` is turned off.

The garden's location is private, so a manifest never holds it. Instead, the garden receptor, and the garden logger's `site`, point at the git-ignored `tools/adsb/site.json` (`../../adsb/site.json` from a manifest). Until that file exists, the garden and its logger are left out, with a warning.

Pass ids are dated by the closest approach to one receptor: the manifest's `pass_receptor`, or else its first public receptor, so they come out the same on a computer without the garden's `site.json`.

Built tables go in `data/derived/deployments/<deployment>/common/`: `receptors`, `flights`, `positions`, `noise_events`, `levels`, `coverage`, `approaches`, `passes`, `unseen` and `identity`, as CSV. `positions` and `levels`, which have a row for every second or so, are folders with a file per UTC day (`positions/2026-11-05.csv`), so the app reads only the day it shows, however long the deployment. A flight's positions all go in the file for the day it started. [ARCHITECTURE.md](ARCHITECTURE.md#common-tables) describes them. `build.json` has the counts and warnings. A build writes the tables into a new folder and then swaps it in, so the app, if it's open, never reads a mixture of two builds.

## Aircraft types

An aircraft's type is fixed by its registration, so each airframe is looked up once in its country's official register and kept in [`registry/fleet.csv`](registry/fleet.csv), in git. The build then gives every pass of that airframe the register's type. A pass whose airframe isn't in the table takes its type from its highest-ranked source, as before: in the ADS-B sources that's tar1090-db's.

```bash
make build      # first, so the fleet check knows which aircraft the builds saw
make fleet      # look up any registration not yet in the table (online)
make build      # again, to use what it found
```

`make fleet` (`noise fleet`) checks the registrations of flights that came within 3 km of a receptor and below 3,000 ft (`--km`, `--ft`), as the passes table starts with. It asks only about those not already in the table, and those that were `not found` 30 days or more ago, one request a second. `--dry-run` lists what it would ask, `--recheck` asks again, and `noise fleet G-LCYN HB-AZH` checks just those.

Registers it can ask, in `survey/registers.py`:

| Mark | Register | How | Gives |
|---|---|---|---|
| G- | UK, the CAA's G-INFO | searched, per aircraft | type, model, engines, MTOW, transponder address, noise certificate |
| HB- | Switzerland, FOCA/BAZL | searched, per aircraft | type, model and its marketing name, engines, MTOM, noise certificate |
| EI-, EJ- | Ireland, the IAA | its monthly "all registered aircraft" Excel file | model, engines, MTOW |
| LX- | Luxembourg, the DAC | its relevé, a PDF on data.public.lu | model |

A downloaded register's newest file is fetched once a run and read in memory; nothing of it is saved but the entries asked for, as the files also name owners. It gives the model but not the ICAO type designator, so `registers.MODEL_TYPES` maps the models that fly near the survey (BD-500-1A10 to BCS1, DHC-8-402 to DH8D, and so on). An entry whose model isn't there is kept with no type, says so in its `note`, and settles nothing until the model is added and the entry rechecked; `make fleet` lists those at the end. So is a model that is two types: the ATR 72-500 and 72-600 are both model 72-212A, so those need a `manual` row. The entry's `register_ref` is the file's URL. The file can be months old: the IAA's newest in November 2026 was for the end of September 2025. `make fleet` says when a file is more than two months old. An aircraft registered since then shows as `not found`, with the file's date in its note, and is asked about again after 30 days. Only G-INFO gives the transponder address, so the check that a pass's hex matches the register's covers G- aircraft only. Reading Luxembourg's PDF needs `pdftotext` (`brew install poppler`), the one thing here outside Python's standard library; without it, only Luxembourg's lookups fail.

The Dutch, Italian and German registers publish no file to download: the Dutch open-data file was withdrawn in 2022, Italy's register is open only to those with a legitimate interest, and Germany's isn't public.

It lists the registrations no register covers. Check those by hand and add a row with `register` set to `manual` and the source in `note`; the script never overwrites one. A registration its register doesn't have gets a `not found` row, which settles no type and is asked about again after 30 days. A recheck never throws away what a register said: an aircraft no longer on its register keeps its entry, with status `left the register`, since its passes are from when it was; and if the mark is now on another airframe (another serial number), the earlier entry is kept and its `note` says what the mark is on now, for a person to decide. Only facts about the aircraft are kept, never its owner or operator.

The noise columns are the airframe's certificated levels, in EPNdB, at the approach, lateral and flyover points.

In the app, a pass's type is the resolved one, everywhere, tooltips included; a tooltip adds a source's own type when it differs. Its detail says where it came from and, for a type from a source alone, why the fleet table didn't settle it. Designators are shown with the type's common name (E290, Embraer E190-E2) from `TYPE_NAMES` in `survey/ui/common.js`; add a designator there when a new one turns up. A type in the passes table shown in orange means a source gave another type, or a transponder address other than the register's: worth a look. `build.json`'s `types` counts the passes by where their type came from.

To add a country, write a function in `survey/registers.py` that takes a registration and returns the fleet table's columns, or None if the register doesn't have it, and add it to `REGISTERS`.

## Code

| Module | Does |
|---|---|
| `survey/manifest.py` | Finds and reads a manifest: window, receptors (including private ones), sources; where the data folder is |
| `survey/adapters/__init__.py` | The adapter interface, and the registry of adapters by name |
| `survey/adapters/adsb.py` | Runs `adsb analyse` on an ADS-B source's raw logs when they've changed, and reads its results: our logger, adsb.lol and OpenSky |
| `survey/adapters/webtrak.py` | Reads WebTrak's raw chunk cache through `tools/webtrak`'s parser: radar, events, 1 s levels |
| `survey/schema.py` | The common tables' columns, the daily files for positions and levels, and reading and writing them so a reader never sees half a build |
| `survey/geometry.py` | Local coordinates, closest approach with `at_track_end` (at an edge of the data), the path angle there, and positions along a track |
| `survey/explain.py` | Why a source has no flight in a pass: no data then, outside its area, above its ceiling, or unexplained |
| `survey/link.py` | Joins flights from different sources into passes, by registration, or by comparing their tracks when there's no registration; ranks the sources |
| `survey/resolve.py` | Each pass's registration and type: the fleet table's first, then the sources', with any disagreement |
| `survey/fleet.py` | `noise fleet`: the fleet table, and which registrations to look up |
| `survey/registers.py` | Looking an aircraft up in its country's register online: the UK's and Switzerland's searched, Ireland's and Luxembourg's downloaded |
| `survey/build.py` | `noise build`: each source's prepare step and adapter, approaches, linking, resolving types, the tables, as a list of steps |
| `survey/app.py` | What the page asks for: the deployments, a day, a rebuild; each deployment's small tables, read once and kept until the next build, and its positions and levels read a day at a time |
| `survey/server.py` | `noise serve`: HTTP only, local only, routes to `app.py` and serves `ui/` |
| `survey/ui/` | The page: `index.html` and `style.css`, `common.js` (state and helpers), `map.js` (plan and profile), `timeline.js`, `passes.js` (table and detail), `types.js` (by aircraft type), `main.js` (loading and start-up) |

### Extending it

- **A new kind of source** (the Fusion, airport records): a module in `survey/adapters/` with `PATHS` (its data paths), optionally `MANIFEST_PATHS` and `prepare(name, spec, context, out_dir, log, warnings)`, a step that works out derived files from raw ones for the window (as the ADS-B adapter runs `adsb analyse`), `read(name, spec, context, warnings)` returning any of the source tables (`flights`, `positions`, `noise_events`, `levels`, `coverage`), and `limits(spec, context)`. Positions and levels can be generators, so a long deployment's rows are read as the build takes them rather than all at once. Add it to `ADAPTERS` in `survey/adapters/__init__.py`. Its manifest entry then names it as its `adapter`. Give it a place in `link.SOURCE_RANK` if it should date passes ahead of others, and a colour and name in `ui/common.js`.
- **A new core step** (`match`, `checks`): a module of its own, called from `build.build()` between the existing steps, with its table added to `schema.TABLES`.
- **A new request for the page:** a method on `app.App`, and a line in `server.py`'s `GET_ROUTES` or `POST_ROUTES`.
- **A new panel on the page:** a script in `ui/`, loaded in `index.html` before `main.js`, and a call from `render()` in `main.js`.

`make test` (at the top of the repository) runs every tool's tests on made-up data, with no network, including the `noise` command's and a check that every tool agrees where the data folder is.

## First results: 5 November 2026

- **Linking:** WebTrak had 07:48–11:01 UTC saved, and OpenSky the whole day. All 19 WebTrak passes within 3 km of NMT6 and below 3,000 ft, between 07:55 and 10:55, linked to their OpenSky flight by registration, with tracks that agree. There were none left over on either side.
- **Heights:** at the closest approach, OpenSky's GPS height was a median of about 6 m below WebTrak's radar height, and within ±30 m for all but one.
- **The exception:** a flight whose WebTrak track started after it had passed NMT6. Its closest approach is now flagged as at the end of the track, and left out of the height difference.

# Survey: every source in one place

The survey app shows what each source saw on a day, on one page:
- the garden's ADS-B logger
- OpenSky
- WebTrak's radar and NMT6's noise levels
- later, the Fusion

It lays out the tracks, heights and noise around a chosen receptor (NMT6, or the garden), and links the same aircraft across sources. The design is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Viewing a day

From `tools/survey`:

```bash
make build      # once, and again after fetching more data
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

The app only listens on this computer, and only reads built deployments. **Rebuild** on the page reruns the build after you've fetched more data.

## Getting data in

Each source is fetched with its own tool, and the survey reads what that tool saves:

| Source | Fetch it with | Manifest entry |
|---|---|---|
| Garden ADS-B | `make pi-collect`, then `adsb analyse --all-positions` (in `tools/adsb`) | `"adsb": {"adapter": "adsb", "results": ..., "logs": ...}` (`logs` for its health log) |
| OpenSky | `make viewer FROM=... TO=...` (in `tools/opensky`) | `"opensky": {"adapter": "adsb", "results": ..., "logs": ...}` |
| adsb.lol | `adsb traces`, then `adsb analyse --all-positions` | `"adsblol": {"adapter": "adsb", "results": ...}` |
| WebTrak | `python3 -m webtrak serve` or `fetch` (in `tools/webtrak`) | `"webtrak": {"adapter": "webtrak", "tool": "../webtrak", "site_dir": ..., "monitors": {"nmt6": "106"}}` |

A **deployment** is a manifest in [`tools/deployments/`](../deployments). It names the period, the receptors and the sources, and it's kept in git. Copy one to add a period, then run `make build DEPLOYMENT=<name>`. Paths in a manifest are relative to it, and a source set to `null` is turned off.

The garden's location is private, so a manifest never holds it. Instead, the garden receptor points at the git-ignored `tools/adsb/site.json`. Until that file exists, the garden is left out, with a warning.

Pass ids are dated by the closest approach to one receptor: the manifest's `pass_receptor`, or else its first public receptor, so they come out the same on a computer without the garden's `site.json`.

Built tables go in `data/<deployment>/common/` (ignored by git): `receptors`, `flights`, `positions`, `noise_events`, `levels`, `coverage`, `approaches`, `passes`, `unseen` and `identity`, as CSV. `positions` and `levels`, which have a row for every second or so, are folders with a file per UTC day (`positions/2026-11-05.csv`), so the app reads only the day it shows, however long the deployment. A flight's positions all go in the file for the day it started. [ARCHITECTURE.md](ARCHITECTURE.md#common-tables) describes them. `build.json` has the counts and warnings. A build writes the tables into a new folder and then swaps it in, so the app, if it's open, never reads a mixture of two builds.

## Aircraft types

An aircraft's type is fixed by its registration, so each airframe is looked up once in its country's official register and kept in [`registry/fleet.csv`](registry/fleet.csv), in git. The build then gives every pass of that airframe the register's type. A pass whose airframe isn't in the table takes its type from its highest-ranked source, as before: in the ADS-B sources that's tar1090-db's.

```bash
make build      # first, so the fleet check knows which aircraft the builds saw
make fleet      # look up any registration not yet in the table (online)
make build      # again, to use what it found
```

`make fleet` (`python3 -m survey fleet`) checks the registrations of flights that came within 3 km of a receptor and below 3,000 ft (`--km`, `--ft`), as the passes table starts with. It asks only about those not already in the table, one request a second. `--dry-run` lists what it would ask, `--recheck` asks again, and `python3 -m survey fleet G-LCYN HB-AZH` checks just those.

Registers it can ask online, in `survey/registers.py`:

| Mark | Register | Gives |
|---|---|---|
| G- | UK, the CAA's G-INFO | type, model, engines, MTOW, transponder address, noise certificate |
| HB- | Switzerland, FOCA/BAZL | type, model and its marketing name, engines, MTOM, noise certificate |

It lists the registrations no register covers. Check those by hand and add a row with `register` set to `manual` and the source in `note`; the script never overwrites one. A registration its register doesn't have gets a `not found` row, so it isn't asked again, and settles no type. Only facts about the aircraft are kept, never its owner or operator.

The noise columns are the airframe's certificated levels, in EPNdB, at the approach, lateral and flyover points.

In the app, a pass's type is the resolved one. Its detail says where it came from. A type in the passes table shown in orange means a source gave another type, or a transponder address other than the register's: worth a look. `build.json`'s `types` counts the passes by where their type came from.

To add a country, write a function in `survey/registers.py` that takes a registration and returns the fleet table's columns, or None if the register doesn't have it, and add it to `REGISTERS`.

## Code

| Module | Does |
|---|---|
| `survey/manifest.py` | Reads a manifest: window, receptors (including private ones), sources |
| `survey/adapters/__init__.py` | The adapter interface, and the registry of adapters by name |
| `survey/adapters/adsb.py` | Reads `adsb analyse` results: our logger, adsb.lol and OpenSky |
| `survey/adapters/webtrak.py` | Reads WebTrak's raw chunk cache through `tools/webtrak`'s parser: radar, events, 1 s levels |
| `survey/schema.py` | The common tables' columns, the daily files for positions and levels, and reading and writing them so a reader never sees half a build |
| `survey/geometry.py` | Local coordinates, closest approach with `at_track_end` (at an edge of the data), the path angle there, and positions along a track |
| `survey/explain.py` | Why a source has no flight in a pass: no data then, outside its area, above its ceiling, or unexplained |
| `survey/link.py` | Joins flights from different sources into passes, by registration, or by comparing their tracks when there's no registration; ranks the sources |
| `survey/resolve.py` | Each pass's registration and type: the fleet table's first, then the sources', with any disagreement |
| `survey/fleet.py` | `python3 -m survey fleet`: the fleet table, and which registrations to look up |
| `survey/registers.py` | Looking an aircraft up in its country's register online: the UK's and Switzerland's |
| `survey/build.py` | `python3 -m survey build`: adapters, approaches, linking, resolving types, the tables, as a list of steps |
| `survey/app.py` | What the page asks for: the deployments, a day, a rebuild; each deployment's small tables, read once and kept until the next build, and its positions and levels read a day at a time |
| `survey/server.py` | `python3 -m survey serve`: HTTP only, local only, routes to `app.py` and serves `ui/` |
| `survey/ui/` | The page: `index.html` and `style.css`, `common.js` (state and helpers), `map.js` (plan and profile), `timeline.js`, `passes.js` (table and detail), `types.js` (by aircraft type), `main.js` (loading and start-up) |

### Extending it

- **A new kind of source** (the Fusion, airport records): a module in `survey/adapters/` with `PATHS`, `read(name, spec, context, warnings)` returning any of the source tables (`flights`, `positions`, `noise_events`, `levels`, `coverage`), and `limits(spec, context)`. Positions and levels can be generators, so a long deployment's rows are read as the build takes them rather than all at once. Add it to `ADAPTERS` in `survey/adapters/__init__.py`. Its manifest entry then names it as its `adapter`. Give it a place in `link.SOURCE_RANK` if it should date passes ahead of others, and a colour and name in `ui/common.js`.
- **A new core step** (`match`, `checks`): a module of its own, called from `build.build()` between the existing steps, with its table added to `schema.TABLES`.
- **A new request for the page:** a method on `app.App`, and a line in `server.py`'s `GET_ROUTES` or `POST_ROUTES`.
- **A new panel on the page:** a script in `ui/`, loaded in `index.html` before `main.js`, and a call from `render()` in `main.js`.

`make test` runs the tests on made-up data, with no network.

## First results: 5 November 2026

- **Linking:** WebTrak had 07:48–11:01 UTC saved, and OpenSky the whole day. All 19 WebTrak passes within 3 km of NMT6 and below 3,000 ft, between 07:55 and 10:55, linked to their OpenSky flight by registration, with tracks that agree. There were none left over on either side.
- **Heights:** at the closest approach, OpenSky's GPS height was a median of about 6 m below WebTrak's radar height, and within ±30 m for all but one.
- **The exception:** a flight whose WebTrak track started after it had passed NMT6. Its closest approach is now flagged as at the end of the track, and left out of the height difference.

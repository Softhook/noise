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
- **Passes:** one row per aircraft movement that came within the chosen distance of the receptor (3 km to start with), and below the chosen height (3,000 ft), in any source, with each source's distance and height at its closest approach, the height difference between the sources, and the loudest noise event from 5 s before to 40 s after the pass (sound takes a few seconds to arrive, and the clocks may differ a little). A grey value means the closest point was at the end of that source's track, so the aircraft may have come closer outside its data. That happens at the edge of OpenSky's box, or when WebTrak's saved data starts or ends mid-pass.
- **Why a source missed a pass:** where a source has no flight in a pass, the table says why. *No data then*, *outside its area* and *above its ceiling* mean it couldn't have seen it. **Missed** means it should have: it had data then, and the aircraft spent at least 20 s inside its area and below its ceiling. That's a gap in its data, or a pass that wasn't linked, and worth looking at. The **Missed, unexplained** tile counts these, and **Unexplained misses only** lists just them.
  - For the ADS-B-family sources, the area is `adsb analyse`'s 15 km around its site, plus the box in the logs' `SOURCE.txt` if they were cut to one (OpenSky's 5 km box around NMT6). The ceiling is `adsb analyse`'s 10,000 ft. Give `max_km` or `ceiling_ft` in the manifest's source entry if its analysis used others.
  - For WebTrak, the area is `max_km` around any receptor, at any height.

The app only listens on this computer, and only reads built deployments. **Rebuild** on the page reruns the build after you've fetched more data.

## Getting data in

Each source is fetched with its own tool, and the survey reads what that tool saves:

| Source | Fetch it with | Manifest entry |
|---|---|---|
| Garden ADS-B | `make pi-collect`, then `adsb analyse --all-positions` (in `tools/adsb`) | `"adsb": {"adapter": "adsb", "results": ...}` |
| OpenSky | `make viewer FROM=... TO=...` (in `tools/opensky`) | `"opensky": {"adapter": "adsb", "results": ..., "logs": ...}` |
| adsb.lol | `adsb traces`, then `adsb analyse --all-positions` | `"adsblol": {"adapter": "adsb", "results": ...}` |
| WebTrak | `python3 -m webtrak serve` or `fetch` (in `tools/webtrak`) | `"webtrak": {"adapter": "webtrak", "tool": "../webtrak", "site_dir": ..., "monitors": {"nmt6": "106"}}` |

A **deployment** is a manifest in [`tools/deployments/`](../deployments). It names the period, the receptors and the sources, and it's kept in git. Copy one to add a period, then run `make build DEPLOYMENT=<name>`. Paths in a manifest are relative to it, and a source set to `null` is turned off.

The garden's location is private, so a manifest never holds it. Instead, the garden receptor points at the git-ignored `tools/adsb/site.json`. Until that file exists, the garden is left out, with a warning.

Built tables go in `data/<deployment>/common/` (ignored by git): `receptors`, `flights`, `positions`, `noise_events`, `levels`, `coverage`, `approaches`, `passes` and `unseen`, as CSV. [ARCHITECTURE.md](ARCHITECTURE.md#common-tables) describes them. `build.json` has the counts and warnings.

## Code

| Module | Does |
|---|---|
| `survey/manifest.py` | Reads a manifest: window, receptors (including private ones), sources |
| `survey/adapters/adsb.py` | Reads `adsb analyse` results: our logger, adsb.lol and OpenSky |
| `survey/adapters/webtrak.py` | Reads WebTrak's raw chunk cache through `tools/webtrak`'s parser: radar, events, 1 s levels |
| `survey/geometry.py` | Local coordinates and closest approach, with `at_track_end` |
| `survey/explain.py` | Why a source has no flight in a pass: no data then, outside its area, above its ceiling, or unexplained |
| `survey/link.py` | Joins flights from different sources into passes, by registration, or by track when there's no registration |
| `survey/build.py` | `python3 -m survey build`: adapters, approaches, linking, the tables |
| `survey/server.py`, `survey/ui.html` | `python3 -m survey serve`: the app |

`make test` runs the tests on made-up data, with no network.

## First results: 5 November 2026

- **Linking:** WebTrak had 07:48–11:01 UTC saved, and OpenSky the whole day. All 19 WebTrak passes within 3 km of NMT6 and below 3,000 m, between 07:55 and 10:55, linked to their OpenSky flight by registration. There were none left over on either side.
- **Heights:** at the closest approach, OpenSky's GPS height was a median of about 6 m below WebTrak's radar height, and within ±30 m for all but one.
- **The exception:** a flight whose WebTrak track started after it had passed NMT6. Its closest approach is now flagged as at the end of the track, and left out of the height difference.

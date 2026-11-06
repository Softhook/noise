# Survey architecture: joining ADS-B, Fusion, WebTrak and airport records

The Thamesmead survey has several data sources that each know part of the story: the Fusion in the garden measures the sound, the ADS-B logger in the garden records the aircraft, WebTrak gives NMT6's levels and the airport's radar, adsb.lol's public archive gives other receivers' ADS-B, and the airport may give us its own records. This document describes how they fit together so that any source can be added or removed without changing the rest.

**Status:** a plan. Nothing in `tools/survey` is written yet. Phase 0 is built first (see [Phases](#phases)).

## Why

WebTrak isn't a long-term source. It is scraped, and if it is closed to us, or we stop using it, the survey must carry on unchanged. But it is useful now in two ways:

- to check that the ADS-B logger gives the right positions, heights, times and types, before the noise meter arrives (Phase 0);
- to give NMT6 levels for the same flights during the short Fusion trial (Phase 1).

After that it should only be needed now and then, to settle a question about one flight, such as whether an aircraft was an E190 or an E190-E2. Airport records, if we get them, would do the same job better and should take precedence.

So the design has one rule: **each source plugs in through an adapter, and the core only sees common tables.**

## Layers

```text
 COLLECTORS (unchanged, independent)      ADAPTERS             CORE (source-agnostic)          PRODUCTS
 ┌───────────────┐                      ┌───────────┐      ┌───────────────────────────┐   ┌───────────────┐
 │ adsb logger   │─logs─▶ adsb analyse ▶│ adsb      │─┐    │ link    flights ↔ flights │   │ Stage 1 Qs    │
 │ (Pi, offline) │                      └───────────┘ │    │ match   events ↔ passes   │──▶│ NMT6 v garden │
 ├───────────────┤                      ┌───────────┐ ├──▶ │ resolve type, registration│   │ ADS-B checks  │
 │ Fusion        │─export──────────────▶│ fusion    │─┤    │ checks  clocks, coverage  │   │ viewer        │
 ├───────────────┤                      └───────────┘ │    └─────────────▲─────────────┘   └───────────────┘
 │ webtrak       │─raw chunk cache─────▶┌───────────┐ │                  │ asks when unsure
 │ scraper       │                      │ webtrak   │─┤    ┌─────────────┴─────────────┐
 ├───────────────┤                      └───────────┘ │    │ LOOKUPS (optional)        │
 │ airport       │─files───────────────▶┌───────────┐ │    │ fleet registry (local)    │
 │ records       │                      │ airport   │─┤    │ airport records           │
 └───────────────┘                      └───────────┘ │    │ webtrak targeted fetch    │
                       overrides, fleet▶┌───────────┐ │    └───────────────────────────┘
                                        │ manual    │─┘
                                        └───────────┘
```

1. **Collectors** are the existing tools: [`tools/adsb`](../adsb/README.md), [`tools/webtrak`](../webtrak/README.md) and [`tools/fusion`](../fusion). They don't know about each other or about this package. The Pi side stays standard-library only and is never changed for the sake of the core.
   - [adsb.lol's daily archive](../adsb/docs/traces.md), not shown in the diagram, comes in through `tools/adsb` too. `adsb traces` turns its track files into logs, and `adsb analyse` turns those into flights and positions, as for our logger. The same `adsb` adapter then reads it, with the source named in the manifest (`adsb` or `adsblol`).
2. **Adapters** turn one source's own output into the [common tables](#common-tables). There is one adapter per source. Removing a source means removing it from the deployment's manifest.
3. **The core** links flights across sources, matches noise events to them and settles each one's identity, using only the common tables. It never imports `adsb`, `webtrak` or `fusion`.
4. **Lookups** answer a question about one flight when the core can't settle it from what it has. They are optional, limited by a budget, and their answers are kept.
5. **Products** are the analyses, reports and viewers. They read the core's outputs, not the sources.

### Dependency rules

- Only an adapter or lookup may import its source's package or read its files.
- The core has its own geometry module rather than importing `adsb.geometry`, so the Pi's code can change without touching the core, and the other way round.
- Source-specific physics stays in its adapter or collector. The QNH and temperature correction of ADS-B heights belongs to `adsb analyse`, for example. The core takes heights as given, along with what kind of height each one is.
- Everything is standard-library Python, like the collectors.

## Common tables

CSV files, with times in UTC ISO format (`2026-11-05T08:12:31.250Z`). An adapter that can't establish a file's time zone stops, as the measurement plan requires. Every row carries `source` and the source's own id, so any result can be traced back to its source.

| Table | Key columns | Filled by |
|---|---|---|
| `receptors` | `id` (`garden`, `nmt6`), lat, lon, ground elevation, mic height | the manifest |
| `flights` | source, source_id, first and last time, registration (normalised), callsign and its kind (ICAO or IATA), type, squawk, direction, origin, destination | adsb, adsblol, webtrak, airport |
| `positions` | source, source_id, t, lat, lon, height AMSL, height kind (`qnh`, `geometric`, `radar`), ground speed, track | adsb, adsblol, webtrak |
| `noise_events` | source, receptor, start, LAmax time, end, LAmax, SEL, Leq, metric (e.g. LAS or 1 s LAeq), trigger flags | fusion (garden), webtrak (nmt6), airport (nmt6) |
| `levels` | source, receptor, t, level, flag | fusion, webtrak |
| `clock` | source, start, end, synchronised, offset if known | adsb health log, Fusion event log |

Normalisation is the adapters' job:

- **Registration:** upper case, letters and digits only. WebTrak gives `GLCYN`, the ADS-B database `G-LCYN`, and both become `GLCYN`.
- **Callsign:** kept as given, with its kind. WebTrak gives the IATA form (`BA8721`) and ADS-B the ICAO form (`CFE…`), so callsigns can't be used to join flights unless a table of airline codes is added.
- **Type:** ICAO type designator (`E190`, `E290`, `BCS1`, `A20N`).
- **Height:** metres above mean sea level. WebTrak's height above the aerodrome is converted with the aerodrome's elevation, and its kind is recorded as `radar`, because we don't know how WebTrak derives it.

The core computes **closest approach to every receptor** from `positions`, so NMT6 is just another receptor, and an NMT6 event can be matched to an ADS-B track as well as to WebTrak's.

## Core

### Link: one pass per aircraft movement

`link` groups the flights from different sources that are the same aircraft movement into a **pass**. Evidence, from strongest to weakest:

1. the same registration, with overlapping times;
2. the same squawk, with overlapping times;
3. tracks that stay close in space and time: the median separation, after the best time shift, under a threshold.

A link needs the tracks to agree as well as the identifiers, so a registration sent by mistake doesn't join two different aircraft. Each link records its evidence and a confidence.

A pass id is stable across reruns, so notes and overrides keep pointing at the same pass: the UTC time of closest approach to the garden, to the minute, and the registration, or the ADS-B hex if there's no registration (e.g. `20261105T0812-GLCYN`).

### Match: noise events to passes

`match` matches each noise event at each receptor to the pass that best fits its LAmax time and the predicted sound arrival from that pass's closest approach. It also lists any other pass close enough to have contributed, such as a helicopter or a high Heathrow arrival. It replaces the matching steps planned in `adsb analyse` (steps 8 and 9 of the [ADS-B plan](../adsb/docs/PLAN.md)), so that it works the same for the garden and for NMT6.

### Resolve: identity, with where each answer came from

`resolve` decides each pass's type and registration. It takes the sources in this order and stops at the first confident answer:

1. **Manual overrides** (`registry/overrides.csv`, kept in git). A person's decision always wins.
2. **Airport records**, if we have them for that period.
3. **The fleet registry** (`registry/fleet.csv`, registration → type, kept in git). LCY's fleet is a few dozen airframes that come back day after day, so once an airframe is confirmed it never needs looking up again. This is what ends the dependence on WebTrak.
4. **The ADS-B database type**, if it's present and agrees with the registry.
5. **A [lookup](#lookups)**, only if one of these triggers fires:
   - the type is on the watch list, the pairs that matter to the survey: `E190`/`E290`, `A320`/`A20N`, `BCS1`/`BCS3`;
   - the type or registration is missing;
   - the registration isn't in the fleet registry;
   - two sources disagree.

Each resolved field has a `_source` column (`type_source`: `manual`, `airport`, `fleet`, `adsb_db`, `webtrak`). Any result can therefore be reported "without WebTrak", and we can see exactly which flights WebTrak changed.

### Checks

`checks` reports on the sources against each other:

- **Clock offset** between each pair of sources that track the same aircraft, per pass and per day. Each comes from the time shift that best lines up their tracks. A steady value confirms the clocks, and a jump shows a fault. For the Fusion it uses the measurement plan's check of LASmax time against the predicted sound arrival.
- **Coverage:** the share of each source's passes near the garden that the other sources also saw, by distance and height. For ADS-B this shows the antenna's coverage, and the effect of the Fusion's 4G modem. In the 37-day survey, WebTrak is only asked about single passes, so adsb.lol is the reference for every day. It's ADS-B too, so it can't show aircraft that don't transmit: only WebTrak and the airport show those.
- **Heights:** WebTrak radar height against the ADS-B QNH, geometric and chosen heights.
- **Identity conflicts:** registrations or types that disagree between sources.
- **Unmatched:** flights and events on either side with nothing to link to.

### Outputs

Written to `data/<deployment>/` (git-ignored):

| File | Contents |
|---|---|
| `common/*.csv` | the common tables, as the adapters wrote them |
| `passes.csv` | one row per pass: its source flights, the evidence and confidence |
| `event_matches.csv` | noise event → pass, per receptor, with geometry and predicted sound arrival |
| `identity.csv` | resolved type and registration per pass, with their sources |
| `checks.txt` | the checks above |
| `match_check.html` | a page per matched event, for checking matches by eye (see [Match check page](#match-check-page)) |
| `lookups.log` | every lookup: what was asked, why, how many requests, the answer |

### Match check page

A page that opens offline in a browser, like the ADS-B viewer, with one entry per noise event:

- the 1 s level trace, about 60 s either side of LAmax, with a vertical line at each candidate pass's predicted sound arrival, labelled with its type and distance
- the matched pass's track, and any other candidate's, on a small plan around the receptor
- the Fusion's spectrogram for the event, if the export has spectra
- the match, its flags, and the pass's identity and where each part came from

In the trial, every match is checked on it. In the survey, only the flagged and unmatched ones. MONA's real-time view of levels with the closest approaches marked ([Jackson et al. 2021](https://doi.org/10.3390/engproc2021013006), figure 4) is the same idea, and [NoiseCapt](https://github.com/kx1t/docker-noisecapt)'s spectrogram for each pass gave us the spectrogram. Built with `match`, in Phase 1.

## Lookups

A lookup takes a pass (its time window and whatever is known about it) and returns flights and positions in the common tables, or nothing. The answer is written to the fleet registry, if it settles an airframe's type, and to the lookup log.

- **Fleet registry:** local, free, always on.
- **Airport records:** local files, if we get them. They rank above WebTrak.
- **adsb.lol:** only for days already downloaded and converted (`cache-only`). A day is about 4 GB, so it's fetched by hand for chosen days, not by a lookup.
- **WebTrak targeted fetch:** reads the raw chunk cache first, and only then fetches the chunks around the pass, about ±2 minutes or 8 requests. It uses `tools/webtrak`'s client, so it keeps its honest user-agent, pacing and caching.

Each lookup's mode is set in the manifest:

| Mode | Behaviour |
|---|---|
| `off` | not used |
| `cache-only` | uses what is already downloaded; makes no requests |
| `on` | may make requests, up to `max_requests` per run; when the budget runs out, further passes are left unresolved and listed |

The budget is the guard against drawing attention to the scraper: Phase 2 might allow a few dozen requests a run at most.

## Manifest

One JSON file per deployment, in `tools/deployments/`, kept in git. It names the period, the receptors, which sources to use and how, and the lookup policy. Every command takes its window and paths from it.

```json
{
  "deployment": "2026-11-phase0",
  "window_utc": ["2026-11-20T06:00:00Z", "2026-11-23T22:00:00Z"],
  "receptors": {
    "garden": {"lat": 51.5, "lon": 0.1, "ground_elevation_m": 3.0, "mic_height_m": 3.0},
    "nmt6": {"lat": 51.50535, "lon": 0.11075, "ground_elevation_m": null, "mic_height_m": null}
  },
  "sources": {
    "adsb": {"results": "../adsb/data/phase0"},
    "webtrak": {
      "role": "source",
      "cache": "../webtrak/data/lcy",
      "windows": [["2026-11-20T06:30:00Z", "2026-11-20T09:30:00Z"]]
    },
    "fusion": null,
    "airport": null
  },
  "lookups": {
    "airport": {"mode": "off"},
    "webtrak": {"mode": "cache-only", "max_requests": 0}
  }
}
```

WebTrak's `role` is one of:

- `source`: its tracks and NMT6 events come in through the adapter, for the listed windows;
- `lookup`: it's only asked about single passes;
- left out: not used at all.

The airport can play the same roles.

## Layout

```text
tools/
  adsb/  webtrak/  fusion/            collectors, unchanged
  deployments/<name>.json             manifests
  survey/
    ARCHITECTURE.md                   this file
    survey/
      __main__.py                     build | lookup | check
      schema.py                       table definitions, reading, writing and validation
      geometry.py                     local coordinates, closest approach to each receptor
      adapters/adsb.py                reads adsb analyse's flights.csv and positions.csv (--all-positions), for
                                      our logger or adsb.lol (source from the manifest)
      adapters/webtrak.py             reads the raw chunk cache with webtrak.parse, within the windows
      adapters/fusion.py              reads the Fusion export, once its format is settled
      adapters/airport.py             reads airport records, once we know their format
      adapters/manual.py              reads the registry's overrides
      lookups/fleet.py
      lookups/airport.py
      lookups/webtrak.py
      link.py  match.py  resolve.py  checks.py
    registry/fleet.csv                registration, type, source, date confirmed
    registry/overrides.csv            pass id, field, value, reason, who
    tests/
```

Commands:

```bash
python3 -m survey build  --manifest ../deployments/2026-11-phase0.json   # adapters, link, match, resolve, checks
python3 -m survey check  --manifest ...                                   # checks only, on an existing build
python3 -m survey lookup --manifest ... --pass 20261105T0812-GLCYN        # settle one pass by hand
```

## Adding or removing a source

To **add** one:

1. Write an adapter that fills some of the common tables.
2. Give it an entry in the manifest.
3. If it can answer identity questions, give it a lookup and a place in `resolve`'s order.

Nothing else changes.

To **remove** one, set it to `null` in the manifest. The build still runs. Its `_source` values disappear from `identity.csv`, and any checks that needed it say so instead of failing.

The test that WebTrak really is removable: from Phase 1 on, build each deployment twice, with WebTrak and without it, and compare. Apart from the NMT6 comparison, every difference should be a pass whose identity WebTrak settled, and each of those should be added to the fleet registry so that the next build doesn't need it.

## Phases

| Phase | Sources | Lookups | Built in this phase |
|---|---|---|---|
| 0: check ADS-B | adsb; webtrak as a source for about three 3-hour windows on 2–3 days | fleet | schema, adsb and webtrak adapters, geometry, `link`, `checks`; the fleet registry seeded from confirmed matches |
| 1: short Fusion trial | adsb, fusion; webtrak as a source for the trial | fleet; webtrak cache-only | fusion adapter, `match` at the garden and NMT6, the NMT6 v garden comparison, the with/without-WebTrak test |
| 2: 37-day survey | adsb, fusion, adsblol; airport if we get records | fleet, airport; webtrak `on` with a small budget | `resolve`'s lookups, the airport adapter |

Phase 0 is fetched after the fact, from windows chosen once the Pi's health log shows they're clean (clock synchronised, no gaps), and with a spread of weather for the height check. The 3.8 hours saved for 5 Nov 2026 held 31 LCY movements, so three such windows give about a hundred LCY passes and many more overflights, which is enough to measure the clock offset, position and height differences.

Phase 0 is tested before the Pi has any real data. We make ADS-B logs from the real 5 Nov WebTrak tracks, with a known clock offset, position noise and height bias, and some aircraft dropped, and check that `link` and `checks` recover them.

## Prior work

- **MONA** (Stanford; [Jackson, Rindfleisch and Alonso 2021](https://doi.org/10.3390/engproc2021013006)) is the closest published system: a single-board computer with dump1090-fa, a GPS with pulse-per-second for the clock, and a sound level meter at each station. Its matching method, "DA-PLANE", works from the aircraft's side. It computes each flight's closest approach to the meter and the expected time of the sound peak. It then looks for peaks in the level time series near that time, rather than relying only on the meter's own triggered events. It stores max(LAeq,1s) and SEL for each attributed overflight, and counts overflights per day within a distance. The paper cites Harding and Ferrier, "Using Post Analysis of a Noise Sample Stream in place of Noise Monitor Based Thresholds in the Detection of Aircraft Noise" (Inter-Noise 2014), and Giladi, "Real-time Identification of Aircraft Sound Events" (Transportation Research Part D 87, 2020), for the same approach. Its code doesn't appear to be published.
- **[Planefence](https://github.com/sdr-enthusiasts/docker-planefence)** logs the aircraft that pass within a set distance and below a set height of a receiver, with [NoiseCapt](https://github.com/kx1t/docker-noisecapt) for an uncalibrated microphone. Its daily table of close passes is the model for the close-pass count on the ADS-B status page. Its noise measurement isn't usable for ours.

## Open questions

- **Matching from the pass side:** should `match` also search the `levels` table near each pass's predicted sound arrival, as MONA does, so that a pass the Fusion didn't trigger on still gets a level? The trial will show how many passes have no Fusion event.
- **Seeding the fleet registry:** only from airframes confirmed by matching two sources, or also from a published fleet list? A published list would need its source and date recorded.
- **Airport records:** what format, which fields and for which periods? It matters most whether they give the type for each movement and NMT6's event levels.
- **WebTrak heights:** how are they derived? Phase 0's comparison against ADS-B geometric height should tell us.
- **NMT6's microphone height and ground elevation:** needed for its closest-approach geometry. They may be in the airport's noise reports.
- **A table of airline codes** to join IATA and ICAO callsigns. It isn't needed while registrations join flights, but it would help with aircraft that don't send one.

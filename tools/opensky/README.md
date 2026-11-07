# OpenSky: aircraft near NMT6

`noise opensky compare` gets every aircraft that passed near NMT6 (St Pauls Church, Thamesmead) from the [OpenSky Network](https://opensky-network.org)'s research database (Trino), and compares them with the WebTrak data saved by [`tools/webtrak`](../webtrak/README.md). It gives a position about once a second and full-resolution heights, and needs research access.

We use only Trino. OpenSky's free REST API was tried first and dropped (see [below](#why-not-the-rest-api)).

## Running it

From the top of the repository:

```bash
make setup    # once: .venv with every tool, pyopensky included
make opensky FROM=2026-10-28T00:00Z TO=2026-10-29T00:00Z           # a period's positions, and its METARs
make opensky-compare FROM=2026-11-05T08:01Z TO=2026-11-05T11:01Z   # ARGS="--radius 3000 --geoid 45" to change them
make test     # every tool's; this one's use made-up data and a fake Trino client, with no network
```

### Viewing a day

1. Once: `make setup`, and set up your OpenSky login (see [Setup](#setup)).
2. Fetch the period, in UTC, for example one whole day:

   ```bash
   make opensky FROM=2026-10-28T00:00Z TO=2026-10-29T00:00Z
   ```

   This takes a minute or two the first time (one OpenSky query per hour), and seconds after that, from the cache. It writes OpenSky's positions as hourly logger files to `data/raw/opensky/2026-10-28/` (named after the `FROM` date, so a period of several days goes in its first day's folder), and EGLC's METARs to `data/raw/metars/eglc-2026-10-28.csv`. A period already fetched isn't fetched again, since raw data isn't overwritten: give `REPLACE=1` to fetch it afresh (the METARs are kept unless you do).
3. Add a deployment for the period in `tools/survey/deployments/` (copy one, and change the dates and folders), then `make build`. That analyses the logs with NMT6 as the site and builds the survey's tables, and `make serve` shows them in the survey app. The ADS-B viewer for the period is `data/derived/deployments/<name>/analysis/opensky/viewer.html`: the flights are built into the file, so it opens offline. It holds OpenSky's data, so keep it private, under OpenSky's research terms. See [In the ADS-B viewer](#in-the-ads-b-viewer) for what goes into it, and [the viewer's guide](../adsb/docs/analysis.md#the-viewer) for how to use it.

`make opensky-compare` runs `noise opensky compare --from ... --to ...`.

For each hour of the period, it runs one query on `state_vectors_data4` for every airborne aircraft in a box 5 km either side of NMT6, whichever airport it uses. Each query asks for the whole hour, and OpenSky sends each position once, at the time it received it. It reads 5 minutes either side of the period, from both OpenSky and WebTrak, so an aircraft passing near the start or end has positions on both sides of its closest approach; only passes whose closest approach falls inside the period are kept. It splits each aircraft's positions into passes and works out each pass's closest approach to NMT6. Passes that came within `--radius` (default 3000 m, as WebTrak) are written to `data/derived/opensky/compare/nmt6-trino-<from>.csv`, which git ignores. It then pairs them with WebTrak's radar tracks by time, to within 90 s, and lists each one's NMT6 event and the height difference.

For each pass it gives:
- the aircraft type and registration (see [Aircraft type](#aircraft-type)),
- the closest ground distance,
- GPS height above sea level (`geoaltitude` minus `--geoid`),
- uncorrected pressure altitude,
- the gap between OpenSky's positions at the closest point,
- the number of receivers that heard it.

### Code

| Module | Does |
|---|---|
| `opensky/trino.py` | The `state_vectors_data4` query, one whole hour partition at a time, and the caching rule |
| `opensky/passes.py` | State vectors into one closest approach per aircraft pass |
| `opensky/geometry.py` | Distances from NMT6, closest approach, the query box |
| `opensky/webtrak.py` | WebTrak's saved radar tracks and NMT6 events |
| `opensky/compare.py` | The `compare` command: the CSV and the table against WebTrak |
| `opensky/logs.py` | The `logs` command: positions as the ADS-B logger's hourly files, for `adsb analyse` and its viewer |
| `opensky/aircraft.py` | Aircraft type and registration from a dated copy of tar1090-db, and the `aircraft` command |
| `opensky/common.py` | NMT6, paths, times and numbers |

### Setup

Research access is free for university researchers, but OpenSky has to approve it (My OpenSky → Request Data Access). Then:

```bash
make setup   # at the top of the repository: .venv, with pyopensky (the project's "opensky" extra); git ignores .venv
```

[pyopensky](https://github.com/junzis/pyopensky) is the client OpenSky recommends. It's the only package outside the standard library in this repository, and only this tool needs it. Only `opensky/trino.py` imports it, and only when it makes a query, so the rest of the tool and its tests run on the standard library. `tools/adsb` still uses only the standard library, so the Pi needs nothing installed.

**Login:** Trino uses your OpenSky **account username and password**, not an API client ID and secret. Put them in pyopensky's `settings.conf`, and keep the file private (`chmod 600`). On a Mac it's at `~/Library/Application Support/pyopensky/settings.conf`:

```ini
[default]
username = your opensky username, in lower case
password = your password
```

If they're blank, pyopensky opens a browser to log in. Never put them in this repository.

### OpenSky's rules for queries

There are no API credits. Instead, OpenSky limits the load on its shared server, and it suspends accounts that keep ignoring [its guidelines](https://openskynetwork.github.io/opensky-api/trino.html). `opensky/trino.py` keeps to them, and the tests check it:

- **Partition filter:** every query filters on the `hour` partition, as well as on a small latitude/longitude box. Trino rejects queries without one.
- **Size:** one query per hour, run one at a time. Each user may have at most 2 queries running and 2 queued. A query may run for at most 30 minutes and scan at most 100 GB.
- **Caching:** pyopensky saves each result (in `~/Library/Caches/opensky` on a Mac, kept for 90 days), keyed on the query's text. Each query covers a whole hour in the same box, whatever `--from`, `--to` and `--radius` (up to 3000 m) are, so any later run that needs that hour reads it from the cache; the rows are cut to the period here. It only caches hours that ended more than a day ago. OpenSky may still be processing more recent hours, and a saved partial result would never be refreshed, so those are queried again on every run.
- **Stale states:** `time - lastcontact <= 15` drops the states OpenSky keeps for up to 300 s after it last heard an aircraft.

- **Less to send:** OpenSky drops ground states (the box takes in London City's runway, about half the rows) and repeated positions, and sends only the columns the tool uses, unsorted. Hours that haven't started aren't queried.

Three hours near NMT6 (08:01–11:01) take five whole-hour queries, about 5 seconds each, including the 5 minutes either side, and return about 4,800 positions (about 1,000 an hour, against 2,500 state vectors an hour before OpenSky dropped ground states and repeats). A later run of any period within those hours takes under a second.

Some periods are missing from OpenSky's data because of outages. Two of them fall in 2026: 2 January 19:00 to 3 January 18:00, and 24 January 08:00–17:00 UTC. Its processing changed on 13–14 August 2026, so results from before and after then may differ.

### In the ADS-B viewer

`noise opensky logs` writes the same positions as the ADS-B logger's hourly files, so [`tools/adsb`](../adsb/README.md)'s `adsb analyse` and its viewer read them unchanged, with NMT6 as the site (`nmt6-site.json`). `make opensky` runs `opensky logs` (with `--replace`, which only ever removes the files of an earlier `opensky logs` run) and `adsb metars`. `make build` then runs `adsb analyse --all-positions` for each deployment that names the folder, with `nmt6-site.json` as its `site`, whenever the logs have changed. It keeps every flight's positions, not just the arrivals and departures, so the [survey app](../survey/README.md) can show OpenSky alongside WebTrak and, later, the garden's logger.

- It uses the same whole-hour queries as `compare`, so hours already fetched come from the cache.
- Heights go in as feet, as readsb gives them. `alt_geom` is OpenSky's `geoaltitude`, which `adsb analyse` corrects with the config's geoid height, and `alt_baro` is pressure altitude. `make opensky` also downloads EGLC METARs (`adsb metars`), so QNH heights are worked out too, and `QNH minus geometric` compares the two.
- Each record carries the aircraft's type, registration and description (`t`, `r`, `desc`), as readsb's do, so the viewer's "By aircraft type" chart and `summary.txt` work.
- OpenSky gives no ground speed here. `adsb analyse` works out headings from the positions.
- `nmt6-site.json` names the site "NMT6, St Pauls Church, Thamesmead", labels it NMT6, and marks it `public`, since WebTrak publishes its location. So the summary and the viewer show its latitude and longitude. Its ground elevation and microphone height are placeholders, so heights above the microphone are approximate.
- The summary names OpenSky as the source and notes that there's no health log. Gaps over 30 minutes are reported as unchecked. On 28 October there were three, 01:01–02:40 and 04:53–05:35 UTC. Each lay between high overflights, with nothing else within 5 km of NMT6. OpenSky was receiving aircraft over London in every 10 minutes of those hours, so the sky near NMT6 was quiet: London City is closed at night, and Heathrow's first arrivals came after 04:30.
- Only positions in the 5 km query box are included.
- The files stay in `data/raw/opensky/` and `data/derived/`, which git ignores, under OpenSky's research terms.

**28 October 2026 (westerly operations):** `adsb analyse` labels all 71 London City flights below 500 m as runway 27 arrivals. They fly a remarkably tight path:
- 203–215 m south of NMT6 (median 210 m, sd 2 m),
- 319–335 m above sea level as they pass (median 327 m, sd 3 m),
- on a 5.5–5.7° path, heading 273°.

From 4 km east of NMT6 to 3 km west, the flights stay within about ±25 m of each other sideways and ±20 m in height. OpenSky's GPS heights come in 25 ft (7.6 m) steps, which limits how finely height can be resolved.

By type, the 71 were 55 E190, 5 BCS1 (A220-100), 3 DH8D (Dash 8-400), 3 E290 and 3 E295 (E190-E2 and E195-E2), 1 C56X and 1 E55P (business jets). All the types fly the same path: their medians are 209–215 m from NMT6 at 321–331 m.

### Aircraft type

OpenSky's state vectors give no aircraft type, so `compare` and `logs` look up every `icao24` in [tar1090-db](https://github.com/wiedehopf/tar1090-db/tree/csv), the database readsb uses on the garden Pi. Both sources therefore give the same ICAO type codes (`E190`, `BCS1`, `A20N`).

- **Saved copies:** each copy is kept in `data/raw/opensky/aircraft-db/aircraft-<date downloaded>.csv.gz`, which git ignores. Every run uses the newest one and prints its name, and `logs` writes it into `SOURCE.txt`.
- **First run:** if there's no copy, it downloads one, about 8 MB.
- **Updating:** `noise opensky aircraft --update` saves a newer copy. Keep one copy for a whole stage, as the [plan](../adsb/docs/PLAN.md) says, and pass `--aircraft-db PATH` to repeat a run with an older one.
- **Missing types:** any aircraft without a type is listed as a warning, with its `icao24` and callsign. On 28 October all 264 aircraft were found. On the 3 flights WebTrak also had, the types matched.

### Things to know about the data

- **Repeated positions:** a state vector repeats the last position until a new one arrives. The query groups states by `lastposupdate`, which the tool uses as each position's time, keeping the first state's heights and the most receivers that heard any of them.
- **GPS height:** `geoaltitude` is height above the WGS84 ellipsoid. Subtract the geoid height (about 45 m in London) to get height above sea level, as WebTrak gives.
- **Pressure altitude:** `baroaltitude` is pressure altitude (1013.25 hPa) and needs a QNH correction, as `tools/adsb` does. On 5 November it read about 90–100 m below GPS height near NMT6.
- **Aircraft without ADS-B:** the state vectors only include aircraft that send ADS-B. `readsb_mlat_sv` has multilateration (MLAT) positions, worked out from the timing of signals at several receivers, for some aircraft that send no position. The tool doesn't query it yet.
- **Aircraft type:** OpenSky doesn't give one. The tool looks it up (see [Aircraft type](#aircraft-type)), so a type is only as good as the database's entry for that `icao24`.
- **Licence:** OpenSky's research terms limit what can be published or redistributed. Publish summaries and cite OpenSky, not the raw state vectors.

### First comparison, 5 November 2026, 08:01–11:01 UTC

- **Matches:** 33 aircraft passed within 3 km of NMT6. WebTrak had all 33, plus one OpenSky didn't: a KC-135 military tanker at 10.7 km, which radar saw but which sent no ADS-B position.
- **Positions:** about 1 s apart at the closest point.
- **Timing:** closest approach within about 3 s of WebTrak's, usually 0–2 s.
- **Receivers:** 28–60 OpenSky receivers heard each London City flight as it passed NMT6.
- **Heights:** for the 19 London City departures at 550–800 m, OpenSky's GPS height above sea level and WebTrak's radar altitude agree to within about ±20 m. The median difference is about −3 m. The exception is PVD464, a small private jet, at −34 m. That meets the plan's target of agreeing to within about 30 m.
- **High overflights:** at 4,700–12,000 m, GPS heights are 20–83 m below the radar's. That's as expected for radar altitude, which comes from air pressure and takes no account of air temperature, with the error growing with height. It doesn't matter for the survey.

## Why not the REST API

On 6 November we also tried OpenSky's free REST API (`/flights/arrival`, `/flights/departure` and `/tracks/all`). It found the same 19 London City flights near NMT6 as WebTrak, to within about 2 s. But it was dropped, because:
- it can only find flights to or from one airport, not every aircraft in an area;
- its tracks are simplified, with points up to 112 s apart near NMT6;
- its heights come in 1000 ft steps, so they're no use for the survey;
- it has daily credit limits, and only goes back 30 days.

The script is in git history (`tools/opensky/nmt6_flights.py`, before it was removed) if it's ever needed.

## How the sources compare

| | Garden Pi ([`tools/adsb`](../adsb/README.md)) | OpenSky research database | Home receiver about 15 km away |
|---|---|---|---|
| Position and height | Every message, full resolution | About 1 s, full resolution | Every message, full resolution |
| Coverage near NMT6 | Almost certain | 33 of 34 on 5 Nov (the missing one sent no ADS-B), 28–60 receivers per flight | Aircraft only 1–3° above the horizon; the lowest arrivals may be blocked |
| Can we tell what was missed? | Yes, from its health log | No | Yes, from its health log |
| Clock | Our GPS | OpenSky's receivers | Our GPS, if fitted |
| History | From when it's installed | Back to 2013 | From when it's installed |
| Terms | Ours | Research licence | Ours |

The research database makes OpenSky a strong second source. It covers periods before the Pi is installed, fills gaps when the Pi is down, and lets us check the Pi's coverage independently. The garden Pi stays the main record for the Fusion trial and survey, because it's the only source whose completeness and clock we can check ourselves.

## Next steps

1. Repeat the comparison over more periods: both runways, both arrivals and departures, and evenings and weekends. Check that the coverage and heights hold.
2. Query `readsb_mlat_sv` as well, for aircraft that don't send ADS-B positions.
3. Check the looked-up types against the airport's records, especially to tell an `A20N` from an `A320`.
4. Add OpenSky as a survey source like [adsb.lol](../adsb/docs/traces.md): convert it to the logger's hourly files, so that `adsb analyse` and the match check page can read it unchanged. Then compare it with the garden Pi, flight by flight, in the Fusion trial.

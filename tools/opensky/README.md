# OpenSky: aircraft near NMT6

These scripts get the aircraft that passed near NMT6 (St Pauls Church, Thamesmead) from the [OpenSky Network](https://opensky-network.org), and compare them with the WebTrak data saved by [`tools/webtrak`](../webtrak/README.md).

| Script | Source | Use it for |
|---|---|---|
| `nmt6_trino.py` | OpenSky's research database (Trino) | **The main one.** Every aircraft in the area, with a position about once a second and full-resolution heights. Needs research access |
| `nmt6_flights.py` | The free REST API | London City flights only, and their times. Its tracks are simplified and its heights come in 1000 ft steps |

## Research database: `nmt6_trino.py`

```bash
tools/opensky/.venv/bin/python tools/opensky/nmt6_trino.py --from 2026-11-05T08:01Z --to 2026-11-05T11:01Z [--radius 3000] [--geoid 45]
```

For each hour of the period, the script runs one query on `state_vectors_data4` for every aircraft in a box about 5 km either side of NMT6, whichever airport it uses. It keeps each position once, at the time OpenSky received it, and drops aircraft on the ground. It splits each aircraft's positions into passes and works out each pass's closest approach to NMT6. Passes that came within `--radius` (default 3000 m, as WebTrak) are written to `data/nmt6-trino-<from>.csv`, which git ignores. It then pairs them with WebTrak's radar tracks by time, to within 90 s, and lists each one's NMT6 event and the height difference.

For each pass it gives:
- the closest ground distance,
- GPS height above sea level (`geoaltitude` minus `--geoid`),
- uncorrected pressure altitude,
- the gap between OpenSky's positions at the closest point,
- the number of receivers that heard it.

### Setup

Research access is free for university researchers, but OpenSky has to approve it (My OpenSky → Request Data Access). Then:

```bash
cd tools/opensky
python3 -m venv .venv && .venv/bin/pip install pyopensky   # .venv is ignored by git
```

[pyopensky](https://github.com/junzis/pyopensky) is the client OpenSky recommends. It's the only package outside the standard library in this repository, and it is kept in `tools/opensky`. `tools/adsb` still uses only the standard library, so the Pi needs nothing installed.

**Login:** Trino uses your OpenSky **account username and password**, not the REST API's client ID and secret. Put them in pyopensky's `settings.conf`, and keep the file private (`chmod 600`). On a Mac it's at `~/Library/Application Support/pyopensky/settings.conf`:

```ini
[default]
username = your opensky username, in lower case
password = your password
```

If they're blank, pyopensky opens a browser to log in. Never put them in this repository.

### OpenSky's rules for queries

There are no API credits. Instead, OpenSky limits the load on its shared server, and it suspends accounts that keep ignoring [its guidelines](https://openskynetwork.github.io/opensky-api/trino.html). The script keeps to them:

- **Partition filter:** every query filters on the `hour` partition, as well as on time and a small latitude/longitude box. Trino rejects queries without one.
- **Size:** one query per hour, run one at a time. Each user may have at most 2 queries running and 2 queued. A query may run for at most 30 minutes and scan at most 100 GB.
- **Caching:** pyopensky saves each result (in `~/Library/Caches/opensky` on a Mac), so a rerun doesn't query again.
- **Stale states:** `time - lastcontact <= 15` drops the states OpenSky keeps for up to 300 s after it last heard an aircraft.

Three hours near NMT6 took four queries, a few seconds each, and returned about 7,700 state vectors.

Some periods are missing from OpenSky's data because of outages. Two of them fall in 2026: 2 January 19:00 to 3 January 18:00, and 24 January 08:00–17:00 UTC. Its processing changed on 13–14 August 2026, so results from before and after then may differ.

### Things to know about the data

- **Repeated positions:** a state vector repeats the last position until a new one arrives. The script uses `lastposupdate` as each position's time and keeps each position once.
- **GPS height:** `geoaltitude` is height above the WGS84 ellipsoid. Subtract the geoid height (about 45 m in London) to get height above sea level, as WebTrak gives.
- **Pressure altitude:** `baroaltitude` is pressure altitude (1013.25 hPa) and needs a QNH correction, as `tools/adsb` does. On 5 November it read about 90–100 m below GPS height near NMT6.
- **Aircraft without ADS-B:** the state vectors only include aircraft that send ADS-B. `readsb_mlat_sv` has multilateration (MLAT) positions, worked out from the timing of signals at several receivers, for some aircraft that send no position. The script doesn't query it yet.
- **Aircraft type:** OpenSky doesn't give one. Look up `icao24` in an aircraft database (OpenSky's own, or tar1090-db as readsb uses).
- **Licence:** OpenSky's research terms limit what can be published or redistributed. Publish summaries and cite OpenSky, not the raw state vectors.

### First comparison, 5 November 2026, 08:01–11:01 UTC

- **Matches:** 33 aircraft passed within 3 km of NMT6. WebTrak had all 33, plus one OpenSky didn't: a KC-135 military tanker at 10.7 km, which radar saw but which sent no ADS-B position.
- **Positions:** about 1 s apart at the closest point.
- **Timing:** closest approach within about 3 s of WebTrak's, usually 0–2 s.
- **Receivers:** 28–60 OpenSky receivers heard each London City flight as it passed NMT6.
- **Heights:** for the 19 London City departures at 550–800 m, OpenSky's GPS height above sea level and WebTrak's radar altitude agree to within about ±20 m. The median difference is about −3 m. The exception is PVD464, a small private jet, at −34 m. That meets the plan's target of agreeing to within about 30 m.
- **High overflights:** at 4,700–12,000 m, GPS heights are 20–83 m below the radar's. That's as expected for radar altitude, which comes from air pressure and takes no account of air temperature, with the error growing with height. It doesn't matter for the survey.

## Free REST API: `nmt6_flights.py`

```bash
python3 tools/opensky/nmt6_flights.py --from 2026-11-05T08:01Z --to 2026-11-05T11:01Z [--radius 3000]
```

The script gets EGLC arrivals and departures from `/flights/arrival` and `/flights/departure`, then fetches each flight's track from `/tracks/all` and works out its closest approach to NMT6. It uses only the standard library and writes to `data/nmt6-<from>.csv`.

**Credentials:** an API client from your OpenSky account page, set as `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`, or saved in `~/.config/opensky/credentials.json` (`{"clientId": ..., "clientSecret": ...}`, mode 600).

**Limits:**
- **Credits:** tracks, flights and live states each have their own daily allowance (4,000 credits for a standard user). A historical track costs 30 credits, so the allowance covers about 133 flights a day.
- **Airport only:** only flights to or from EGLC are found, because the API can't search past times by area.
- **Simplified tracks:** the tracks endpoint is experimental. It only adds a point when the aircraft turns more than 2.5° or changes height by more than 100 m, and at least every 15 minutes. Heights come in 1000 ft steps.

On 5 November it found the same 19 London City flights near NMT6 as WebTrak, to within about 2 s and usually within 100 m. But its points were up to 112 s apart, and its heights couldn't be used.

## How the sources compare

| | Garden Pi ([`tools/adsb`](../adsb/README.md)) | OpenSky research database | Free REST API | Home receiver about 15 km away |
|---|---|---|---|---|
| Position and height | Every message, full resolution | About 1 s, full resolution | Simplified; 1000 ft heights | Every message, full resolution |
| Coverage near NMT6 | Almost certain | 33 of 34 on 5 Nov (the missing one sent no ADS-B), 28–60 receivers per flight | London City flights only | Aircraft only 1–3° above the horizon; the lowest arrivals may be blocked |
| Can we tell what was missed? | Yes, from its health log | No | No | Yes, from its health log |
| Clock | Our GPS | OpenSky's receivers | OpenSky's receivers | Our GPS, if fitted |
| History | From when it's installed | Back to 2013 | 30 days | From when it's installed |
| Terms | Ours | Research licence | API terms | Ours |

The research database makes OpenSky a strong second source. It covers periods before the Pi is installed, fills gaps when the Pi is down, and lets us check the Pi's coverage independently. The garden Pi stays the main record for the Fusion trial and survey, because it's the only source whose completeness and clock we can check ourselves.

## Next steps

1. Repeat the comparison over more periods: both runways, both arrivals and departures, and evenings and weekends. Check that the coverage and heights hold.
2. Query `readsb_mlat_sv` as well, for aircraft that don't send ADS-B positions.
3. Look up aircraft types from `icao24`.
4. Add OpenSky as a survey source like [adsb.lol](../adsb/docs/traces.md): convert it to the logger's hourly files, so that `adsb analyse` and the match check page can read it unchanged. Then compare it with the garden Pi, flight by flight, in the Fusion trial.

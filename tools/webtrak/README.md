# WebTrak scraper for London City Airport (LCY)

This tool downloads nearly live and historical noise and flight track data from London City Airport's public WebTrak system ([eu.webtrak.aero/lcy](https://eu.webtrak.aero/lcy)), focusing on **NMT6** (St Paul's Church, Thamesmead).

It provides the counterpart dataset called for in the [Thamesmead Garden Measurement Plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md) to compare noise levels measured in the garden against the airport's permanent monitor directly under the RWY 27 approach path.

## How WebTrak works

WebTrak is powered by Envirosuite (formerly Brüel & Kjær EMS). The web application loads flight tracks and noise measurements in 30-second blocks (`.mobile` chunk endpoints):

- **Live delay:** WebTrak runs approximately **25 minutes behind real time** for community display. The "current" or "live" view is the latest 30-second chunk published.
- **Noise monitors (NMT):** Each chunk contains 1-second sound levels (dB) per active monitor, plus calculated noise events (`LAmax`, `SEL`, `Leq`, `EPNL`, duration, and start/end times).
- **Gaps at 00:00 and 12:00:** for about 40 s from midnight and noon every monitor reports 20.0 dB with flag `9` (possibly an automatic calibration check; WebTrak doesn't say). That is a placeholder, not a measurement, so those seconds are saved with a blank `level_db`.
- **Radar tracks:** 4-second position updates with callsign, ICAO type, direction (Arrival/Departure/Other), airport, latitude/longitude, height above aerodrome (metres), and ground speed (m/s). WebTrak gives a callsign only for LCY's scheduled flights; for other aircraft the `callsign` column holds the registration, or is blank if there is none either.
- **NMT6:** Listed as monitor ID `106` (*"St Pauls Church, Thamesmead"*, 51.50535° N, 0.11075° E).

All network calls use only Python's standard library (`urllib`). Requests are spaced out (1 s apart when following, 2 s for historical fetches, timed from the end of each reply), replies are gzipped (about 6 KB a chunk instead of 30 KB), retries back off and honour `Retry-After`, and every chunk is cached so it is downloaded only once.

WebTrak keeps a rolling window of about 18 months; `range` shows the current one.

## Quick start

Run from `tools/webtrak` (or from the project root with `PYTHONPATH=tools/webtrak`):

```bash
cd tools/webtrak

# The web app: start downloads, watch their progress, see statistics (http://127.0.0.1:8765)
python3 -m webtrak serve

# Run tests (no network calls)
python3 -m unittest discover tests

# Check available data range and current delay
python3 -m webtrak range

# List all airport monitors
python3 -m webtrak monitors

# Follow NMT6 live (polls every 30 s for new chunks, backfilling the last hour)
python3 -m webtrak follow

# Fetch a historical period (in local airport time)
python3 -m webtrak fetch --from "2026-11-05 08:00" --to "2026-11-05 10:00"

# Several monitors from the same downloads
python3 -m webtrak fetch --from "2026-11-05 08:00" --to "2026-11-05 10:00" --nmt 106,103

# Check the saved NMT6 data for gaps and anything that looks wrong (reads the files only)
python3 -m webtrak quality
python3 -m webtrak quality --from "2026-11-05 08:00" --to "2026-11-05 11:00" --json report.json
```

### Checking the data (`quality`)

`quality` reads a monitor's saved files (and the raw cache, for the radar status) and reports what is missing and what looks wrong. It never downloads and never changes a file. Each check is marked `ok`, `info` (worth knowing, not a fault) or `WARN`, with a few examples. The thresholds are rules of thumb, listed at the top of `webtrak/quality.py`, and a warning is a reason to look, not proof that the data is wrong.

- **Coverage:** missing chunks between the first and last saved one; chunks short of 30 s or with repeated seconds; radar not online; events still waiting for radar.
- **Levels:** no-measurement runs (the 00:00 and 12:00 placeholders counted apart); levels outside 25–110 dB; the same level for 30 s or more; steps of 15 dB or more in one second; wrong UTC offsets.
- **Events:** repeats; SEL that isn't Leq + 10 log10(duration); LAmax that isn't the highest 1 s level; flag 1 seconds outside every event; aircraft events with no aircraft matched, or matched more than 1.5 km away; non-aircraft events with an aircraft within 1 km; LAmax more than 5 s before or 20 s after the closest approach; events whose radar window isn't all saved.
- **Radar:** repeated positions, gaps within a track, missing heights, implausible heights or speeds.

Flag 1 marks only aircraft (class 1) events: in the data so far, the seconds of class 5 events keep flag 5.

### The web app

`serve` runs a small web app on this computer only (standard library, no installs). From it you can start a `fetch` for a period or `follow` live, for one or several monitors, with an estimate of how many chunks need downloading and how long it will take. You can then watch each download's progress, rate and time left, see which half-minutes of a day each monitor has saved, and look at statistics for any saved period: LAeq, L10/L50/L90, the aircraft share of the sound energy, a chart of LAeq with every event's LAmax (drag across it to zoom in, down to a minute; its LAeq buckets get finer as you zoom, down to 1 s, and Back, Zoom out, Earlier and Later move around), 15-minute figures, results by aircraft type, and the list of events.

Downloads run as ordinary `fetch`/`follow` processes, so closing the app doesn't stop them; Stop finishes the current chunk and exits cleanly (as Ctrl-C now does on the command line). A download started from the command line shows as "being written" on its monitor, and the app won't start a second one there.

`fetch` also gets 90 s either side of the period, so events near its ends are matched against all the radar around them. It carries on past a chunk that fails, and stops only after 3 failures in a row. Run the same command again to pick up whatever is missing; chunks already saved or cached are not downloaded again. `follow` retries missing chunks within its `--backfill` window, waiting 1, 2, 4 … up to 30 minutes between attempts. Only one process at a time can write to a monitor's folder.

## Output data structure

Data is stored under `tools/webtrak/data/<site>/` (git-ignored):

```text
tools/webtrak/data/lcy/
├── jobs/                            # Downloads started from the web app: settings and logs
├── raw/YYYY-MM-DD/<handle>.txt.gz   # Each chunk as received (UTC day), shared by all monitors; --no-raw turns it off
└── nmt106/
    ├── state.json          # Saved chunk ranges, and events still waiting for radar
    ├── events.csv          # Noise events matched to closest aircraft approach
    ├── levels/
    │   └── YYYY-MM-DD.csv  # 1-second noise levels (UTC and local timestamps, dB, flag)
    └── aircraft/
        └── YYYY-MM-DD.csv  # Radar positions within 3 km radius of the monitor
```

Each chunk holds every monitor and all radar, so the raw cache lets you add monitors later without downloading again. It takes about 8 KB a chunk, roughly 23 MB a day or 700 MB a month.

### Event matching (`events.csv`)

For each noise event reported by NMT6, the scraper looks at the radar tracks within the `--radius` during the 60 seconds either side of the `LAmax` time, and picks the one that came closest in slant distance. Radar positions are 4 s (about 300 m) apart, so the closest point is looked for along the line between neighbouring positions, not only at the positions themselves.

An event is listed in one or two chunks around its time (the one where it starts, the one where it ends, or both), so the radar for the minute after its LAmax may still be to come: the event waits (in `state.json`, so a restart doesn't lose it) until those chunks are saved, and is matched then. When following, an event whose chunks never arrive is matched with what there is once the data is 10 minutes further on; a `fetch` matches the events in its period that are still waiting at the end. The match identifies:
- Matched aircraft callsign (or registration), aircraft type, direction (`A`/`D`/`O`), airport, track id.
- Closest approach: ground distance (m), height (m), slant distance (m), and how many seconds `LAmax` came after it. `candidates` is the number of tracks in range.

### Output files schema

- **`levels/YYYY-MM-DD.csv`**: `time_utc`, `time_local`, `level_db`, `flag` (flag `1` during an aircraft event, `5` otherwise, `9` no measurement). `level_db` is blank when there was no measurement.
- **`aircraft/YYYY-MM-DD.csv`**: `time_utc`, `time_local`, `track`, `callsign`, `type`, `registration`, `direction`, `airport`, `origin`, `destination`, `lat`, `lon`, `height_m`, `altitude_m`, `speed_ms`, `distance_m`, `slant_m`.
- **`events.csv`**: `start_utc`, `start_local`, `lmax_time_local`, `end_local`, `duration_s`, `lmax_db`, `sel_db`, `leq_db`, `epnl_db`, `event_class`, `callsign`, `type`, `direction`, `airport`, `track`, `closest_time_local`, `closest_distance_m`, `closest_height_m`, `closest_slant_m`, `lmax_after_closest_s`, `candidates`.

## Terms and polite scraping

WebTrak data is provided for personal and non-commercial community engagement. This tool sets an honest user-agent header, asks for compressed replies and stores data locally.

There is no published rate limit, and the server sends no rate-limit headers, but it serves WebTrak for many airports. Following live (one chunk every 30 s) is what an open browser tab does. A historical fetch is much heavier: a day is 2,880 requests (about 4½ hours at the default 2 s, as WebTrak takes about 3.5 s to answer each) and a month about 86,000. For long periods, fetch only what lines up with the garden measurements, run it overnight UK time, and consider asking London City Airport for the NMT6 data directly.

### What the server sees

Every request is built in `Client._request` (`webtrak/client.py`) and sends:

| Header | Value |
|---|---|
| `User-Agent` | `thamesmead-noise-survey/0.1 (personal, non-commercial noise research)`: the project and its purpose, but no name, email or URL |
| `Referer` | `https://eu.webtrak.aero/lcy` (the site being looked at) |
| `Accept-Encoding` | `gzip` |

`urllib` adds `Host` and `Connection: close` itself, and `Content-Type` on POSTs. There are no cookies, sessions, tokens or account details, so requests are anonymous and not linked to each other. Beyond the headers, the server sees:

- **The IP address.** This is the real identifier: it's tied to the ISP and roughly to a location.
- **That it's a script.** Python's TLS handshake and a fresh connection for every request look nothing like a browser.
- **The pattern.** `.mobile` chunks in time order, at steady 1–2 s intervals, for hours at a time.

So WebTrak can tell this is an automated research tool from one IP, but nothing ties it to a person unless they trace the IP. If we're happy to be contacted, a contact address can go in the user-agent (`USER_AGENT` in `client.py`), e.g. `thamesmead-noise-survey/0.1 (+mailto:…; non-commercial noise research)`, which is the usual courtesy for research scrapers.

### Why we don't disguise it as a browser

We considered making the scraper look like a person using a browser (a browser user-agent, random timing) and decided against it:

- **It would only hide the scraper.** The point of a browser disguise is to stop Envirosuite seeing automated traffic. That would also stop them throttling it, which they may reasonably want to do.
- **It wouldn't work.** A day of history is 2,880 requests and a month about 86,000, far more than any person sends. The TLS handshake gives Python away anyway.
- **It's riskier for the project.** If they object to an honest scraper, they can block it or get in touch. A disguised one looks like evasion, which matters if we later want London City Airport's cooperation.

If requests start failing (403s, 429s, blocks), the fix is slower `--delay`, shorter fetch periods or overnight runs, not camouflage. A small random jitter on the delay, keeping the honest user-agent, would be fine if we want requests to arrive less regularly.

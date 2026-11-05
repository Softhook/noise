# WebTrak scraper for London City Airport (LCY)

This tool downloads nearly live and historical noise and flight track data from London City Airport's public WebTrak system ([eu.webtrak.aero/lcy](https://eu.webtrak.aero/lcy)), focusing on **NMT6** (St Paul's Church, Thamesmead).

It provides the counterpart dataset called for in the [Thamesmead Garden Measurement Plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md) to compare noise levels measured in the garden against the airport's permanent monitor directly under the RWY 27 approach path.

## How WebTrak works

WebTrak is powered by Envirosuite (formerly Brüel & Kjær EMS). The web application loads flight tracks and noise measurements in 30-second blocks (`.mobile` chunk endpoints):

- **Live delay:** WebTrak runs approximately **25 minutes behind real time** for community display. The "current" or "live" view is the latest 30-second chunk published.
- **Noise monitors (NMT):** Each chunk contains 1-second sound levels (dB) per active monitor, plus calculated noise events (`LAmax`, `SEL`, `Leq`, `EPNL`, duration, and start/end times).
- **Radar tracks:** 4-second position updates with callsign, ICAO type, direction (Arrival/Departure/Other), airport, latitude/longitude, height above aerodrome (metres), and ground speed (m/s).
- **NMT6:** Listed as monitor ID `106` (*"St Pauls Church, Thamesmead"*, 51.50535° N, 0.11075° E).

All network calls use only Python's standard library (`urllib`). Requests are spaced out (1 s apart when following, 2 s for historical fetches, timed from the end of each reply), replies are gzipped (about 6 KB a chunk instead of 30 KB), retries back off and honour `Retry-After`, and every chunk is cached so it is downloaded only once.

WebTrak keeps a rolling window of about 18 months; `range` shows the current one.

## Quick start

Run from `tools/webtrak` (or from the project root with `PYTHONPATH=tools/webtrak`):

```bash
cd tools/webtrak

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
```

`fetch` carries on past a chunk that fails, and stops only after 3 failures in a row. Run the same command again to pick up whatever is missing; chunks already saved or cached are not downloaded again. `follow` retries missing chunks within its `--backfill` window, waiting 1, 2, 4 … up to 30 minutes between attempts. Only one process at a time can write to a monitor's folder.

## Output data structure

Data is stored under `tools/webtrak/data/<site>/` (git-ignored):

```text
tools/webtrak/data/lcy/
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

For each noise event reported by NMT6, the scraper correlates nearby radar tracks within ±60 seconds of the `LAmax` peak time. An event is listed in one or two chunks around its time (the one where it starts, the one where it ends, or both), so the radar for the minute after its LAmax may still be to come: the event waits (in `state.json`, so a restart doesn't lose it) until those chunks are saved, and is matched then. If they never arrive it is matched with what there is once the data is 10 minutes further on, or at the end of a `fetch`. The match identifies:
- Matched aircraft callsign, aircraft type, direction (`A`/`D`/`O`), origin/destination.
- Closest approach: ground distance (m), height (m), slant distance (m), and timing difference relative to `LAmax`.

### Output files schema

- **`levels/YYYY-MM-DD.csv`**: `time_utc`, `time_local`, `level_db`, `flag` (flag `1` during an event, `5` background).
- **`aircraft/YYYY-MM-DD.csv`**: `time_utc`, `time_local`, `track`, `callsign`, `type`, `registration`, `direction`, `airport`, `origin`, `destination`, `lat`, `lon`, `height_m`, `altitude_m`, `speed_ms`, `distance_m`, `slant_m`.
- **`events.csv`**: `start_utc`, `start_local`, `lmax_time_local`, `end_local`, `duration_s`, `lmax_db`, `sel_db`, `leq_db`, `epnl_db`, `event_class`, `callsign`, `type`, `direction`, `airport`, `track`, `closest_time_local`, `closest_distance_m`, `closest_height_m`, `closest_slant_m`, `lmax_after_closest_s`, `candidates`.

## Terms and polite scraping

WebTrak data is provided for personal and non-commercial community engagement. This tool sets an honest user-agent header, asks for compressed replies and stores data locally.

There is no published rate limit, and the server sends no rate-limit headers, but it serves WebTrak for many airports. Following live (one chunk every 30 s) is what an open browser tab does. A historical fetch is much heavier: a day is 2,880 requests (about 2½ hours at the default 2 s) and a month about 86,000. For long periods, fetch only what lines up with the garden measurements, run it overnight UK time, and consider asking London City Airport for the NMT6 data directly.

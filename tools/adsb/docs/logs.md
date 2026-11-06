# What gets logged

The logger (`adsb log`) writes two kinds of file, adding to the current one as it goes. `adsb status` and the analysis only ever read them.

```text
/var/lib/adsb-logger/
  adsb/2026-11-05T14.jsonl.gz      one file per UTC hour; a restart adds .1, .2 and so on
  health/2026-11-05.jsonl          a health record every 5 minutes, and at each event
```

- **ADS-B files:** each line is one JSON object, exactly as readsb sent it. Lines are kept if the position is within `max_km` of the garden, if there's no position, or if the line can't be read. The files are flushed at least once a minute. A new file is also started when the clock becomes synchronised or stops being so, so each file is wholly one or the other.
- **Health log:** line counts, aircraft seen, connection events, clock status from `chronyc`, CPU temperature, throttling, uptime, free disk space and the receiver's signal levels (below). The logger checks the clock every 10 seconds until it's synchronised, then every minute, and records each change as an event. It stops writing when the disk is nearly full. After a write error it records the error and retries a minute later. After three in a row it exits, so systemd starts it afresh. If the SSD itself has failed, the watchdog reboots the Pi (see [pi-setup.md](pi-setup.md#3-the-ssd-at-home)).
- **Open files:** while running, the logger lists the files it's writing to in `/run/adsb-logger/open-files`, in memory, so `make pi-collect` leaves them for the next visit.

Each health record also has `boot_id`, the kernel's id for the boot, and `uptime_s`. After a power cut the clock starts behind, so records from before the cut and after the boot overlap in time. The analysis takes each boot's records in uptime order to find when the clock wasn't synchronised, in the times the data was actually stamped with.

Each health record's `receiver` holds readsb's statistics for its last 5 minutes, from `/run/readsb/stats.json`, or `null` if readsb wasn't writing them. They show, afterwards, whether flights may have been missed because the gain was too high, rather than because of the logger:

| Field | Meaning |
|---|---|
| `gain_db` | The radio's gain in dB |
| `messages` | Messages accepted |
| `strong_signals`, `strong_share` | Messages stronger than -3 dBFS, and their share of `messages` |
| `signal_dbfs`, `noise_dbfs`, `peak_signal_dbfs` | Mean signal, noise and peak signal, in dBFS (always negative) |
| `samples_dropped` | Sample blocks readsb couldn't process. Anything above 0 means the CPU is overloaded |
| `age_s` | How old readsb's 5 minutes were when read |

Each health record's `near` lists the aircraft that came within `near_km` (2 km) of the garden below `near_max_ft` (3,000 ft) since the previous record, as `{hex: closest distance in km}`. `near_limits` records the two settings. `adsb status` counts these as passes each day, so a site visit shows whether the flights we need are still being caught. It's only a quick check: the analysis works from the full log.

These are the ADS-B fields we use. readsb leaves out any field it doesn't have.

| Field | Meaning |
|---|---|
| `now` | Time the message was received, in Unix seconds (UTC), from the Pi's clock |
| `hex` | The aircraft's 24-bit ICAO address. A leading `~` means it isn't an ICAO address |
| `flight` | Callsign, which may have trailing spaces |
| `r`, `t`, `dbFlags` | Registration, ICAO type code and database flags, from the aircraft database |
| `lat`, `lon`, `seen_pos` | Position and its age in seconds |
| `nic`, `rc` | Position quality |
| `alt_baro` | Pressure altitude in feet, or `"ground"`. Don't use it without a QNH correction |
| `alt_geom` | GNSS altitude in feet above the WGS84 ellipsoid, not above sea level |
| `nav_qnh` | Pressure setting in hPa selected in the aircraft, if it sends one |
| `gs`, `track` | Ground speed in knots and track in degrees |

Full definitions are in [readsb's JSON README](https://github.com/wiedehopf/readsb/blob/dev/README-json.md).

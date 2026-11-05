# What gets logged

The logger (`adsb log`) writes two kinds of file, adding to the current one as it goes. `adsb status` and the analysis only ever read them.

```text
/var/lib/adsb-logger/
  adsb/2026-11-05T14.jsonl.gz      one file per UTC hour; a restart adds .1, .2 and so on
  health/2026-11-05.jsonl          a health record every 5 minutes, and at each event
```

- **ADS-B files:** each line is one JSON object, exactly as readsb sent it. Lines are kept if the position is within `max_km` of the garden, if there's no position, or if the line can't be read. The files are flushed at least once a minute.
- **Health log:** line counts, aircraft seen, connection events, clock status from `chronyc`, CPU temperature, throttling, uptime and free disk space. The logger checks the clock every 10 seconds until it's synchronised, then every minute, and records each change as an event. It stops writing when the disk is nearly full. After a write error it records the error and retries a minute later, rather than stopping.

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

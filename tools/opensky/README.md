# OpenSky: London City flights near NMT6

`nmt6_flights.py` gets London City's flights near NMT6 (St Pauls Church, Thamesmead) from the [OpenSky Network](https://opensky-network.org) REST API. It compares them with the WebTrak data saved by [`tools/webtrak`](../webtrak/README.md). It uses only Python's standard library.

```bash
python3 tools/opensky/nmt6_flights.py --from 2026-11-05T08:01Z --to 2026-11-05T11:01Z [--radius 3000]
```

For each EGLC arrival and departure around the period, the script fetches the flight's OpenSky track and works out its closest approach to NMT6, interpolating between track points. It keeps the flights that came within `--radius` of NMT6 during the period, and writes them to `data/nmt6-<from>.csv`, which git ignores. It then pairs them with WebTrak's radar tracks by time, to within 90 s, and lists each flight's NMT6 event.

**Credentials** come from `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`, or from `~/.config/opensky/credentials.json` (`{"clientId": ..., "clientSecret": ...}`, mode 600). Never put them in this repository.

**Credits:** a 3-hour period used about 1,350 of the 4,000 daily API credits, so the API covers 6–9 hours of data a day.

## First comparison, 5 November 2026, 08:01–11:01 UTC

- **Flights:** 19 London City flights came within 3 km of NMT6 in both OpenSky and WebTrak, with none in only one of them. All 19 were departures, and each had an NMT6 event (67.6–77.3 dB LAmax).
- **Time:** the times of closest approach agree to within about 2 s.
- **Distance:** closest ground distances usually agree to within about 100 m. The worst is PVD464 (137 m in OpenSky, 240 m in WebTrak), where OpenSky's track points are 112 s apart.
- **Callsigns:** OpenSky gives the ICAO callsigns used on the radio (CFE76JZ, KLC978), and WebTrak gives flight numbers (BA8491, KL978), so flights are paired by time.
- **Heights:** OpenSky's track heights are pressure altitudes in 1000 ft (304.8 m) steps, so they can't be used.

## How good is each source?

**The free REST API** is what this script uses. It identifies the flight and its time well, but its tracks are simplified for drawing on a map:

| | What the aircraft broadcasts | What `/tracks/all` returns |
|---|---|---|
| Position | About 2 a second, from its GPS, usually to 10–30 m | Points where the path changes; 1–112 s apart near NMT6 |
| Height | Pressure altitude in 25 ft steps, plus GPS height | Rounded to 1000 ft |
| Type | Not broadcast; looked up from the ICAO address | Not given (look up `icao24` in an aircraft database) |

The API can't search past times by area, so only flights to or from EGLC are found.

**OpenSky's research database** (Trino, by application) has a position about once a second with full-resolution pressure and GPS heights. It has the same accuracy as our own receiver. It still differs from a receiver in the garden:

- **Coverage:** it holds only what volunteers' receivers heard, and we can't tell whether a pass was missed or a receiver was offline.
- **Stale positions:** each state vector carries the last position heard, which can be several seconds old. Use `lastposupdate` to filter these out.
- **Clock:** timestamps come from OpenSky's receivers. Many are GPS-synchronised, but we can't confirm it for a given flight.
- **Licence:** its research terms limit what can be published or redistributed.

**A home receiver about 15 km away** gets the same messages as the garden, so positions and heights are just as accurate. But aircraft over Thamesmead at 300–800 m are only 1–3° above its horizon. Buildings or trees on the line to Thamesmead can block them, and the lowest arrivals (300–400 m) are the most likely to be missed. Antenna height and a clear view towards Thamesmead matter more than antenna quality. Unlike OpenSky, it has our own GPS-timed clock and health log, so its coverage can be measured.

**The garden Pi** ([`tools/adsb`](../adsb/README.md)) hears every pass with the aircraft nearly overhead, and it is timed by its own GPS clock. It stays the main source for the Fusion trial and survey.

## Next steps

1. When research access is approved, repeat this comparison from the research database, and check its heights against WebTrak's radar.
2. Measure a home receiver's coverage: run `adsb log` with `site.json` set to NMT6's public coordinates, then compare the passes it hears with WebTrak's NMT6 events.
3. During the Fusion trial, compare OpenSky with the garden Pi flight by flight. If it catches every pass with the right heights, use it for gaps and for periods before the Pi.
4. Add OpenSky as a survey source like [adsb.lol](../adsb/docs/traces.md): convert it to the logger's hourly files, so that `adsb analyse` and the match check page can read it unchanged.

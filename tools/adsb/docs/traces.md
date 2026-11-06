# adsb.lol's archive

[adsb.lol](https://adsb.lol) publishes every aircraft's track from its whole network of volunteer receivers, one gzipped JSON file per aircraft per UTC day, in readsb's track format. `adsb traces` turns those files into the logger's hourly format, so `adsb analyse` reads them unchanged. Since they come from other receivers, they give an independent check on our coverage and clock, and can fill a day our Pi was off.

The track files are thinned: readsb keeps a point at least every 30 s, and more often when the track or height changes. In a test on the simulated day, thinned to one point every 4 s, the analysis found the same 309 flights, with the same labels, as from the full log. Our logger's stream is still the main record.

We don't keep readsb's track files on our own Pi: they'd be a second copy of the same data from the same receiver (see the [plan](PLAN.md#4-logger-adsb-log)).

## Converting

```bash
python3 -m adsb traces --config site.json --out OUT/adsb --source "WHERE FROM" INPUT [INPUT ...]
python3 -m adsb analyse --config site.json --logs OUT/adsb --out OUT/results --weather eglc.csv
```

`INPUT` is any of these:

- an unpacked archive, or one day of readsb's `globe_history` folder
- a `.tar` archive
- every part of a split archive (`.tar.aa`, `.tar.ab`, ...), which are read in order without unpacking

Only positions within the logger's `max_km` of the site are kept (or `--max-km`). `OUT/adsb` must be empty. It gets one `.jsonl.gz` file per UTC hour and a `SOURCE.txt` that names the source, the inputs and the counts. The output says it's **not** the logger's own record, so it can't be mistaken for one. Keep each day in its own folder.

The analysis warns that there's no health log. That's expected: the clock check and the gap checks need the logger's health log, so for this data they aren't available.

Each line has the logger's field names. `seen_pos` is 0, `trace_flags` holds readsb's flags for the point (1 stale, 2 new leg, 4 geometric vertical rate, 8 geometric altitude), and `type` is the position's source, such as `adsb_icao` or `mlat`. `flight`, `squawk` and `category` carry forward from the last point that had them; quality fields such as `nic` and `rc` don't, so a point without them isn't filtered on them. See readsb's [trace format](https://github.com/wiedehopf/readsb/blob/dev/README-json.md).

## Downloading

[adsb.lol](https://adsb.lol) publishes each day's tracks from its whole network as GitHub releases, a day or so later, in one repository per year: [adsblol/globe_history_2026](https://github.com/adsblol/globe_history_2026). Each day comes as a split tar archive (`.tar.aa`, `.tar.ab`), with separate `prod` and `staging` releases. The repository's README says to use `staging` if `prod` is much smaller. Each archive is a copy of readsb's `globe_history` folder for that day. A day is about 4 GB (5 November 2026), because it covers the world, so download only the days you need. The data is under the [ODbL](http://opendatacommons.org/licenses/odbl/1.0/), so credit adsb.lol in anything published from it.

```bash
gh release download v2026.11.05-planes-readsb-prod-0 --repo adsblol/globe_history_2026 --dir data/adsblol/raw
python3 -m adsb traces --config site.json --out data/adsblol/2026-11-05/adsb \
    --source "adsb.lol prod 2026-11-05" data/adsblol/raw/v2026.11.05-planes-readsb-prod-0.tar.*
```

The conversion reads the whole archive, which takes a while for a day of the world. Once converted, the raw archive can be deleted.

What it's good for:

- **Coverage:** flights near the garden that adsb.lol has and we don't show what our antenna misses. This matters most in the 37-day survey, when WebTrak is only asked about single flights. In the [survey architecture](../../survey/ARCHITECTURE.md) it's a source like any other, used by `checks`.
- **Clock:** the same aircraft, in two independent sources, gives the time offset between them, as for WebTrak.
- **Gaps:** a day the Pi was off can still be analysed for flights, though without our own timing.

What it isn't:

- It's still ADS-B, so aircraft that don't transmit are missing from it too. Only WebTrak's radar or the airport's records find those.
- Its times come from other receivers' clocks, and its heights and types come from the same transmissions and database as ours. It's independent for coverage and timing, not for identity.

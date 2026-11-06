# Analysing the logs

Copy the logs to a laptop, recording checksums, and run the analysis on the copy.

The analysis measures everything from the site in the config's `site` section. That's the garden for our own logger, but it can be any point, such as a WebTrak monitor (see [`tools/opensky`](../../opensky/README.md#in-the-ads-b-viewer)). Three optional keys say what to call it:

| Key | Meaning |
|---|---|
| `name` | What the summary and the viewer call the site, such as `Garden` or `NMT6, St Pauls Church, Thamesmead`. Default `Site` |
| `label` | A short form for the map and the charts, such as `NMT6`. Default: `name` |
| `public` | `true` only if the site's location may be shown. The summary and the viewer then give its latitude and longitude. Leave it out for the garden |

1. Download EGLC METARs for the logged period from the [Iowa Environmental Mesonet archive](https://mesonet.agron.iastate.edu/request/download.phtml):

   ```bash
   python3 -m adsb metars --from 2026-11-05 --to 2026-11-06 --out eglc.csv
   ```

   It asks for a day either side of the period, since the analysis uses the latest report before each position. It uses the request we tested: routine and special reports, in UTC. `--station` changes the airport.

   A CSV with `time,qnh_hpa,temp_c` columns also works, for example from the Fusion's weather station.


2. Run the analysis, from `tools/adsb`:

   ```bash
   python3 -m adsb analyse --config site.json --logs LOG_COPY --out results --weather eglc.csv
   ```

   Add `--from 2026-11-05 --to 2026-11-06` to analyse one period, for example to make a smaller viewer for one day. The logs are read in time order and each flight is finished once its aircraft goes quiet. So memory use depends on how many aircraft are in the air at once, not on the length of the survey: about 40 MB for a simulated day.

## Outputs

- `flights.csv`: one row per flight.
- `positions.csv`: every position of flights labelled as arrivals or departures. Use `--all-positions` to include all flights.
- `summary.txt`: data gaps, damaged files, warnings and medians by label and aircraft type. A gap of over 30 minutes in the kept data is reported as `GAP` when data may have been lost, and as `QUIET` when the health log shows the logger connected and receiving throughout, so there were just no aircraft nearby. Without a health log, a gap is reported as `GAP ... unchecked`, because a quiet sky and lost data look the same. Logs converted from another source (`adsb traces`, `opensky logs`) have a `SOURCE.txt`. The summary then names the source and notes that no health log is expected, instead of warning about it. It also counts the lines stamped while the clock wasn't synchronised, and the lines skipped because their time was more than an hour outside their file's hour, which means a corrupt time.
- `viewer.html`: everything above, to explore in a browser. See [The viewer](#the-viewer).

## How each value is worked out

- **Position:** positions are converted to metres east and north of the site. Each position's time is when it was received, less its age.
- **Height:** two heights are worked out for every position:
  - **QNH height:** `alt_baro` corrected with the latest METAR QNH and temperature. METAR QNH is rounded down to the whole hPa, so 0.5 hPa is added back. The temperature correction scales the height by the ratio of actual to standard mean air temperature below the aircraft, which matters on cold days: about 4% at 15 °C below standard. Both can be turned off in the config's `analysis` section.
  - **Geometric height:** `alt_geom` minus `geoid_height_m` from the config. This is roughly 45 m in London, from memory, and needs confirming from a geoid model. Until it's set, only QNH heights are worked out.

  Each flight uses one source throughout, geometric where available. `median_qnh_minus_geometric_m` compares the two, and a flight is flagged `heights_disagree` when they differ by more than 30 m. Geometric is rejected in favour of QNH (`geometric_rejected`) only when the difference matches a known aircraft fault: sending height above sea level as geometric, which shows as a difference close to the geoid height. Other differences could be the weather's fault, so geometric is kept.
- **Offset from the site:** `lateral_offset_m` is the closest distance between the site and the track, measured along the ground. Straight lines are fitted to the positions and heights over 20 seconds either side of the closest point. This averages out position noise and the 25 ft altitude steps; the nearest single position would read short. `site_side` says which side of the track the site is on: north or south for east–west tracks, east or west for north–south ones.
- **Sound delay:** `closest_slant_m` is the closest straight-line distance between the aircraft and the microphone. `sound_delay_s` is that distance divided by the speed of sound, which is worked out from the METAR temperature. Each row of `positions.csv` has the time the sound left the aircraft and the time it reached the microphone. Use the arrival time to find where the aircraft was when the sound at LAmax left it.
- **Path:** `path_angle_deg` is fitted from height against distance along the track, within 3 km of the site. Distance is measured along a straight line, so position noise doesn't lengthen it. This should tell 5.5° from 4.49°. `label` gives `rwy27_arrival`, `rwy09_departure` or `other`, from heading, climb or descent, height and offset. This is a first rule of thumb, so check it against real flights.
- **Quality flags:**
  - `no_qnh`, `no_height`: QNH or height missing
  - `assumed_sound_speed`: no temperature, so 340.3 m/s was used
  - `gap_at_closest_point`: a gap in the track near the site
  - `closest_point_at_track_end`: the track ends before passing the site
  - `heights_disagree`: QNH and geometric heights differ by more than 30 m
  - `geometric_rejected`: QNH height used because geometric looked like the sea-level fault
  - `clock_not_synchronised`: the flight overlaps a period when the health log showed the clock unsynchronised

Go-arounds and missed approaches are labelled `other` without a specific flag. Look for them among `other` flights with a low closest point.

## The viewer

`viewer.html` opens in any browser, works offline and loads nothing from the internet. Hover over anything for details, and click to select a flight.

- **Tracks around the site:** a plan view in kilometres from the site, with rings at 1, 2 and 5 km. The site is marked with its `label`.
- **Height profile:** height above the microphone against distance east of the site.
- **By aircraft type:** one dot per flight for a chosen measure, such as path angle (with 4.49° and 5.5° marked), offset, height, distance or sound delay.
- **Flights table:** sortable, with a panel showing every value for the selected flight.
- **Warnings and summary:** from `summary.txt`.

The viewer is headed with the site's `name`. It has no latitudes or longitudes, only distances from the site, unless the site is marked `public`, when it shows the site's own. A viewer for the garden still shows exact offsets from the arrival path, though, so treat one made from real data as private.

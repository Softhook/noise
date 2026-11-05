# ADS-B flight logger for the Thamesmead noise survey

This folder is for a Raspberry Pi that records every aircraft near the Thamesmead garden. Its log lets us match each noise event from the Acoem Fusion to an aircraft's identity, type, track and height, as the [measurement plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md) requires.

The Pi logs locally, and its clock is set by a USB GPS receiver. Data is collected from it by hand, and nothing is sent to a flight-tracking network or other online service.

**Status:** the logger, analysis, simulator and viewer are written and pass their tests, but only on simulated data. Nothing has been run on the Pi or on real ADS-B data yet. See the [build plan](PLAN.md).

## How it works

```text
On the Pi:
Antenna -> Pro Stick Plus -> readsb --(JSON stream, TCP)--> adsb_logger.py -> hourly .jsonl.gz files
                                |                              |
                                +--> tar1090 (live map)         +--> health log every 5 minutes
USB GPS -> gpsd -> chrony (sets the Pi's clock)

Afterwards, on a laptop:
logs + EGLC METARs -> adsb_analyse.py -> flights.csv, positions.csv, summary.txt
```

| File | Purpose |
|---|---|
| `adsb_logger.py` | Saves readsb's stream and the health log. Runs on the Pi |
| `adsb_status.py` | Checks the logger on a site visit: running, clock, disk, and whether data is being kept |
| `adsb_analyse.py` | Builds flights from the logs, with heights, offsets from the garden and sound delay, and writes a viewer |
| `viewer_template.html` | The viewer page, which the analysis fills in with data |
| `adsb_simulate.py` | Makes a simulated day of logs with known answers, and can act as a fake readsb |
| `site.example.json` | Config template. The location is a placeholder |
| `adsb-logger.service` | Runs the logger at boot |
| `test_*.py` | Tests, using made-up data |

All the scripts use only the Python standard library. Run the tests from the project folder:

```bash
python3 -m unittest discover tools/adsb
```

## Trying it without the Pi

Make a simulated day, analyse it and open the viewer:

```bash
python3 tools/adsb/adsb_simulate.py demo
open tools/adsb/data/demo/results/viewer.html
```

The simulated day isn't real data, though it includes the main kinds of error real data has. Its fleet of E190s, E190-E2s, E195-E2s, A220-100s and A320neos flies straight paths with no wind, turbulence or speed changes. Arrivals use 5.5°, or 4.49° for the A320neo, and the garden is 500 m north of the RWY 27 centreline, 4 km from the threshold. RWY 27 is in use until 13:15, then RWY 09. It includes overflights, two helicopter passes and some deliberate problems:

- about 8 m of noise on every position, as in good real ADS-B
- a cold day, with altimeter readings worked out from the actual pressure, so the temperature correction is tested
- METAR QNH rounded down, as real METARs do
- some positions too poor to use, and some aircraft with non-ICAO addresses
- an aircraft with no geometric altitude
- one sending sea-level height as geometric
- a reception gap near the garden
- QNH changing through the day
- an unreadable line
- a power cut at 12:10 that damages a log file and leaves the clock briefly unsynchronised

`truth.csv` gives the true values for every flight. The tests in `test_adsb_simulate.py` check that the analysis recovers them. On the simulated day, 95% of arrivals come back within about 1.5 m of their true offset, 0.6 m of height and 0.01° of path angle. Real data will be worse, so these figures show the method works, not how accurate it will be in the garden.

The simulator only replaces its own earlier output. It won't write into a folder it didn't make.

To test the logger itself, run a fake readsb that replays the simulated day at 10 times real speed, then point the logger at port 30154:

```bash
python3 tools/adsb/adsb_simulate.py serve --speed 10
```

## The viewer

`viewer.html` opens in any browser, works offline and loads nothing from the internet. Hover over anything for details, and click to select a flight.

- **Tracks around the garden:** a plan view in kilometres from the garden, with rings at 1, 2 and 5 km.
- **Height profile:** height above the microphone against distance east of the garden.
- **By aircraft type:** one dot per flight for a chosen measure, such as path angle (with 4.49° and 5.5° marked), offset, height, distance or sound delay.
- **Flights table:** sortable, with a panel showing every value for the selected flight.
- **Warnings and summary:** from `summary.txt`.

The viewer has no latitudes or longitudes, only distances from the garden. It still shows exact offsets from the arrival path, though, so treat a viewer made from real data as private.

## Setting up the Pi

These steps come from the project documentation and haven't yet been run on our Pi. Steps 1–3 come from the readsb project. Read the install script before running it, because it runs as root and removes any other ADS-B decoder.

1. Install 64-bit Raspberry Pi OS Lite, then connect the stick, antenna, GPS receiver and SSD.
2. Install readsb and tar1090:

   ```bash
   sudo bash -c "$(wget -O - https://github.com/wiedehopf/adsb-scripts/raw/master/readsb-install.sh)"
   sudo reboot
   ```

3. Set the receiver location and automatic gain:

   ```bash
   sudo readsb-set-location <latitude> <longitude>
   sudo readsb-gain auto
   ```

4. Download a dated aircraft database from the [`csv` branch of tar1090-db](https://github.com/wiedehopf/tar1090-db/tree/csv). Keep that copy for the whole stage.
5. Edit `/etc/default/readsb`. Add the first option to `NET_OPTIONS` and the second to `DECODER_OPTIONS`. Keep what's already there:

   ```text
   --net-json-port 30154
   --db-file /path/to/aircraft-YYYY-MM-DD.csv.gz
   ```

   readsb only adds the type (`t`) and registration (`r`) when `--db-file` is set. We chose port 30154; any free port will do.

6. Restart readsb and check the stream:

   ```bash
   sudo systemctl restart readsb
   nc localhost 30154 | head
   ```

7. Open `http://<pi-address>/tar1090` to see the live map.

### GPS clock

A Pi 4 has no battery-backed clock, so after a power cut it can't know the time until the GPS has a fix. This setup is a starting point that we still need to test.

```bash
sudo apt install gpsd chrony
```

In `/etc/default/gpsd`, check the device name with `ls /dev/ttyACM* /dev/ttyUSB*`:

```text
DEVICES="/dev/ttyACM0"
GPSD_OPTIONS="-n"
```

Create `/etc/chrony/conf.d/gps.conf`:

```text
refclock SHM 0 refid GPS precision 1e-1 offset 0.0 delay 0.2
makestep 1 -1
```

`makestep 1 -1` lets chrony jump the clock at any time, so it corrects a wrong boot time straight away.

USB GPS receivers commonly lag by a few hundred milliseconds. That's within our 1 s target, so `offset 0.0` will do. For directivity or Doppler work, which needs 0.25 s, measure the lag: run the Pi with internet access for a few hours, compare the GPS source with internet time using `chronyc sourcestats`, and set `offset` to the difference. The GPS antenna needs a view of the sky.

Check the clock with `chronyc tracking`. The logger records this in its health log every 5 minutes.

### Logger

The SSD should be mounted at `/var/lib/adsb-logger`. The service won't start without it, rather than filling the SD card.

```bash
sudo useradd --system --no-create-home adsb-logger
sudo usermod -aG video adsb-logger              # so it can read throttling flags
sudo mkdir -p /opt/adsb-logger /etc/adsb-logger
sudo chown adsb-logger /var/lib/adsb-logger
sudo cp adsb_logger.py adsb_status.py /opt/adsb-logger/
sudo cp site.example.json /etc/adsb-logger/site.json
sudo nano /etc/adsb-logger/site.json            # the garden's real location and ground height
sudo cp adsb-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adsb-logger
journalctl -u adsb-logger -f
```

### On each site visit

```bash
python3 /opt/adsb-logger/adsb_status.py
```

This shows when the logger last wrote, the clock's state, free disk space, temperature, power problems and how much data was kept in the last 24 hours. It warns if:

- the logger has stopped
- the clock isn't synchronised
- the disk is filling
- the Pi is overheating or short of power
- readsb keeps disconnecting
- nothing is being kept, which usually means the site location in the config is wrong

It exits with code 1 when there are warnings.

## What gets logged

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

## Analysing the logs

Copy the logs to a laptop, recording checksums, and run the analysis on the copy.

1. Download EGLC METARs for the logged period from the [Iowa Environmental Mesonet archive](https://mesonet.agron.iastate.edu/request/download.phtml). This is the request we tested:

   ```bash
   curl -o eglc.csv 'https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=EGLC&data=metar&year1=2026&month1=11&day1=4&year2=2026&month2=11&day2=5&tz=Etc/UTC&format=onlycomma&latlon=no&missing=empty&trace=empty&direct=no&report_type=3&report_type=4'
   ```

   A CSV with `time,qnh_hpa,temp_c` columns also works, for example from the Fusion's weather station.

2. Run the analysis:

   ```bash
   python3 tools/adsb/adsb_analyse.py --config site.json --logs LOG_COPY --out results --weather eglc.csv
   ```

   Add `--from 2026-11-05 --to 2026-11-06` to analyse one period, for example to make a smaller viewer for one day. The logs are read in time order and each flight is finished once its aircraft goes quiet. So memory use depends on how many aircraft are in the air at once, not on the length of the survey: about 40 MB for a simulated day.

### Outputs

- `flights.csv`: one row per flight.
- `positions.csv`: every position of flights labelled as arrivals or departures. Use `--all-positions` to include all flights.
- `summary.txt`: data gaps, damaged files, warnings and medians by label and aircraft type. A gap of over 30 minutes in the kept data is reported as `GAP` when data may have been lost, and as `QUIET` when the health log shows the logger connected and receiving throughout, so there were just no aircraft nearby. It also counts the lines stamped while the clock wasn't synchronised.
- `viewer.html`: everything above, to explore in a browser. See [The viewer](#the-viewer).

### How each value is worked out

- **Position:** positions are converted to metres east and north of the garden. Each position's time is when it was received, less its age.
- **Height:** two heights are worked out for every position:
  - **QNH height:** `alt_baro` corrected with the latest METAR QNH and temperature. METAR QNH is rounded down to the whole hPa, so 0.5 hPa is added back. The temperature correction scales the height by the ratio of actual to standard mean air temperature below the aircraft, which matters on cold days: about 4% at 15 °C below standard. Both can be turned off in the config's `analysis` section.
  - **Geometric height:** `alt_geom` minus `geoid_height_m` from the config. This is roughly 45 m in London, from memory, and needs confirming from a geoid model. Until it's set, only QNH heights are worked out.

  Each flight uses one source throughout, geometric where available. `median_qnh_minus_geometric_m` compares the two, and a flight is flagged `heights_disagree` when they differ by more than 30 m. Geometric is rejected in favour of QNH (`geometric_rejected`) only when the difference matches a known aircraft fault: sending height above sea level as geometric, which shows as a difference close to the geoid height. Other differences could be the weather's fault, so geometric is kept.
- **Offset from the garden:** `lateral_offset_m` is the closest distance between the garden and the track, measured along the ground. Straight lines are fitted to the positions and heights over 20 seconds either side of the closest point. This averages out position noise and the 25 ft altitude steps; the nearest single position would read short. `garden_side` says which side of the track the garden is on: north or south for east–west tracks, east or west for north–south ones.
- **Sound delay:** `closest_slant_m` is the closest straight-line distance between the aircraft and the microphone. `sound_delay_s` is that distance divided by the speed of sound, which is worked out from the METAR temperature. Each row of `positions.csv` has the time the sound left the aircraft and the time it reached the microphone. Use the arrival time to find where the aircraft was when the sound at LAmax left it.
- **Path:** `path_angle_deg` is fitted from height against distance along the track, within 3 km of the garden. Distance is measured along a straight line, so position noise doesn't lengthen it. This should tell 5.5° from 4.49°. `label` gives `rwy27_arrival`, `rwy09_departure` or `other`, from heading, climb or descent, height and offset. This is a first rule of thumb, so check it against real flights.
- **Quality flags:**
  - `no_qnh`, `no_height`: QNH or height missing
  - `assumed_sound_speed`: no temperature, so 340.3 m/s was used
  - `gap_at_closest_point`: a gap in the track near the garden
  - `closest_point_at_track_end`: the track ends before passing the garden
  - `heights_disagree`: QNH and geometric heights differ by more than 30 m
  - `geometric_rejected`: QNH height used because geometric looked like the sea-level fault
  - `clock_not_synchronised`: the flight overlaps a period when the health log showed the clock unsynchronised

Go-arounds and missed approaches are labelled `other` without a specific flag. Look for them among `other` flights with a low closest point.

## Keep out of this repository

This repository is public. Never commit:

- the garden's coordinates, including in config files, sample logs or screenshots
- flight logs or analysis results

`.gitignore` excludes `site.json` and `logs/`, `results/` and `data/` folders in `tools/adsb`. Anything published should be summarised, and shouldn't identify individual private aircraft.

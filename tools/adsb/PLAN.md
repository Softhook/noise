# ADS-B flight logger plan

5 November 2026

## Purpose

Record the aircraft type, time, track and height of each flight near the Thamesmead garden, so that each noise event can be matched to an aircraft. This could fill these rows of the [measurement plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md):

| Measurement plan needs | From ADS-B? |
|---|---|
| Aircraft type, runway and time | Yes. Type comes from a database and runway is inferred from the track |
| Track and height | Yes, after correcting height |
| Other noise during events | Partly. Shows other aircraft transmitting nearby, but not those without ADS-B, or road noise |
| Aircraft weight | No |
| NMT6 levels | No |
| Wind, temperature and rain | No |

The Pi logs locally, and we collect the data by hand. So we won't know about a fault until someone checks the Pi, and the design needs to allow for that.

## Requirements

These targets are our proposals, to be tested in the trial.

| Requirement | Target | Why |
|---|---|---|
| Flights captured | At least 99% of RWY 27 arrivals have a position within 2 km of their closest point to the garden | Each lost flight is a noise event without an aircraft |
| Timing | Pi clock within about 1 s of UTC, and any larger error detected | Enough to match events to flights; height, distance and levels don't depend on the clock. A 0.25 s target is only needed for directivity or Doppler work, which isn't planned. See the measurement plan's [Timing](../../Documents/Thamesmead_Garden_Measurement_Plan.md#timing) |
| Height | QNH-corrected and geometric heights agree within about 30 m | Against an expected height of about 385 m |
| Data loss from a power cut | No more than 60 s | Keeps gaps small and easy to identify |
| Unattended running | 37 days, restarting by itself after a fault or power cut | Matches the survey length |
| Noise from the Pi | None measurable at the microphone | Must not affect the survey |

## Elements

### 1. Hardware

| Item | Status | Notes |
|---|---|---|
| Raspberry Pi 4 | Have | Fanless case |
| FlightAware Pro Stick Plus | Have | Draws 300 mA from USB |
| 1090 MHz antenna with SMA connector | To buy | FlightAware's page doesn't mention one being included, so check the box |
| Short, low-loss coax | To buy | [Long coax loses a lot of signal](https://www.rtl-sdr.com/flightaware-prostick-vs-flightaware-prostick-plus-review/) |
| Official 5 V 3 A power supply | To check | Weak supplies are a common cause of unreliable Pis |
| SD card for the operating system | To check | A good-quality card |
| USB SSD for logs, 256 GB | To buy | Takes the constant writes off the SD card |
| Weatherproof enclosure | Depends on site | Only if the Pi can't go indoors |
| USB GPS receiver | Chosen | Sets the clock. See [Clock](#3-clock) |
| USB Ethernet or spare cable | To check | For a laptop to collect data on site |

### 2. Receiver

- Use readsb and tar1090, set up as in the [README](README.md).
- Start with automatic gain. Aircraft pass close to the garden, so check signal strength and [aim for a low share of strong signals](https://github.com/wiedehopf/adsb-wiki/wiki/Optimizing-gain).
- Use a tuned 1090 MHz antenna. The stick's amplifier comes before its filter, and [strong FM and TV signals can overload it](https://www.rtl-sdr.com/flightaware-prostick-vs-flightaware-prostick-plus-review/). If that happens, try an external filter before the stick.
- Save a dated copy of the aircraft database and keep it for the whole stage, so results can be reproduced.

### 3. Clock

A Pi 4 has no battery-backed clock, so after a power cut it starts with the wrong time until it finds a time source. readsb timestamps use the Pi's clock, so this directly affects matching.

**Decision:** a USB GPS receiver, read by `gpsd` and `chrony`. The setup is in the [README](README.md#gps-clock).

- The GPS's main job is to set the right time after a power cut. The Pi has no battery-backed clock, so without it the clock could be minutes or days wrong.
- USB GPS receivers send no pulse-per-second signal, and they commonly lag by a few hundred milliseconds. That's within our 1 s target, so measuring the lag is optional. Measure it and set chrony's offset only if we take on directivity or Doppler work, which needs 0.25 s; if it then varies too much, switch to a GPS module with pulse-per-second.
- The GPS antenna needs a view of the sky, which affects where the Pi goes.
- Don't rely on a battery-backed clock add-on alone, as it would drift without correction.

The logger will record clock status regularly and keep logging when the clock isn't synchronised, so that the data can be flagged and possibly corrected later.

The Fusion is set to UTC with GPS synchronisation, and drifts by at most 0.5 s a day between its midnight corrections, which is within our target. The measurement plan's [Timing](../../Documents/Thamesmead_Garden_Measurement_Plan.md#timing) section covers both clocks. The real risk is a large error, such as a clock wrong after a power cut or an hour out from a time zone. The results give an independent check: LASmax should come at a steady delay after each arrival's closest approach, so a jump would show a clock problem.

### 4. Logger (`adsb_logger.py`)

Connects to readsb's JSON stream and writes it to disk.

- **Python standard library only**, like `tools/fusion`, so it needs no packages installed.
- **Keep lines as received.** Interpretation happens later, so a mistake in analysis never damages the original data.
- **Hourly files**, such as `2026-11-05T14.jsonl.gz`, named in UTC.
- **Flush every 60 s or less**, so that a damaged file can still be read up to the last flush.
- **Limit by distance.** Keep positions within 30 km of the garden, plus aircraft that have no position yet. The distance should be configurable.
- **Reconnect automatically** if readsb restarts, and record the gap.
- **Stop safely** if the disk is nearly full, and record why.
- **Config outside the repository**, in `/etc/adsb-logger/site.json`, because it holds the garden's coordinates. It's JSON rather than TOML so it can be read on the laptop's Python 3.9.
- Runs as a `systemd` service that restarts automatically and starts on boot.

We'll decide in the trial whether to also keep readsb's own daily track files (`--write-globe-history`) as a backup. readsb warns they can [create thousands of files a day](https://github.com/wiedehopf/readsb#saving-traces), though it may be far fewer with one receiver.

### 5. Health log

Every 5 minutes, write a line to a separate file with:

- messages and positions received, and aircraft seen
- age of the newest message
- clock status and offset from `chronyc tracking`
- free disk space
- CPU temperature and any low-power or overheating flags from `vcgencmd get_throttled`
- time since boot

`adsb_status.py` summarises this log for site visits, and warns about the problems most likely to lose data unnoticed. The clock is checked every 10 seconds until it's synchronised, so short unsynchronised periods after a power cut are caught. We'll decide whether a simple status light is also worth adding.

### 6. Storage

The estimate below is rough and assumes 50 aircraft in range at most, 2 positions a second, about 800 bytes a line and 8:1 compression. The trial will give real figures.

| | Per day | 37 days |
|---|---:|---:|
| Uncompressed | 7 GB | 256 GB |
| Compressed | 0.9 GB | 32 GB |

A 256 GB SSD leaves plenty of margin, and could hold both stages if needed.

### 7. Power, housing and placement

- Mains power, with outdoor connections protected by an RCD and weatherproofed. The Fusion needs mains too, so plan them together.
- If possible, keep the Pi indoors with the antenna at a window or just outside. We only need flights within about 20–30 km, so a roof antenna is probably unnecessary.
- If it has to go outdoors, use a weatherproof enclosure shaded from the sun, and check for condensation and overheating.
- Don't mount anything on the Fusion's tripod, and keep equipment clear of the microphone. It could add vibration or reflect sound.
- Keep the antenna a few metres from the Fusion's 4G modem, then compare reception with the modem on and off.

### 8. Collecting data

- Visit about once a week during the trial and early in the survey, as there are no remote alerts. Check `adsb_status.py` on each visit.
- Connect a laptop by cable, copy the files with `rsync`, and record SHA-256 checksums, as the measurement plan asks for the Fusion data.
- Keep the data on the Pi until a copy has been checked, then keep a second copy off site.

### 9. Analysis

Scripts run on a laptop, and they never change the original logs.

1. **Check the logs.** Read all files, then list gaps, damaged files and periods when the clock wasn't synchronised.
2. **Group positions into flights.** Group by `hex`, starting a new flight after a gap of about 10 minutes. Trim spaces from callsigns.
3. **Confirm the aircraft type.** Use `t` from the log, then compare with the airport's records if we can get them. This matters most for telling an `A20N` from an `A320` in Stage 2. Check all type codes against the first data: we expect `E190`, `E290` (E190-E2), `BCS1` (A220-100) and `A20N` (A320neo), from memory.
4. **Correct height.**
   - **QNH:** `alt_baro` is normally referenced to 1013.25 hPa, so correct it with EGLC's QNH, at about 27 ft (8 m) per hPa. METARs can be downloaded afterwards, and the Fusion's WXT536, if we have one, gives a local pressure check. Find a reliable METAR archive.
   - **Geometric:** subtract the geoid height from `alt_geom`, using a published geoid model. It's roughly 45 m in London, from memory.
   - **Compare:** check both results against each other and against `nav_qnh`, then decide which to use as the main height.
5. **Calculate geometry.** For each position, calculate distance, angle and height relative to the microphone, then each flight's closest approach. Filter out poor positions using `nic`, `rc` and `seen_pos`.
6. **Classify flights.** Identify RWY 27 arrivals, RWY 09 departures and other traffic from track, height and vertical rate. Estimate the approach angle, to confirm 5.5° or 4.49° for each flight.
7. **Allow for sound delay.** Sound reaching the garden left the aircraft earlier, by about 1.9 s at 5.5° (631 m) and 1.7 s at 4.49° (590 m). These are nominal values at 4 km from the threshold; use each flight's real distance. Work out where the aircraft was when the sound left it.
8. **Match noise events.** Match each Fusion event to the flight that fits its time and position. Fusion times must be in UTC; stop if a file's time zone is unknown. Report the median of LASmax time minus `sound_arrival_time_utc` for each day's RWY 27 arrivals, and flag a day where it jumps by more than about 0.5 s, as the clock check. Flag events with no flight, or with more than one aircraft close enough to affect the level. Fusion CSV exports should be enough at 1 s, and the [data format plan](../../Documents/Fusion_Data_Format_Reverse_Engineering.md) covers the 100 ms data.
9. **Export one table.** One row per event, with the fields in the measurement plan's [What to record](../../Documents/Thamesmead_Garden_Measurement_Plan.md#what-to-record) section, plus quality flags.

### 10. Testing

- **Automated tests** in `tools/adsb`, in the style of `tools/fusion`. These should cover missing fields, `"ground"` altitudes, invalid lines, reconnecting, file changeover, reading damaged files, height correction, flight grouping and sound delay.
- **Test data**, made up at first, then real lines from the Pi. Any committed sample must have its location data replaced with coordinates that don't reveal the garden.
- **Hardware tests**: pull the power, restart readsb, unplug the stick, fill a small test disk and start without a time source. Confirm the recovery and the record each one leaves.

## Build order

| Step | Work | Done when | Status |
|---:|---|---|---|
| 1 | Install the receiver on a desk or at a window | Aircraft appear on tar1090 and in the JSON stream | To do |
| 2 | Save 24 hours of real stream data | We have real fields, line sizes and aircraft counts | To do |
| 3 | Write the logger and tests | The logger survives the hardware tests | Written, with tests passing on made-up data. Hardware tests to do |
| 4 | Set up the GPS clock and health log | Clock status is logged and recovers after a power cut | Health log and `adsb_status.py` written. GPS to do |
| 5 | Write analysis steps 1–7 | Flights, heights and classifications look right against tar1090 | Written, with tests passing on made-up data. Real data to do |
| 5a | Simulator and viewer | The analysis recovers a simulated day's known values, and results can be explored in a browser | Done. On simulated data only, with about 8 m of position noise, 95% of arrivals come back within about 1.5 m of offset, 0.6 m of height and 0.01° of path angle. This shows the method works, not the accuracy we'll get from real data |
| 6 | Install on site | The Pi meets the capture and noise targets alongside the Fusion | To do |
| 7 | Run the 2–3 day trial with the Fusion | Data goes through export, SEL, spectra and flight matching, and the Fusion's clock corrections look right in its event log | To do |
| 8 | Write analysis steps 8–9 and review the targets | Each aircraft type's events match, and the clock check holds | To do; needs the Fusion export format |
| 9 | Run Stage 1 | Regular visits, with data copied and checked | To do |

Steps 1–4 don't need the Fusion. Step 7 is the [trial already in the measurement plan](../../Documents/Thamesmead_Garden_Measurement_Plan.md#running-the-campaign).

## NMT6 data from the airport

The measurement plan asks for NMT6 levels for the same flights, to compare the two sites. London City's public flight and noise tracker is WebTrak, at [eu.webtrak.aero/lcy](https://eu.webtrak.aero/lcy). It's a JavaScript app, and the page we downloaded showed no terms of use. We haven't checked whether it shows NMT6, how long its delay is, or whether its terms allow automated collection.

The analysis is done afterwards, so we don't need the data in real time. The options, in order of preference:

1. **Ask the airport for NMT6 event data** for the survey periods: LAmax, SEL, event times and the matched flight, ideally with the 1 s levels. The Bickerdike Allen report used the airport's own system data, so the data exists. Ask through the airport's noise team or the consultative committee.
2. **Record what WebTrak shows**, but only if its terms allow it and the airport agrees. First check whether it shows NMT6 and what the levels are, such as a 1 s Leq. WebTrak levels elsewhere include non-aircraft noise. This would be a separate script and wouldn't run on the Pi, which has no internet.
3. **Read WebTrak by hand** for a sample of flights, as a check on option 1.

Our own ADS-B log would make matching their events to flights straightforward.

## Risks

| Risk | Effect | How we reduce it |
|---|---|---|
| A fault goes unnoticed | Weeks of lost data | Automatic restarts, health log and regular visits |
| Clock wrong after a power cut | Events matched to the wrong flight | Clock checked every 10 s until synchronised, and flights in unsynchronised periods flagged. The check against closest approach is still to build |
| Fusion and Pi in different time zones, or a time zone lost in export | Every event an hour out | Fusion set to UTC with summer time off, times kept as UTC in ISO format, and the matcher refuses an unknown time zone |
| Height left uncorrected | Errors of up to about 250 m on a 30 hPa day | QNH correction with temperature and METAR rounding allowed for, compared with geometric height. Geometric height rejected when it shows the sea-level fault |
| Tests pass but real data differs | False confidence in accuracy | The simulator adds noise, cold weather and known faults, but it can't reproduce everything. Check against tar1090 and airport records once real data exists |
| Aircraft type wrong in the database | The wrong aircraft in a comparison | Dated database, and checks against airport records |
| Overload from nearby signals | Fewer flights captured | Tuned antenna and low gain, then an external filter if needed |
| Interference from the Fusion's 4G modem | Fewer flights captured | Separate the two, and test with the modem on and off |
| An aircraft doesn't send ADS-B | An unmatched event | Flag it, and compare with airport records |
| Disk or SD card failure | Lost data | SSD for logs, and regular checked copies |
| Garden location is published | Privacy | Config outside the repository, with no logs or real positions committed |

## Open questions

- [x] Clock source: USB GPS.
- [ ] How large and how steady is our USB GPS receiver's lag? Only needed if we take on directivity or Doppler work.
- [ ] Can the Pi go indoors with a view of the sky for the GPS, and is there mains power near it and near the Fusion?
- [ ] Will the airport supply NMT6 event data for the survey periods? What do WebTrak's terms allow?
- [ ] Who will visit the site, and how often?
- [ ] Is an antenna included with our Pro Stick Plus?
- [ ] Do we have the Fusion's WXT536 weather station for a local pressure reading?
- [ ] Can the airport supply flight records for checking types and capture?
- [ ] Which geoid model should we use, and what is the geoid height at the garden? The [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml) archive works for EGLC METARs, with QNH and temperature.
- [ ] Do these targets suit the analysis? Review them after the trial.

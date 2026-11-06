"""Turn ADS-B logs into flights, with corrected heights, offsets from the site and sound delay.

  python3 -m adsb analyse --config site.json --logs LOG_DIR --out OUT_DIR [--weather eglc_metars.csv]
                          [--from 2026-11-05] [--to 2026-11-06] [--all-positions]

Writes flights.csv (one row per flight), positions.csv (each position of the labelled flights),
summary.txt and viewer.html, which opens in a browser without a network connection. The logs are
only ever read. Times are UTC.

The logs are read in time order and each flight is finished as soon as its aircraft has been
silent for new_flight_gap_s, so memory use depends on how many aircraft are in the air at once,
not on how long the survey is. Use --from and --to to make a viewer for a shorter period.

The runway labels are a first rule of thumb. Check them against real flights before relying on them.

This module runs the pipeline and writes the outputs. The work is done in:
  logs.py      reading the hourly files          tracks.py   records to positions to flights
  weather.py   QNH and temperature by time       flight.py   one flight's heights, geometry, label
  health.py    the logger's health log           viewer.py   viewer.html
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import statistics
import sys

from .common import format_utc, number, overlaps, parse_utc, rounded
from .flight import analyse_flight
from .geometry import Site
from .health import health_summary, logger_was_listening
from .logs import log_paths, read_log_records
from .tracks import FlightBuilder, parse_point
from .viewer import viewer_data, viewer_track, write_viewer
from .weather import WEATHER_MAX_AGE_S, Weather

DEFAULTS = {
    "max_km": 15.0,  # Analysis radius, tighter than the logger's
    "ceiling_ft": 10000,
    "max_seen_pos_s": 2.0,
    "min_nic": 6,
    "new_flight_gap_s": 600.0,
    "weather_max_age_s": WEATHER_MAX_AGE_S,
    # METAR QNH is rounded down to the whole hPa, so the true value is on average 0.5 hPa higher.
    "metar_qnh_rounded_down": True,
    # Correct QNH heights for the difference between the METAR temperature and the standard atmosphere.
    "temperature_correction": True,
    "slope_window_m": 3000.0,
    "min_slope_span_m": 1000.0,
    "level_angle_deg": 0.5,
    "runway_27_heading_deg": 272.9,  # True bearing, from a flight-planning database; check against the AIP
    "heading_tolerance_deg": 30.0,
    "max_label_height_m": 1500.0,
    "max_label_offset_m": 3000.0,
    "max_gap_near_site_s": 10.0,
    "smoothing_window_s": 20.0,  # Fit straight lines this far either side of the closest point
    "height_disagreement_m": 30.0,
    "sea_level_fault_tolerance_m": 15.0,
    "viewer_spacing_s": 1.0,
    "viewer_other_spacing_s": 10.0,
}
FLIGHT_COLUMNS = [
    "flight_id", "hex", "callsign", "type", "registration", "db_flags", "label", "first_seen_utc",
    "last_seen_utc", "positions", "height_source", "site_side", "lateral_offset_m",
    "closest_ground_time_utc", "height_at_closest_ground_amsl_m", "closest_slant_time_utc",
    "closest_slant_m", "angle_from_vertical_deg", "sound_delay_s", "sound_arrival_time_utc",
    "heading_deg", "path_angle_deg", "path_trend", "ground_speed_kt", "qnh_hpa", "temp_c",
    "sound_speed_m_s", "median_qnh_minus_geometric_m", "aircraft_qnh_hpa", "flags",
]
POSITION_COLUMNS = [
    "flight_id", "hex", "callsign", "type", "emission_time_utc", "arrival_time_utc", "lat", "lon",
    "east_m", "north_m", "ground_distance_m", "height_qnh_amsl_m", "height_geometric_amsl_m",
    "height_used_amsl_m", "height_above_mic_m", "slant_m", "angle_from_vertical_deg",
    "sound_delay_s", "ground_speed_kt", "track_deg", "nic", "rc", "rssi",
]


# Latitude and longitude keep 6 decimal places (about 0.1 m); 3 would snap tracks to a ~70 x 110 m grid
COORDINATE_COLUMNS = {"lat", "lon"}


class CsvOut:
    def __init__(self, path, columns):
        self.file = open(path, "w", newline="")
        self.columns = columns
        self.writer = csv.DictWriter(self.file, columns, extrasaction="ignore")
        self.writer.writeheader()
        self.rows = 0

    def write(self, row):
        self.writer.writerow({key: "" if row.get(key) is None else rounded(row[key], 6 if key in COORDINATE_COLUMNS else 3)
                              for key in self.columns})
        self.rows += 1

    def close(self):
        self.file.close()


def median_text(values, places=1):
    values = [v for v in values if v is not None]
    return f"{statistics.median(values):.{places}f}" if values else "-"


def read_source(log_dir):
    """The first line of SOURCE.txt, which converted logs (adsb traces, opensky logs) have, or None."""
    try:
        with open(os.path.join(log_dir, "SOURCE.txt")) as f:
            first = f.readline().strip()
    except OSError:
        return None
    return first[len("Source:"):].strip() if first.startswith("Source:") else first or "unnamed"


def build_summary(flights, report, weather_loaded, geoid_known, health, site=None, source=None):
    lines = []
    if site is not None:
        where = f" ({site.lat:.5f}, {site.lon:.5f})" if site.public else ""
        lines.append(f"Site: {site.name}{where}")
    if source:
        lines.append(f"Source: {source}. Converted, not the logger's own record")
    lines += [
        f"Files read: {report['files']}",
        f"Lines read: {report['lines']}, unreadable: {report['invalid_lines']}",
        f"Flights: {len(flights)}",
        f"Time covered: {report['first']} to {report['last']}",
        f"Health records: {health['records']}",
    ]
    if not weather_loaded:
        lines.append("WARNING: no weather file, so there are no QNH heights")
    if not geoid_known:
        lines.append("WARNING: geoid_height_m not set, so there are no geometric heights")
    if not health["records"] and source:
        lines.append("NOTE: no health log, as expected for converted logs, so there's no clock check, "
                     "and a gap can't be told from a quiet sky")
    elif not health["records"]:
        lines.append("WARNING: no health log, so clock problems can't be detected")
    for start, end in health["unsynced"]:
        lines.append(f"WARNING: clock not synchronised from {format_utc(start)} to {format_utc(end)}")
    for event in ("disconnected", "disk_low_paused", "write_error", "start"):
        if health["events"].get(event):
            lines.append(f"LOGGER: {health['events'][event]} '{event}' events")
    for item in report["damaged_files"]:
        lines.append(f"DAMAGED: {item}")
    if report["misdated_lines"]:
        lines.append(f"WARNING: {report['misdated_lines']} lines skipped because their time was far "
                     "outside their file's hour")
    if report["unsynced_lines"]:
        lines.append(f"WARNING: {report['unsynced_lines']} lines were stamped while the clock wasn't "
                     "synchronised, so their times may be wrong")
    for start, end, listening in report["gaps"]:
        if listening:
            lines.append(f"QUIET over 30 minutes, logger running: {format_utc(start)} to {format_utc(end)}")
        elif not health["records"]:
            lines.append(f"GAP over 30 minutes, unchecked (no health log, so it may be a quiet sky): "
                         f"{format_utc(start)} to {format_utc(end)}")
        else:
            lines.append(f"GAP over 30 minutes: {format_utc(start)} to {format_utc(end)}")
    lines.append("")
    lines.append("label, type, flights, median offset m, height AMSL m, slant m, path angle, QNH minus geometric m")
    groups = collections.defaultdict(list)
    for flight in flights:
        groups[(flight["label"], flight["type"] or "unknown")].append(flight)
    for (label, kind), group in sorted(groups.items()):
        lines.append(", ".join([
            label, kind, str(len(group)),
            median_text([f["lateral_offset_m"] for f in group]),
            median_text([f["height_at_closest_ground_amsl_m"] for f in group]),
            median_text([f["closest_slant_m"] for f in group]),
            median_text([f["path_angle_deg"] for f in group], 2),
            median_text([f["median_qnh_minus_geometric_m"] for f in group]),
        ]))
    return "\n".join(lines) + "\n"


def run(config, log_dir, out_dir, weather_path=None, all_positions=False, start=None, end=None):
    """Analyse the logs between start and end (Unix times, either may be None). Returns (flights, summary)."""
    settings = {**DEFAULTS, **config.get("analysis", {})}
    site = Site(config)
    weather = (
        Weather.load(weather_path, settings["weather_max_age_s"], settings["metar_qnh_rounded_down"])
        if weather_path
        else Weather(max_age=settings["weather_max_age_s"])
    )
    health = health_summary(log_dir)
    report = {
        "files": 0, "lines": 0, "invalid_lines": 0, "misdated_lines": 0, "damaged_files": [], "gaps": [],
        "unsynced_lines": 0,
    }
    builder = FlightBuilder(settings["new_flight_gap_s"])
    flights, tracks = [], {}
    minutes = set()
    os.makedirs(out_dir, exist_ok=True)
    positions = CsvOut(os.path.join(out_dir, "positions.csv"), POSITION_COLUMNS)

    def finish(finished):
        flight_id, code, points = finished
        flight, rows = analyse_flight(flight_id, code, points, site, weather, settings, health["unsynced"])
        flights.append(flight)
        labelled = flight["label"] != "other"
        spacing = settings["viewer_spacing_s"] if labelled else settings["viewer_other_spacing_s"]
        tracks[flight_id] = viewer_track(rows, spacing)
        if all_positions or labelled:
            for row in rows:
                positions.write(row)

    count = 0
    for record in read_log_records(log_paths(log_dir, start, end), report):
        now = number(record.get("now"))
        if now is None or (start is not None and now < start) or (end is not None and now >= end):
            continue
        minutes.add(int(now // 60))
        if health["unsynced"] and overlaps(health["unsynced"], now, now):
            report["unsynced_lines"] += 1
        parsed = parse_point(record, site, settings)
        if parsed:
            finished = builder.add(*parsed)
            if finished:
                finish(finished)
        count += 1
        # Use this record's time, not the latest seen, so one bad time can't finish every open flight
        # for the rest of the run.
        if count % 20000 == 0:
            for finished in builder.finish_quiet(now):
                finish(finished)
    for finished in builder.finish_all():
        finish(finished)
    positions.close()
    flights.sort(key=lambda f: f["flight_id"])

    ordered = sorted(minutes)
    report["first"] = format_utc(ordered[0] * 60) if ordered else "-"
    report["last"] = format_utc(ordered[-1] * 60) if ordered else "-"
    report["gaps"] = [
        (a * 60, b * 60, logger_was_listening(health["entries"], a * 60, b * 60))
        for a, b in zip(ordered, ordered[1:]) if b - a > 30
    ]

    flights_out = CsvOut(os.path.join(out_dir, "flights.csv"), FLIGHT_COLUMNS)
    for flight in flights:
        flights_out.write(flight)
    flights_out.close()
    summary = build_summary(flights, report, bool(weather.entries), site.geoid is not None, health, site,
                            read_source(log_dir))
    with open(os.path.join(out_dir, "summary.txt"), "w") as f:
        f.write(summary)
    write_viewer(os.path.join(out_dir, "viewer.html"), viewer_data(flights, tracks, summary, site, config))
    return flights, summary


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, help="JSON file; see site.example.json")
    parser.add_argument("--logs", required=True, help="the logger's log_dir, or a copy of it")
    parser.add_argument("--out", required=True, help="folder for the results")
    parser.add_argument("--weather", help="CSV of METARs, or of time, qnh_hpa and temp_c")
    parser.add_argument("--from", dest="start", help="first UTC date or time to include, such as 2026-11-05")
    parser.add_argument("--to", dest="end", help="UTC date or time to stop before, such as 2026-11-06")
    parser.add_argument("--all-positions", action="store_true", help="include unlabelled flights in positions.csv")
    args = parser.parse_args(argv)
    with open(args.config) as f:
        config = json.load(f)
    start = parse_utc(args.start) if args.start else None
    end = parse_utc(args.end) if args.end else None
    _, summary = run(config, args.logs, args.out, args.weather, args.all_positions, start, end)
    print(summary, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

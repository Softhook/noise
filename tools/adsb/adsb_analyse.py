#!/usr/bin/env python3
"""Turn ADS-B logs into flights, with corrected heights, offsets from the garden and sound delay.

  adsb_analyse.py --config site.json --logs LOG_DIR --out OUT_DIR [--weather eglc_metars.csv]
                  [--from 2026-11-05] [--to 2026-11-06] [--all-positions]

Writes flights.csv (one row per flight), positions.csv (each position of the labelled flights),
summary.txt and viewer.html, which opens in a browser without a network connection. The logs are
only ever read. Times are UTC. Uses only the standard library.

The logs are read in time order and each flight is finished as soon as its aircraft has been
silent for new_flight_gap_s, so memory use depends on how many aircraft are in the air at once,
not on how long the survey is. Use --from and --to to make a viewer for a shorter period.

The runway labels are a first rule of thumb. Check them against real flights before relying on them.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import glob
import gzip
import json
import math
import os
import re
import statistics
import sys
import zlib
from typing import NamedTuple, Optional

from adsb_logger import read_health_log

FEET = 0.3048
WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014
DEFAULT_SOUND_SPEED = 340.3  # At 15 °C
ISA_SEA_LEVEL_K = 288.15
LAPSE_RATE = 0.0065  # K per metre

DEFAULTS = {
    "max_km": 15.0,  # Analysis radius, tighter than the logger's
    "ceiling_ft": 10000,
    "max_seen_pos_s": 2.0,
    "min_nic": 6,
    "new_flight_gap_s": 600.0,
    "weather_max_age_s": 3 * 3600.0,
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
    "last_seen_utc", "positions", "height_source", "garden_side", "lateral_offset_m",
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
LOG_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2})(?:\.(\d+))?\.jsonl\.gz$")


class Point(NamedTuple):
    t: float
    lat: float
    lon: float
    x: float
    y: float
    baro_ft: Optional[float]
    geom_ft: Optional[float]
    nav_qnh: Optional[float]
    callsign: Optional[str]
    type: Optional[str]
    registration: Optional[str]
    db_flags: Optional[int]
    gs: Optional[float]
    track: Optional[float]
    nic: Optional[int]
    rc: Optional[int]
    rssi: Optional[float]


class Site:
    def __init__(self, config):
        site = config["site"]
        for key in ("lat", "lon", "ground_elevation_m"):
            if not isinstance(site.get(key), (int, float)):
                raise ValueError(f"config site.{key} must be a number")
        self.lat, self.lon = float(site["lat"]), float(site["lon"])
        self.mic_amsl = float(site["ground_elevation_m"]) + float(site.get("mic_height_m", 3.0))
        geoid = config.get("geoid_height_m")
        self.geoid = None if geoid is None else float(geoid)
        s = math.sin(math.radians(self.lat))
        w = math.sqrt(1 - WGS84_E2 * s * s)
        self.metres_per_rad_north = WGS84_A * (1 - WGS84_E2) / w ** 3
        self.metres_per_rad_east = WGS84_A / w * math.cos(math.radians(self.lat))

    def local_xy(self, lat, lon):
        """Metres east and north of the garden. Accurate enough within the analysis radius."""
        return (
            math.radians(lon - self.lon) * self.metres_per_rad_east,
            math.radians(lat - self.lat) * self.metres_per_rad_north,
        )


def qnh_altitude_m(baro_ft, qnh_hpa, temp_c=None):
    """Height above sea level from pressure altitude and QNH.

    Without a temperature this assumes the standard atmosphere. With one, the height is scaled by the
    ratio of the actual to the standard mean temperature of the air below the aircraft, assuming the
    standard lapse rate. That is the usual altimeter temperature correction. It is approximate, and
    the airfield being near sea level keeps the error small.
    """
    standard = (baro_ft - 145366.45 * (1 - (qnh_hpa / 1013.25) ** 0.190284)) * FEET
    if temp_c is None:
        return standard
    half_lapse = LAPSE_RATE * standard / 2
    return standard * (temp_c + 273.15 - half_lapse) / (ISA_SEA_LEVEL_K - half_lapse)


def geometric_altitude_m(geom_ft, geoid_m):
    """Height above sea level from ADS-B geometric altitude, which is above the WGS84 ellipsoid."""
    return geom_ft * FEET - geoid_m


def sound_speed(temp_c):
    return 331.3 * math.sqrt(1 + temp_c / 273.15)


def angle_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class Weather:
    """QNH and temperature by time, from a METAR archive or a simple CSV.

    Accepts a time column called `valid` or `time`, and either a `metar` column or `qnh_hpa`
    with an optional `temp_c`. QNH from a METAR has 0.5 hPa added when metar_qnh_rounded_down
    is set; a qnh_hpa column is taken as exact.
    """

    def __init__(self, entries=(), max_age=DEFAULTS["weather_max_age_s"]):
        self.entries = sorted(entries)
        self.times = [e[0] for e in self.entries]
        self.max_age = max_age

    @classmethod
    def load(cls, path, max_age=DEFAULTS["weather_max_age_s"], metar_rounded_down=True):
        entries = []
        with open(path, newline="") as f:
            for row in csv.DictReader(line for line in f if not line.startswith("#")):
                when = row.get("valid") or row.get("time")
                if not when:
                    continue
                qnh, temp, from_metar = parse_weather_row(row)
                if qnh is not None:
                    if from_metar and metar_rounded_down:
                        qnh += 0.5
                    entries.append((parse_utc(when), qnh, temp))
        return cls(entries, max_age)

    def at(self, t):
        """The latest report no more than max_age old, as (qnh, temp), or (None, None)."""
        i = bisect.bisect_right(self.times, t) - 1
        if i < 0 or t - self.times[i] > self.max_age:
            return None, None
        return self.entries[i][1], self.entries[i][2]


def parse_weather_row(row):
    """Return (qnh, temp, qnh came from a METAR)."""
    metar = row.get("metar") or ""
    from_metar = False
    if row.get("qnh_hpa"):
        qnh = float(row["qnh_hpa"])
    else:
        match = re.search(r"\bQ(\d{4})\b", metar)
        qnh = float(match.group(1)) if match else None
        from_metar = qnh is not None
    temp = None
    if row.get("temp_c"):
        temp = float(row["temp_c"])
    else:
        match = re.search(r"\s(M?\d{2})/(?:M?\d{2})?\s", metar)
        if match:
            temp = float(match.group(1).replace("M", "-"))
    return qnh, temp, from_metar


def parse_utc(text):
    text = text.strip().replace("T", " ").replace("Z", "")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    raise ValueError(f"unreadable time: {text!r}")


def format_utc(t):
    if t is None:
        return ""
    moment = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def log_paths(log_dir, start=None, end=None):
    """Log files in time order. A restart's file (T12.1) comes after the file it follows (T12).

    With start or end, files more than an hour outside the period are skipped.
    """
    found = []
    for path in glob.glob(os.path.join(log_dir, "**", "*.jsonl.gz"), recursive=True):
        match = LOG_NAME.match(os.path.basename(path))
        if match:
            hour = parse_utc(match.group(1).replace("T", " ") + ":00")
            if start is not None and hour + 7200 < start:
                continue
            if end is not None and hour - 3600 >= end:
                continue
            found.append((0, hour, int(match.group(2) or 0), path))
        else:
            found.append((1, 0, 0, path))  # Unexpected names go last, in name order
    return [item[3] for item in sorted(found)]


def read_log_records(paths, report):
    """Yield every readable record. A damaged file is read up to the damage and then reported."""
    for path in paths:
        report["files"] += 1
        try:
            with gzip.open(path, "rb") as f:
                for line in f:
                    report["lines"] += 1
                    try:
                        record = json.loads(line)
                    except ValueError:
                        report["invalid_lines"] += 1
                        continue
                    if isinstance(record, dict):
                        yield record
                    else:
                        report["invalid_lines"] += 1
        except (EOFError, OSError, zlib.error) as error:
            report["damaged_files"].append(f"{os.path.basename(path)}: {error}")


def parse_point(record, site, settings):
    """Return (hex, Point), or None if the record can't be used for this analysis."""
    lat, lon, now = number(record.get("lat")), number(record.get("lon")), number(record.get("now"))
    code = record.get("hex")
    if lat is None or lon is None or now is None or not code:
        return None
    baro = record.get("alt_baro")
    if baro == "ground":
        return None
    baro, geom = number(baro), number(record.get("alt_geom"))
    altitude = baro if baro is not None else geom
    if altitude is not None and altitude > settings["ceiling_ft"]:
        return None
    seen = number(record.get("seen_pos")) or 0.0
    if seen > settings["max_seen_pos_s"]:
        return None
    nic = number(record.get("nic"))
    if nic is not None and nic < settings["min_nic"]:
        return None
    x, y = site.local_xy(lat, lon)
    if math.hypot(x, y) > settings["max_km"] * 1000:
        return None
    callsign = record.get("flight")
    callsign = callsign.strip() or None if isinstance(callsign, str) else None
    return code, Point(
        t=now - seen, lat=lat, lon=lon, x=x, y=y, baro_ft=baro, geom_ft=geom,
        nav_qnh=number(record.get("nav_qnh")),
        callsign=callsign, type=record.get("t"), registration=record.get("r"), db_flags=record.get("dbFlags"),
        gs=number(record.get("gs")), track=number(record.get("track")), nic=nic,
        rc=number(record.get("rc")), rssi=number(record.get("rssi")),
    )


class FlightBuilder:
    """Group positions into flights as they arrive, finishing a flight once its aircraft goes quiet.

    A gap of gap_s either way in time starts a new flight; a backwards jump that large means the
    clock was stepped. Each flight is numbered when its first position arrives.
    """

    def __init__(self, gap_s):
        self.gap_s = gap_s
        self.open = {}
        self.next_id = 1

    def add(self, code, point):
        """Add a position. Returns a finished flight as (id, hex, points), or None."""
        finished = None
        current = self.open.get(code)
        if current and abs(point.t - current[2][-1].t) >= self.gap_s:
            finished = self._finish(code)
            current = None
        if current is None:
            current = self.open[code] = (self.next_id, code, [])
            self.next_id += 1
        current[2].append(point)
        return finished

    def finish_quiet(self, now):
        """Finish every flight with nothing for gap_s before now."""
        quiet = [code for code, (_, _, points) in self.open.items() if now - points[-1].t >= self.gap_s]
        return [self._finish(code) for code in quiet]

    def finish_all(self):
        return [self._finish(code) for code in list(self.open)]

    def _finish(self, code):
        flight_id, code, points = self.open.pop(code)
        points.sort(key=lambda p: p.t)
        kept = [points[0]]
        for point in points[1:]:
            if point.t > kept[-1].t:
                kept.append(point)
        return flight_id, code, kept


def most_common(values):
    values = [v for v in values if v not in (None, "")]
    return collections.Counter(values).most_common(1)[0][0] if values else None


def choose_heights(points, site, weather, settings):
    """Work out both heights for every position, then choose one source for the whole flight.

    Geometric is preferred, because it doesn't depend on pressure or temperature. Disagreement of
    more than height_disagreement_m is flagged. Geometric is only rejected, in favour of QNH, when
    the disagreement matches the known fault of an aircraft sending height above sea level as
    geometric: QNH minus geometric close to the geoid height. Other disagreements could be the
    weather's fault, such as a stale QNH, so they're flagged but geometric is kept.
    Returns (source, used, qnh heights, geometric heights, median QNH minus geometric, flags).
    """
    qnh_heights, geom_heights = [], []
    for p in points:
        qnh, temp = weather.at(p.t)
        if not settings["temperature_correction"]:
            temp = None
        qnh_heights.append(
            qnh_altitude_m(p.baro_ft, qnh, temp) if p.baro_ft is not None and qnh is not None else None
        )
        geom_heights.append(
            geometric_altitude_m(p.geom_ft, site.geoid)
            if p.geom_ft is not None and site.geoid is not None
            else None
        )
    differences = [q - g for q, g in zip(qnh_heights, geom_heights) if q is not None and g is not None]
    disagreement = statistics.median(differences) if differences else None
    disagrees = disagreement is not None and abs(disagreement) > settings["height_disagreement_m"]
    enough = len(points) / 2
    has_geom = sum(h is not None for h in geom_heights) >= enough
    has_qnh = sum(h is not None for h in qnh_heights) >= enough
    flags = ["heights_disagree"] if disagrees else []
    sea_level_fault = (
        disagrees and site.geoid is not None
        and abs(disagreement - site.geoid) <= settings["sea_level_fault_tolerance_m"]
    )
    if has_geom and not (sea_level_fault and has_qnh):
        return "geometric", geom_heights, qnh_heights, geom_heights, disagreement, flags
    if has_qnh:
        if has_geom:
            flags.append("geometric_rejected")
        return "qnh", qnh_heights, qnh_heights, geom_heights, disagreement, flags
    return "none", [None] * len(points), qnh_heights, geom_heights, disagreement, flags


def closest_on_segment(a, b):
    """Fraction along the segment from a to b nearest the origin, for tuples of any length."""
    delta = [q - p for p, q in zip(a, b)]
    length = sum(d * d for d in delta)
    if length == 0:
        return 0.0
    return min(1.0, max(0.0, -sum(p * d for p, d in zip(a, delta)) / length))


def closest_approach(vectors):
    """Return (segment index, fraction, distance) for the path's closest point to the origin."""
    if len(vectors) == 1:
        return 0, 0.0, math.sqrt(sum(c * c for c in vectors[0]))
    best = None
    for i in range(len(vectors) - 1):
        u = closest_on_segment(vectors[i], vectors[i + 1])
        at = [p + u * (q - p) for p, q in zip(vectors[i], vectors[i + 1])]
        distance = math.sqrt(sum(c * c for c in at))
        if best is None or distance < best[2]:
            best = (i, u, distance)
    return best


def path_slope(points, heights, centre, settings):
    """Fit height against ground distance within a window around the closest point.

    Returns (signed angle in degrees, heading in degrees), either of which may be None.
    """
    distance = [0.0]
    for a, b in zip(points, points[1:]):
        distance.append(distance[-1] + math.hypot(b.x - a.x, b.y - a.y))
    window = settings["slope_window_m"]
    chosen = [i for i, d in enumerate(distance) if abs(d - distance[centre]) <= window]
    if len(chosen) < 2:
        return None, None
    first, last = points[chosen[0]], points[chosen[-1]]
    east, north = last.x - first.x, last.y - first.y
    length = math.hypot(east, north)
    heading = math.degrees(math.atan2(east, north)) % 360 if length else None
    if not length:
        return None, heading
    # Measure distance along the straight line through the window, not by adding up the steps between
    # positions: position noise makes every step look longer, which would understate the angle.
    ux, uy = east / length, north / length
    fit = [((points[i].x - first.x) * ux + (points[i].y - first.y) * uy, heights[i]) for i in chosen if heights[i] is not None]
    if len(fit) < 5 or fit[-1][0] - fit[0][0] < settings["min_slope_span_m"]:
        return None, heading
    mean_d = sum(d for d, _ in fit) / len(fit)
    mean_h = sum(h for _, h in fit) / len(fit)
    spread = sum((d - mean_d) ** 2 for d, _ in fit)
    if spread == 0:
        return None, heading
    slope = sum((d - mean_d) * (h - mean_h) for d, h in fit) / spread
    return math.degrees(math.atan(slope)), heading


def label_flight(heading, trend, height_above_mic, lateral, settings):
    if heading is None or height_above_mic is None:
        return "other"
    if height_above_mic > settings["max_label_height_m"] or lateral > settings["max_label_offset_m"]:
        return "other"
    west = settings["runway_27_heading_deg"]
    tolerance = settings["heading_tolerance_deg"]
    if trend == "descending" and angle_difference(heading, west) <= tolerance:
        return "rwy27_arrival"
    if trend == "climbing" and angle_difference(heading, (west + 180) % 360) <= tolerance:
        return "rwy09_departure"
    return "other"


def garden_side(heading, closest_x, closest_y):
    """Which side of the track the garden is on, by compass, chosen to suit the track's direction."""
    if heading is not None and (angle_difference(heading, 0) < 45 or angle_difference(heading, 180) < 45):
        return "east" if closest_x < 0 else "west"
    return "north" if closest_y < 0 else "south"


def interpolate_height(heights, i, j, u):
    """Height at fraction u between positions i and j, using the nearest known heights."""
    if heights[i] is not None and heights[j] is not None:
        return heights[i] + u * (heights[j] - heights[i])
    for k in (i, j) if u < 0.5 else (j, i):
        if heights[k] is not None:
            return heights[k]
    return None


def linear_fit(ts, values):
    """Least-squares straight line, returned as (value at t = 0, rate)."""
    n = len(ts)
    mean_t, mean_v = sum(ts) / n, sum(values) / n
    spread = sum((t - mean_t) ** 2 for t in ts)
    rate = sum((t - mean_t) * (v - mean_v) for t, v in zip(ts, values)) / spread
    return mean_v - rate * mean_t, rate


def smoothed_closest(points, heights, centre_t, window_s, mic_amsl):
    """Closest approach from straight lines fitted to the positions within window_s of centre_t.

    Taking the nearest of many noisy positions favours those that happen to fall near the garden,
    so it reads short. Fitting lines over about 40 s averages the noise, and the 25 ft altitude steps.
    Returns None if there aren't enough positions, so the caller can fall back to the raw track.
    """
    indices = [k for k, p in enumerate(points) if abs(p.t - centre_t) <= window_s]
    chosen = [points[k] for k in indices]
    if len(chosen) < 6 or chosen[-1].t - chosen[0].t < window_s:
        return None
    ts = [p.t - centre_t for p in chosen]
    x0, vx = linear_fit(ts, [p.x for p in chosen])
    y0, vy = linear_fit(ts, [p.y for p in chosen])
    lo, hi = ts[0], ts[-1]
    speed2 = vx * vx + vy * vy
    tau = min(hi, max(lo, -(x0 * vx + y0 * vy) / speed2)) if speed2 else 0.0
    result = {
        "ground_time": centre_t + tau, "x": x0 + vx * tau, "y": y0 + vy * tau,
        "lateral": math.hypot(x0 + vx * tau, y0 + vy * tau), "height": None, "slant": None,
    }
    known = [(t, heights[k]) for t, k in zip(ts, indices) if heights[k] is not None]
    if len(known) >= 6 and known[-1][0] - known[0][0] >= window_s:
        z0, vz = linear_fit([t for t, _ in known], [h - mic_amsl for _, h in known])
        result["height"] = z0 + vz * tau + mic_amsl
        total2 = speed2 + vz * vz
        tau3 = min(hi, max(lo, -(x0 * vx + y0 * vy + z0 * vz) / total2)) if total2 else 0.0
        at = (x0 + vx * tau3, y0 + vy * tau3, z0 + vz * tau3)
        result.update(slant=math.sqrt(sum(c * c for c in at)), slant_time=centre_t + tau3, slant_point=at)
    return result


def angle_from_vertical(vector):
    """Degrees from straight up, for (east, north, up) relative to the microphone."""
    return math.degrees(math.atan2(math.hypot(vector[0], vector[1]), vector[2]))


def path_trend(angle, level_deg):
    if angle is None:
        return None
    return "climbing" if angle > level_deg else "descending" if angle < -level_deg else "level"


def position_rows(flight_id, code, points, used, qnh_heights, geom_heights, mic_amsl, speed):
    """One positions.csv row per position, with its sound delay to the microphone."""
    rows = []
    for p, h, q, g in zip(points, used, qnh_heights, geom_heights):
        ground = math.hypot(p.x, p.y)
        above = None if h is None else h - mic_amsl
        slant = None if above is None else math.hypot(ground, above)
        delay = None if slant is None else slant / speed
        rows.append({
            "t": p.t, "flight_id": flight_id, "hex": code, "emission_time_utc": format_utc(p.t),
            "arrival_time_utc": "" if delay is None else format_utc(p.t + delay),
            "lat": p.lat, "lon": p.lon, "east_m": p.x, "north_m": p.y, "ground_distance_m": ground,
            "height_qnh_amsl_m": q, "height_geometric_amsl_m": g, "height_used_amsl_m": h,
            "height_above_mic_m": above, "slant_m": slant,
            "angle_from_vertical_deg": None if above is None else math.degrees(math.atan2(ground, above)),
            "sound_delay_s": delay, "ground_speed_kt": p.gs, "track_deg": p.track, "nic": p.nic,
            "rc": p.rc, "rssi": p.rssi,
        })
    return rows


def raw_slant_closest(points, used, mic_amsl):
    """Closest point to the microphone in three dimensions along the raw track, using only
    positions with a height. Returns (distance, time, (east, north, up)), or None."""
    known = [k for k, h in enumerate(used) if h is not None]
    if not known:
        return None
    vectors = [(points[k].x, points[k].y, used[k] - mic_amsl) for k in known]
    a, v, slant = closest_approach(vectors)
    b = min(a + 1, len(known) - 1)
    when = points[known[a]].t + v * (points[known[b]].t - points[known[a]].t)
    return slant, when, [c + v * (d - c) for c, d in zip(vectors[a], vectors[b])]


def closest_point(points, used, mic_amsl, settings, flags):
    """The flight's closest approach to the garden, along the ground and in three dimensions.

    Uses straight lines fitted around the closest point when there are enough positions, and the
    raw track otherwise or for whatever the fit can't give. Adds track-end and gap flags.
    Returns (closest, index of the nearest position).
    """
    i, u, lateral = closest_approach([(p.x, p.y) for p in points])
    j = min(i + 1, len(points) - 1)
    if (i == 0 and u == 0) or (j == len(points) - 1 and u == 1) or len(points) == 1:
        flags.append("closest_point_at_track_end")
    if points[j].t - points[i].t > settings["max_gap_near_site_s"]:
        flags.append("gap_at_closest_point")
    closest = {
        "lateral": lateral,
        "ground_time": points[i].t + u * (points[j].t - points[i].t),
        "x": points[i].x + u * (points[j].x - points[i].x),
        "y": points[i].y + u * (points[j].y - points[i].y),
        "height": interpolate_height(used, i, j, u),
        "slant": None, "slant_time": None, "slant_point": None,
    }
    raw_slant = raw_slant_closest(points, used, mic_amsl)
    if raw_slant:
        closest.update(zip(("slant", "slant_time", "slant_point"), raw_slant))
    smooth = smoothed_closest(points, used, closest["ground_time"], settings["smoothing_window_s"], mic_amsl)
    if smooth:
        closest.update({key: smooth[key] for key in ("lateral", "ground_time", "x", "y")})
        if smooth["height"] is not None:
            closest.update({key: smooth[key] for key in ("height", "slant", "slant_time", "slant_point")})
    nearest = i if u < 0.5 else j
    return closest, nearest


def overlaps(intervals, start, end):
    return any(a <= end and b >= start for a, b in intervals)


def analyse_flight(flight_id, code, points, site, weather, settings, unsynced=()):
    """Return (flight row, position rows) for one flight.

    unsynced is a list of (start, end) times when the logger's clock wasn't synchronised.
    """
    source, used, qnh_heights, geom_heights, disagreement, flags = choose_heights(points, site, weather, settings)
    first_qnh, first_temp = weather.at(points[0].t)
    speed = sound_speed(first_temp) if first_temp is not None else DEFAULT_SOUND_SPEED
    if first_temp is None:
        flags.append("assumed_sound_speed")
    if first_qnh is None:
        flags.append("no_qnh")
    if source == "none":
        flags.append("no_height")

    rows = position_rows(flight_id, code, points, used, qnh_heights, geom_heights, site.mic_amsl, speed)

    closest, nearest = closest_point(points, used, site.mic_amsl, settings, flags)
    lateral, ground_time, ground_height = closest["lateral"], closest["ground_time"], closest["height"]
    slant, slant_time, at = closest["slant"], closest["slant_time"], closest["slant_point"]
    angle = None if at is None else angle_from_vertical(at)
    delay = None if slant is None else slant / speed
    arrival = None if slant is None else slant_time + delay

    path_angle, heading = path_slope(points, used, nearest, settings)
    trend = path_trend(path_angle, settings["level_angle_deg"])
    above_at_closest = None if ground_height is None else ground_height - site.mic_amsl
    label = label_flight(heading, trend, above_at_closest, lateral, settings)

    start, end = points[0].t, points[-1].t
    if overlaps(unsynced, start, end):
        flags.append("clock_not_synchronised")

    callsign = most_common(p.callsign for p in points)
    aircraft_type = most_common(p.type for p in points)
    for row in rows:
        row.update(callsign=callsign, type=aircraft_type)
    speeds = [p.gs for p in points if p.gs is not None]
    near_speeds = [p.gs for p in points if p.gs is not None and abs(p.t - ground_time) <= 15]
    aircraft_qnh = [p.nav_qnh for p in points if p.nav_qnh is not None]
    flight = {
        "flight_id": flight_id, "hex": code, "callsign": callsign, "type": aircraft_type,
        "registration": most_common(p.registration for p in points),
        "db_flags": most_common(p.db_flags for p in points), "label": label,
        "first_seen_utc": format_utc(start), "last_seen_utc": format_utc(end),
        "positions": len(points), "height_source": source,
        "garden_side": garden_side(heading, closest["x"], closest["y"]), "lateral_offset_m": lateral,
        "closest_ground_time_utc": format_utc(ground_time),
        "height_at_closest_ground_amsl_m": ground_height,
        "closest_slant_time_utc": format_utc(slant_time), "closest_slant_m": slant,
        "angle_from_vertical_deg": angle, "sound_delay_s": delay,
        "sound_arrival_time_utc": format_utc(arrival), "heading_deg": heading,
        "path_angle_deg": None if path_angle is None else abs(path_angle), "path_trend": trend,
        "ground_speed_kt": statistics.median(near_speeds or speeds) if speeds else None,
        "qnh_hpa": first_qnh, "temp_c": first_temp, "sound_speed_m_s": speed,
        "median_qnh_minus_geometric_m": disagreement,
        "aircraft_qnh_hpa": statistics.median(aircraft_qnh) if aircraft_qnh else None,
        "flags": ";".join(flags),
    }
    return flight, rows


def read_health(log_dir):
    """Read the logger's health log: when the clock wasn't synchronised, and what went wrong.

    The clock is treated as unsynchronised from each record that says so until the next record
    that says it's synchronised, or to the end of the log.
    """
    entries = read_health_log(log_dir)
    unsynced, start = [], None
    for entry in entries:
        synced = (entry.get("clock") or {}).get("synchronised")
        if synced is False and start is None:
            start = entry["time"]
        elif synced is True and start is not None:
            unsynced.append((start, entry["time"]))
            start = None
    if start is not None:
        unsynced.append((start, entries[-1]["time"]))
    events = collections.Counter(e["event"] for e in entries if e.get("event"))
    return {"records": len(entries), "unsynced": unsynced, "events": events, "entries": entries}


def logger_was_listening(entries, start, end, max_spacing_s=900):
    """True if the health log shows the logger running, connected and receiving from start to end.

    A gap in the kept data is then a quiet sky near the garden, not lost data. Without health
    records covering the whole gap, it counts as lost.
    """
    inside = [e for e in entries if start <= e["time"] <= end]
    times = [start] + [e["time"] for e in inside] + [end]
    if any(b - a > max_spacing_s for a, b in zip(times, times[1:])):
        return False
    if any(e.get("connected") is False or e.get("event") in ("start", "stop", "disconnected") for e in inside):
        return False
    return sum(e.get("lines") or 0 for e in inside) > 0


def rounded(value):
    return round(value, 3) if isinstance(value, float) else value


class CsvOut:
    def __init__(self, path, columns):
        self.file = open(path, "w", newline="")
        self.columns = columns
        self.writer = csv.DictWriter(self.file, columns, extrasaction="ignore")
        self.writer.writeheader()
        self.rows = 0

    def write(self, row):
        self.writer.writerow({key: "" if row.get(key) is None else rounded(row[key]) for key in self.columns})
        self.rows += 1

    def close(self):
        self.file.close()


def median_text(values, places=1):
    values = [v for v in values if v is not None]
    return f"{statistics.median(values):.{places}f}" if values else "-"


def build_summary(flights, report, weather_loaded, geoid_known, health):
    lines = [
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
    if not health["records"]:
        lines.append("WARNING: no health log, so clock problems can't be detected")
    for start, end in health["unsynced"]:
        lines.append(f"WARNING: clock not synchronised from {format_utc(start)} to {format_utc(end)}")
    for event in ("disconnected", "disk_low_paused", "write_error", "start"):
        if health["events"].get(event):
            lines.append(f"LOGGER: {health['events'][event]} '{event}' events")
    for item in report["damaged_files"]:
        lines.append(f"DAMAGED: {item}")
    if report["unsynced_lines"]:
        lines.append(f"WARNING: {report['unsynced_lines']} lines were stamped while the clock wasn't "
                     "synchronised, so their times may be wrong")
    for start, end, listening in report["gaps"]:
        if listening:
            lines.append(f"QUIET over 30 minutes, logger running: {format_utc(start)} to {format_utc(end)}")
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
    health = read_health(log_dir)
    report = {"files": 0, "lines": 0, "invalid_lines": 0, "damaged_files": [], "gaps": [], "unsynced_lines": 0}
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

    latest = -math.inf
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
        latest = max(latest, now)
        count += 1
        if count % 20000 == 0:
            for finished in builder.finish_quiet(latest):
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
    summary = build_summary(flights, report, bool(weather.entries), site.geoid is not None, health)
    with open(os.path.join(out_dir, "summary.txt"), "w") as f:
        f.write(summary)
    write_viewer(os.path.join(out_dir, "viewer.html"), viewer_data(flights, tracks, summary, site, config))
    return flights, summary


VIEWER_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_template.html")


def viewer_track(rows, spacing_s=1.0):
    """Thin a flight's positions for drawing: [seconds from start, east m, north m, height above mic m]."""
    track, last = [], None
    for row in rows:
        if last is not None and row["t"] - last < spacing_s and row is not rows[-1]:
            continue
        above = row["height_above_mic_m"]
        track.append([
            round(row["t"] - rows[0]["t"], 1), round(row["east_m"]), round(row["north_m"]),
            None if above is None else round(above),
        ])
        last = row["t"]
    return track


def viewer_data(flights, tracks, summary, site, config):
    """Everything the viewer shows. Deliberately no latitudes or longitudes, so the garden isn't revealed."""
    return {
        "generated_utc": format_utc(dt.datetime.now(dt.timezone.utc).timestamp()),
        "simulated": bool(config.get("simulated")),
        "mic_amsl_m": round(site.mic_amsl, 2),
        "summary": summary,
        "flights": [{key: rounded(value) for key, value in flight.items()} for flight in flights],
        "tracks": {str(key): value for key, value in tracks.items()},
    }


def write_viewer(path, data):
    with open(VIEWER_TEMPLATE) as f:
        template = f.read()
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    with open(path, "w") as f:
        f.write(template.replace("__ADSB_DATA__", payload, 1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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

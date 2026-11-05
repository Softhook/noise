"""Work out one flight's heights, closest approach to the garden, sound delay, path angle and label."""

from __future__ import annotations

import math
import statistics

from .atmosphere import DEFAULT_SOUND_SPEED, geometric_altitude_m, qnh_altitude_m, sound_speed
from .common import format_utc, most_common, overlaps
from .geometry import angle_difference, angle_from_vertical, closest_approach, garden_side, linear_fit


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


def path_trend(angle, level_deg):
    if angle is None:
        return None
    return "climbing" if angle > level_deg else "descending" if angle < -level_deg else "level"


def interpolate_height(heights, i, j, u):
    """Height at fraction u between positions i and j, using the nearest known heights."""
    if heights[i] is not None and heights[j] is not None:
        return heights[i] + u * (heights[j] - heights[i])
    for k in (i, j) if u < 0.5 else (j, i):
        if heights[k] is not None:
            return heights[k]
    return None


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

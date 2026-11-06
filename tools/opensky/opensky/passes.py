"""OpenSky state vectors into one closest approach to NMT6 per aircraft pass.

Heights: geoaltitude is GPS height above the WGS84 ellipsoid, so the geoid height (about 45 m in
London) is subtracted to give height above sea level, as WebTrak gives. baroaltitude is pressure
altitude (1013.25 hPa) and needs a QNH correction, which isn't done here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .common import NMT6, iso, number
from .geometry import closest_approach

PASS_GAP_S = 300  # An aircraft unseen for this long has left; a new pass starts when it returns

CSV_FIELDS = ["closest_utc", "callsign", "icao24", "distance_m", "geo_msl_m", "baro_alt_m", "positions",
              "point_gap_s", "receivers"]


@dataclass
class Pass:
    t: float  # Time of closest approach, Unix seconds
    icao24: str
    callsign: str
    distance_m: int
    geo_msl_m: int | None  # GPS height above sea level
    baro_alt_m: int | None  # Pressure altitude, uncorrected
    positions: int
    point_gap_s: float  # Seconds between positions either side of the closest approach
    receivers: int  # Most receivers that heard one state

    @property
    def closest_utc(self):
        return iso(self.t)

    def row(self):
        return {field: getattr(self, field) for field in CSV_FIELDS}


def positions(states):
    """One aircraft's airborne positions, each once, at the time it was received, in time order.

    A state vector repeats the last position until a new one arrives, so states with the same
    lastposupdate are the same position. Trino's query already sends each position and only airborne
    ones, but a position can be in two hour partitions.
    """
    points, seen = [], set()
    for s in sorted(states, key=lambda s: s["time"]):
        t = number(s["lastposupdate"]) or float(s["time"])
        if s.get("onground") or number(s["lat"]) is None or number(s["lon"]) is None or t in seen:
            continue
        seen.add(t)
        points.append({**s, "t": t})
    return sorted(points, key=lambda p: p["t"])


def split_passes(points, gap_s=PASS_GAP_S):
    """Split time-ordered points wherever the aircraft went unseen for more than gap_s."""
    groups = []
    for p in points:
        if groups and p["t"] - groups[-1][-1]["t"] <= gap_s:
            groups[-1].append(p)
        else:
            groups.append([p])
    return groups


def interpolate(points, t, key):
    """Linear value of points[key] at time t, from the neighbouring points that have one."""
    have = [(p["t"], v) for p in points if (v := number(p[key])) is not None]
    for (t0, v0), (t1, v1) in zip(have, have[1:]):
        if t0 <= t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return min(have, key=lambda tv: abs(tv[0] - t))[1] if have else None


def summarise(icao24, points, t, d, geoid_m):
    """One pass, whose closest approach is d metres at time t."""
    gaps = [b["t"] - a["t"] for a, b in zip(points, points[1:])]
    near = min(range(len(points)), key=lambda i: abs(points[i]["t"] - t))
    geo = interpolate(points, t, "geoaltitude")
    baro = interpolate(points, t, "baroaltitude")
    callsigns = Counter(str(p["callsign"]).strip() for p in points if p.get("callsign"))
    return Pass(
        t=t, icao24=icao24,
        callsign=callsigns.most_common(1)[0][0] if callsigns else "",
        distance_m=round(d),
        geo_msl_m=round(geo - geoid_m) if geo is not None else None,
        baro_alt_m=round(baro) if baro is not None else None,
        positions=len(points),
        point_gap_s=round(max(gaps[max(0, near - 1):near + 1] or [0]), 1),
        receivers=int(max(number(p["receivers"]) or 0 for p in points)),
    )


def passes_near(states, begin, end, radius_m, geoid_m, origin=NMT6):
    """Passes within radius_m of origin whose closest approach is from begin to end, in time order."""
    by_aircraft = {}
    for s in states:
        by_aircraft.setdefault(s["icao24"], []).append(s)
    found = []
    for icao24, aircraft_states in by_aircraft.items():
        for group in split_passes(positions(aircraft_states)):
            if len(group) < 2:
                continue
            t, d = closest_approach([(p["t"], float(p["lat"]), float(p["lon"])) for p in group], origin)
            if d <= radius_m and begin <= t <= end:
                found.append(summarise(icao24, group, t, d, geoid_m))
    return sorted(found, key=lambda p: p.t)

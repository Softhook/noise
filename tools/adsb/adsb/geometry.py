"""Positions relative to the garden, and the closest-approach geometry used by the analysis.

Used on the Pi too (distance_km), so it must only import the standard library.
"""

from __future__ import annotations

import math


WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014

def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance, which is accurate enough for choosing what to keep."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))

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


def angle_difference(a, b):
    return abs((a - b + 180) % 360 - 180)


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


def linear_fit(ts, values):
    """Least-squares straight line, returned as (value at t = 0, rate)."""
    n = len(ts)
    mean_t, mean_v = sum(ts) / n, sum(values) / n
    spread = sum((t - mean_t) ** 2 for t in ts)
    rate = sum((t - mean_t) * (v - mean_v) for t, v in zip(ts, values)) / spread
    return mean_v - rate * mean_t, rate


def angle_from_vertical(vector):
    """Degrees from straight up, for (east, north, up) relative to the microphone."""
    return math.degrees(math.atan2(math.hypot(vector[0], vector[1]), vector[2]))


def garden_side(heading, closest_x, closest_y):
    """Which side of the track the garden is on, by compass, chosen to suit the track's direction."""
    if heading is not None and (angle_difference(heading, 0) < 45 or angle_difference(heading, 180) < 45):
        return "east" if closest_x < 0 else "west"
    return "north" if closest_y < 0 else "south"

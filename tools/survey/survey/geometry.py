"""Local coordinates, distances, and positions along a track. The core's own, so tools/adsb can change freely.

A track is a time-ordered list of tuples whose first four items are (t, lat, lon, height_m or
None); anything after those is ignored here.
"""

from __future__ import annotations

import bisect
import math

WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014
# A track is only interpolated between positions this close in time. Further apart is a hole in
# the source's data (OpenSky's tracks have them where an aircraft left its box and came back), and
# a straight line across it isn't where the aircraft was.
MAX_INTERPOLATE_S = 30


class Frame:
    """Metres east and north of a point. Accurate enough within a few tens of kilometres."""

    def __init__(self, lat, lon):
        self.lat, self.lon = float(lat), float(lon)
        s = math.sin(math.radians(self.lat))
        w = math.sqrt(1 - WGS84_E2 * s * s)
        self.per_rad_north = WGS84_A * (1 - WGS84_E2) / w ** 3
        self.per_rad_east = WGS84_A / w * math.cos(math.radians(self.lat))

    def xy(self, lat, lon):
        return (math.radians(lon - self.lon) * self.per_rad_east, math.radians(lat - self.lat) * self.per_rad_north)


def closest_approach(points, frame, mic_amsl=None):
    """Closest ground approach of a track to the frame's origin.

    The closest point is looked for along each segment between neighbouring positions, not only at
    the positions, but never across a hole of more than MAX_INTERPOLATE_S. Returns (t, ground_m,
    height_m, slant_m, at_track_end), with height and slant None when unknown, or None for an empty
    track. at_track_end is True when the closest point is at an edge of the source's data: the
    track's first or last position, or a position beside a hole. The aircraft may then have come
    closer where the source has no positions.
    """
    if not points:
        return None
    pts = [(p[0], *frame.xy(p[1], p[2]), p[3]) for p in points]
    n = len(pts)
    # Positions at an edge of the data: the ends, and either side of a hole
    edge = [i == 0 or i == n - 1 or pts[i][0] - pts[i - 1][0] > MAX_INTERPOLATE_S
            or pts[i + 1][0] - pts[i][0] > MAX_INTERPOLATE_S for i in range(n)]
    best = None
    for i in range(n):
        a = pts[i]
        j = i + 1 if i + 1 < n and pts[i + 1][0] - a[0] <= MAX_INTERPOLATE_S else i
        b = pts[j]
        dx, dy = b[1] - a[1], b[2] - a[2]
        length = dx * dx + dy * dy
        f = 0.0 if length == 0 else min(1.0, max(0.0, -(a[1] * dx + a[2] * dy) / length))
        d = math.hypot(a[1] + f * dx, a[2] + f * dy)
        if best is None or d < best[1]:
            if a[3] is not None and b[3] is not None:
                h = a[3] + f * (b[3] - a[3])
            else:
                h = a[3] if f < 0.5 else b[3]
            at_edge = (f == 0.0 and edge[i]) or (f == 1.0 and edge[j])
            best = (a[0] + f * (b[0] - a[0]), d, h, at_edge)
    t, d, h, at_edge = best
    slant = None if h is None or mic_amsl is None else math.hypot(d, h - mic_amsl)
    return t, d, h, slant, at_edge


def distance_m(frame, lat, lon):
    x, y = frame.xy(lat, lon)
    return math.hypot(x, y)


def apart_m(a, b):
    """Ground distance between two (lat, lon, ...) points, flat-earth: fine over a few kilometres."""
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111195, (a[1] - b[1]) * 111195 * math.cos(lat))


def position_at(points, t, times=None):
    """(lat, lon, height) interpolated at time t along a track; the nearest end position outside
    it. times: the points' times, if already worked out."""
    times = times or [p[0] for p in points]
    i = bisect.bisect_left(times, t)
    if i == 0 or i == len(points):
        p = points[0] if i == 0 else points[-1]
        return p[1], p[2], p[3]
    a, b = points[i - 1], points[i]
    f = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
    h = None if a[3] is None or b[3] is None else a[3] + f * (b[3] - a[3])
    return a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), h

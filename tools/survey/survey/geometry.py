"""Local coordinates around a receptor, and closest approach. The core's own, so tools/adsb can change freely."""

from __future__ import annotations

import math

WGS84_A = 6378137.0
WGS84_E2 = 0.00669437999014


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
    """Closest ground approach of a time-ordered track to the frame's origin.

    points: [(t, lat, lon, height_m or None)]. The closest point is looked for along each segment
    between neighbouring positions, not only at the positions. Returns (t, ground_m, height_m,
    slant_m, at_track_end), with height and slant None when unknown, or None for an empty track.
    at_track_end is True when the closest point is the track's first or last position.
    """
    if not points:
        return None
    pts = [(t, *frame.xy(lat, lon), h) for t, lat, lon, h in points]
    best = None
    for i in range(len(pts)):
        a = pts[i]
        b = pts[i + 1] if i + 1 < len(pts) else a
        dx, dy = b[1] - a[1], b[2] - a[2]
        length = dx * dx + dy * dy
        f = 0.0 if length == 0 else min(1.0, max(0.0, -(a[1] * dx + a[2] * dy) / length))
        x, y = a[1] + f * dx, a[2] + f * dy
        d = math.hypot(x, y)
        if best is None or d < best[1]:
            if a[3] is not None and b[3] is not None:
                h = a[3] + f * (b[3] - a[3])
            else:
                h = a[3] if f < 0.5 else b[3]
            best = (a[0] + f * (b[0] - a[0]), d, h)
    t, d, h = best
    slant = None if h is None or mic_amsl is None else math.hypot(d, h - mic_amsl)
    return t, d, h, slant, t <= pts[0][0] or t >= pts[-1][0]


def distance_m(frame, lat, lon):
    x, y = frame.xy(lat, lon)
    return math.hypot(x, y)

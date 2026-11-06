"""Distances from NMT6. Flat-earth is fine over the few kilometres the survey covers."""

from __future__ import annotations

import math

from .common import EARTH_RADIUS_M, NMT6


def local_xy(lat, lon, origin=NMT6):
    """Metres east and north of origin."""
    x = math.radians(lon - origin[1]) * EARTH_RADIUS_M * math.cos(math.radians(origin[0]))
    y = math.radians(lat - origin[0]) * EARTH_RADIUS_M
    return x, y


def closest_approach(points, origin=NMT6):
    """(time, ground distance m) of the closest approach to origin, interpolated between points.

    points: [(t, lat, lon)] in time order, at least one.
    """
    xy = [(t, *local_xy(lat, lon, origin)) for t, lat, lon in points]
    best = min(((t, math.hypot(x, y)) for t, x, y in xy), key=lambda td: td[1])
    for (t0, x0, y0), (t1, x1, y1) in zip(xy, xy[1:]):
        dx, dy = x1 - x0, y1 - y0
        if not (dx or dy):
            continue
        f = max(0.0, min(1.0, -(x0 * dx + y0 * dy) / (dx * dx + dy * dy)))
        d = math.hypot(x0 + f * dx, y0 + f * dy)
        if d < best[1]:
            best = (t0 + f * (t1 - t0), d)
    return best


def box_around(centre, half_side_m):
    """(lat min, lat max, lon min, lon max) of a box half_side_m either side of centre."""
    dlat = math.degrees(half_side_m / EARTH_RADIUS_M)
    dlon = dlat / math.cos(math.radians(centre[0]))
    return centre[0] - dlat, centre[0] + dlat, centre[1] - dlon, centre[1] + dlon

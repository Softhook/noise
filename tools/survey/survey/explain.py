"""Why a source has no flight in a pass: was the aircraft ever where, and when, that source could see it?

Each adapter says what its source can see (`limits`): a height ceiling, and the areas it covers.
With the coverage table, which says when, that's enough to tell a pass a source couldn't have seen
from one it should have seen and didn't. Only the second kind needs looking into: it's a gap in
the source's data, or a pass `link` failed to join.

limits: {"ceiling_m": metres above sea level or None, "areas": [(kind, lat, lon, km)], "any": bool}
where kind is "circle" (within km of the point) or "box" (within km either side of it, east and
north). With "any", the aircraft need be in only one of the areas, otherwise in all of them.
"""

from __future__ import annotations

import bisect
import math

from .common import parse_time
from .geometry import Frame

NO_DATA = "no data"
OUTSIDE = "outside its area"
ABOVE = "above its ceiling"
UNEXPLAINED = "unexplained"
REASONS = (NO_DATA, OUTSIDE, ABOVE, UNEXPLAINED)

MIN_VISIBLE_S = 20  # An aircraft seen for less than this, where the source could see it, isn't counted
MAX_STEP_S = 60  # Time between two positions counts only if they're this close together
# A ceiling is in pressure altitude, and heights here are radar, QNH or GPS heights, so a height
# this close below the ceiling may still have been above it for the source. Pressure altitude is
# about 8.3 m higher for each hPa that QNH is below 1013.25: 300 m covers QNH down to about 977 hPa,
# lower than London sees in all but the deepest storms. (The other way, with a high QNH, the
# source could see higher than its ceiling, which only makes a miss less likely to be explained.)
CEILING_MARGIN_M = 300


def prepare(limits):
    """limits with each area's Frame worked out once."""
    areas = [(kind, Frame(lat, lon), km * 1000) for kind, lat, lon, km in limits["areas"]]
    return {**limits, "frames": areas}


def in_area(limits, lat, lon):
    tests = []
    for kind, frame, m in limits["frames"]:
        x, y = frame.xy(lat, lon)
        tests.append(math.hypot(x, y) <= m if kind == "circle" else max(abs(x), abs(y)) <= m)
    if not tests:
        return True
    return any(tests) if limits["any"] else all(tests)


def _span(points, keep):
    """Seconds spent in the points where keep is True, counting only steps both ends of which are kept."""
    return sum(b[0] - a[0] for a, b, ka, kb in zip(points, points[1:], keep, keep[1:])
               if ka and kb and b[0] - a[0] <= MAX_STEP_S)


class Coverage:
    """When a source has data, merged into separate runs, so a time is looked up by bisection
    rather than against every row: the logger's health log gives a row per run between outages."""

    def __init__(self, spans):
        self.starts, self.ends = [], []
        for a, b in sorted(spans):
            if self.ends and a <= self.ends[-1]:
                self.ends[-1] = max(self.ends[-1], b)
            else:
                self.starts.append(a)
                self.ends.append(b)

    def __contains__(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        return i >= 0 and t <= self.ends[i]


def why_unseen(points, limits, coverage):
    """Why a source didn't see a pass. points: time-ordered [(t, lat, lon, height_m or None)], from
    the sources that did see it; coverage: when this source has data, a Coverage or [(start, end)];
    limits: from prepare(). Returns one of REASONS, the first that holds for all but MIN_VISIBLE_S
    of the pass."""
    if not isinstance(coverage, Coverage):
        coverage = Coverage(coverage)
    covered = [p[0] in coverage for p in points]
    if _span(points, covered) < MIN_VISIBLE_S:
        return NO_DATA
    inside = [c and in_area(limits, p[1], p[2]) for p, c in zip(points, covered)]
    if _span(points, inside) < MIN_VISIBLE_S:
        return OUTSIDE
    ceiling = limits["ceiling_m"]
    low = [i and (ceiling is None or p[3] is None or p[3] <= ceiling - CEILING_MARGIN_M) for p, i in zip(points, inside)]
    if _span(points, low) < MIN_VISIBLE_S:
        return ABOVE
    return UNEXPLAINED


def unseen_rows(members, tracks, limits, coverage):
    """Rows for the unseen table: each pass, and each source that has no flight in it, with why.
    members: link.members(); tracks: {(source, source_id): track (geometry.py)}; limits: {source:
    limits}; coverage: the coverage table's rows."""
    when = {}
    for c in coverage:
        when.setdefault(c["source"], []).append((parse_time(c["start_utc"]), parse_time(c["end_utc"])))
    when = {source: Coverage(spans) for source, spans in when.items()}
    empty = Coverage([])
    ready = {source: prepare(lim) for source, lim in limits.items()}
    rows = []
    for pass_id, keys in sorted(members.items()):
        seen = {k[0] for k in keys}
        points = sorted((p[:4] for k in keys for p in tracks.get(k, [])), key=lambda p: p[0])
        for source, lim in ready.items():
            if source not in seen:
                rows.append({"pass_id": pass_id, "source": source,
                             "reason": why_unseen(points, lim, when.get(source, empty))})
    return rows


def summary(rows):
    """build.json's unseen: how many (pass, source) pairs there are for each reason."""
    return {reason: sum(1 for u in rows if u["reason"] == reason) for reason in REASONS}

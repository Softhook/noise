"""Turn log records into positions, and group the positions into flights."""

from __future__ import annotations

import math
from typing import NamedTuple, Optional

from .common import number


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

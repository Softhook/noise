"""WebTrak's radar tracks and NMT6 events, from the files saved by tools/webtrak."""

from __future__ import annotations

import csv
import datetime as dt
import os
from dataclasses import dataclass

from .common import WEBTRAK_DIR, number, parse_time


@dataclass
class RadarPass:
    t: float  # Time of the track's closest point to NMT6
    callsign: str
    type: str
    distance_m: float
    altitude_m: float | None  # Above sea level


@dataclass
class Event:
    t: float  # Time of LAmax
    lmax_db: float


def days(begin, end):
    day = dt.datetime.fromtimestamp(begin, dt.timezone.utc).date()
    while day <= dt.datetime.fromtimestamp(end, dt.timezone.utc).date():
        yield day
        day += dt.timedelta(days=1)


def radar_passes(begin, end, radius_m, pad_s=0, webtrak_dir=WEBTRAK_DIR):
    """The closest point of each radar track within radius_m, if it falls from begin to end.

    Points are read for pad_s either side, so a track near the start or end has its closest
    point found from both sides.
    """
    closest = {}
    for day in days(begin - pad_s, end + pad_s):
        path = os.path.join(webtrak_dir, "aircraft", f"{day}.csv")
        if not os.path.exists(path):
            continue
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                t = parse_time(row["time_utc"])
                d = number(row["distance_m"])
                if d is None or d > radius_m or not begin - pad_s <= t <= end + pad_s:
                    continue
                best = closest.get(row["track"])
                if best is None or d < best.distance_m:
                    closest[row["track"]] = RadarPass(t, row["callsign"], row["type"], d, number(row["altitude_m"]))
    return sorted((p for p in closest.values() if begin <= p.t <= end), key=lambda p: p.t)


def events(begin, end, webtrak_dir=WEBTRAK_DIR):
    """NMT6's noise events with LAmax from begin to end, in file order."""
    path = os.path.join(webtrak_dir, "events.csv")
    if not os.path.exists(path):
        return []
    found = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t = parse_time(row["lmax_time_local"])
            if begin <= t <= end:
                found.append(Event(t, float(row["lmax_db"])))
    return found

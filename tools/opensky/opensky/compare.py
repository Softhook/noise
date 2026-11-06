"""Every aircraft near NMT6 from OpenSky's research database (Trino), compared with WebTrak.

  .venv/bin/python -m opensky compare --from 2026-11-05T08:01Z --to 2026-11-05T11:01Z

Passes within --radius of NMT6 are written to data/nmt6-trino-<from>.csv, then paired with
WebTrak's radar tracks by time and listed with NMT6's noise events.

Both sources are read for PAD_S either side of the period, so an aircraft passing NMT6 near the
start or end has positions on both sides of its closest approach. Only passes whose closest
approach falls inside the period are kept.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from . import aircraft, trino, webtrak
from .common import NMT6, OUT_DIR, iso, parse_time
from .geometry import box_around
from .passes import CSV_FIELDS, passes_near

PAD_S = 5 * 60  # Read this long either side of the period; aircraft cross the query box in 1-3 minutes
BOX_MARGIN_M = 2000  # Query beyond --radius, so a closest approach near the edge has points either side
QUERY_BOX_M = 3000 + BOX_MARGIN_M  # The box's half-side for any --radius up to 3000 m, so their queries are cached alike
MATCH_S = 90  # Closest approaches this close in time are taken to be the same flight
EVENT_S = 60  # An NMT6 event this close in time to a closest approach is listed with it


def pair(a, b, within_s):
    """Greedy one-to-one matching on .t, closest first. Returns [(a or None, b or None)] in time order."""
    options = sorted((abs(x.t - y.t), i, j) for i, x in enumerate(a) for j, y in enumerate(b)
                     if abs(x.t - y.t) <= within_s)
    used_a, used_b, pairs = set(), set(), []
    for _, i, j in options:
        if i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
            pairs.append((a[i], b[j]))
    pairs += [(a[i], None) for i in range(len(a)) if i not in used_a]
    pairs += [(None, b[j]) for j in range(len(b)) if j not in used_b]
    return sorted(pairs, key=lambda p: (p[0] or p[1]).t)


def nearest_event(events, t, within_s=EVENT_S):
    ev = min(events, key=lambda e: abs(e.t - t), default=None)
    return ev if ev and abs(ev.t - t) <= within_s else None


def write_csv(passes, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, CSV_FIELDS)
        w.writeheader()
        w.writerows(p.row() for p in passes)


def blank(value):
    return "" if value is None else value


def report(radar, passes, events, radius_m, out=None):
    """The paired table, then counts and the height differences."""
    def say(text=""):
        print(text, file=out or sys.stdout)

    say(f"\nWebTrak: {len(radar)} radar tracks within {radius_m:.0f} m, {len(events)} NMT6 events\n")
    say(f"{'closest (UTC)':20} {'WebTrak':10} {'type':5} {'dist':>5} {'alt':>5} | "
        f"{'OpenSky':9} {'type':5} {'dist':>5} {'geo':>5} {'baro':>5} {'dt':>4} {'gap':>4} {'rx':>3} | {'dalt':>5} | NMT6 LAmax")
    pairs = pair(radar, passes, MATCH_S)
    diffs = []
    for w, o in pairs:
        t = (w or o).t
        ev = nearest_event(events, t)
        alt = w.altitude_m if w and w.altitude_m is not None else float("nan")
        left = f"{w.callsign:10} {w.type:5} {w.distance_m:5.0f} {alt:5.0f}" if w else " " * 28
        offset = f"{o.t - w.t:+.0f}" if w and o else ""
        right = (f"{o.callsign:9} {o.type or '?':5} {o.distance_m:5} {blank(o.geo_msl_m):>5} {blank(o.baro_alt_m):>5} {offset:>4} "
                 f"{o.point_gap_s:>4} {o.receivers:>3}") if o else " " * 46
        dalt = ""
        if w and o and w.altitude_m is not None and o.geo_msl_m is not None:
            diffs.append(o.geo_msl_m - w.altitude_m)
            dalt = f"{diffs[-1]:+.0f}"
        say(f"{iso(t):20} {left} | {right} | {dalt:>5} | {f'{ev.lmax_db:.1f} dB' if ev else ''}")
    say(f"\nIn both: {sum(1 for w, o in pairs if w and o)}. WebTrak only: {sum(1 for w, o in pairs if not o)}. "
        f"OpenSky only: {sum(1 for w, o in pairs if not w)}.")
    if diffs:
        diffs.sort()
        say(f"OpenSky GPS height minus WebTrak altitude: median {diffs[len(diffs) // 2]:+.0f} m, "
            f"range {diffs[0]:+.0f} to {diffs[-1]:+.0f} m")
    say("alt = WebTrak altitude above sea level (m); geo = OpenSky GPS height minus geoid (m); baro = pressure "
        "altitude, uncorrected (m); dt = OpenSky minus WebTrak closest time (s); gap = seconds between OpenSky "
        "positions there; rx = most receivers hearing it; dalt = geo minus alt.")


def add_arguments(parser):
    parser.add_argument("--from", dest="begin", required=True, help="UTC, e.g. 2026-11-05T08:00Z")
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--radius", type=float, default=3000, help="metres from NMT6 (default 3000, as WebTrak)")
    parser.add_argument("--geoid", type=float, default=45.0, help="geoid height at NMT6 in metres (default 45)")
    parser.add_argument("--aircraft-db", help="a saved copy of tar1090-db (default: the newest in data/aircraft-db)")


def add_types(passes, db):
    """Fill in each pass's type and registration from the aircraft database."""
    for p in passes:
        found = db.get(p.icao24.lower())
        if found:
            p.type, p.registration = found.type, found.registration


def run(args, client=None, db=None):
    begin, end = parse_time(args.begin), parse_time(args.end)
    if db is None:
        _, db = aircraft.database(getattr(args, "aircraft_db", None))
    box = box_around(NMT6, max(QUERY_BOX_M, args.radius + BOX_MARGIN_M))
    states = trino.fetch_states(begin - PAD_S, end + PAD_S, box, client)
    passes = passes_near(states, begin, end, args.radius, args.geoid)
    add_types(passes, db)
    aircraft.report_unknown(db, [(p.icao24, p.callsign) for p in passes])

    out = os.path.join(OUT_DIR, f"nmt6-trino-{iso(begin)[:16].replace(':', '')}.csv")
    write_csv(passes, out)
    print(f"{len(passes)} aircraft passes within {args.radius:.0f} m of NMT6 -> {os.path.relpath(out)}")

    radar = webtrak.radar_passes(begin, end, args.radius, PAD_S)
    report(radar, passes, webtrak.events(begin, end), args.radius)


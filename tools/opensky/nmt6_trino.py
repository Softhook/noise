#!/usr/bin/env python3
"""Every aircraft near NMT6 from OpenSky's research database (Trino), compared with WebTrak.

  tools/opensky/.venv/bin/python tools/opensky/nmt6_trino.py --from 2026-11-05T08:01Z --to 2026-11-05T11:01Z

Unlike nmt6_flights.py, which uses the REST API's simplified tracks, this reads state_vectors_data4:
a state about once a second for every aircraft in a small box around NMT6, whatever its airport,
with full-resolution pressure (baroaltitude) and GPS (geoaltitude) heights. It needs research
access and no API credits.

Login: pyopensky reads your OpenSky username and password from its settings.conf (on a Mac,
~/Library/Application Support/pyopensky/settings.conf), or opens a browser to log in if they're
blank. Never put them in this repository.

Load on OpenSky's shared server is kept small, as its guidelines require: one query per hour
partition, always filtered on `hour`, one at a time, and pyopensky caches each result so a
rerun doesn't query again.

Heights: WebTrak's altitude_m is above mean sea level. geoaltitude is GPS height above the WGS84
ellipsoid, so subtract the geoid height (--geoid, about 45 m in London) to compare them.
baroaltitude is pressure altitude (1013.25 hPa) and needs a QNH correction, not done here.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

from nmt6_flights import (MATCH_S, NMT6, OUT_DIR, closest_approach, iso, pair, parse_time,
                          webtrak_events, webtrak_passes)

BOX_MARGIN_M = 2000  # Query beyond --radius, so a closest approach near the edge has points either side
PASS_GAP_S = 300  # An aircraft unseen for this long has left; a new pass starts when it returns
STALE_S = 15  # OpenSky's recommended limit on time - lastcontact


def hour_partitions(begin, end):
    return list(range(int(begin) // 3600 * 3600, int(end) + 1, 3600))


def query_hour(trino, hour, begin, end, box):
    lat0, lat1, lon0, lon1 = box
    sql = f"""
        SELECT time, icao24, callsign, lat, lon, baroaltitude, geoaltitude, velocity, heading,
               vertrate, onground, lastposupdate, lastcontact, cardinality(serials) AS receivers
        FROM state_vectors_data4
        WHERE hour = {hour}
          AND time BETWEEN {int(begin)} AND {int(end)}
          AND lat BETWEEN {lat0:.5f} AND {lat1:.5f}
          AND lon BETWEEN {lon0:.5f} AND {lon1:.5f}
          AND time - lastcontact <= {STALE_S}
        ORDER BY icao24, time
    """
    df = trino.query(sql)
    return [] if df is None else df.to_dict("records")


def number(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)


def interpolate(points, t, key):
    """Linear value of points[key] at time t, from the neighbouring points that have one."""
    have = [(p["t"], number(p[key])) for p in points if number(p[key]) is not None]
    for (t0, v0), (t1, v1) in zip(have, have[1:]):
        if t0 <= t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return min(have, key=lambda tv: abs(tv[0] - t))[1] if have else None


def passes_from_states(rows, begin, end, radius, geoid):
    """Closest approach to NMT6 for each pass of each aircraft."""
    by_aircraft = {}
    for r in rows:
        by_aircraft.setdefault(r["icao24"], []).append(r)
    passes = []
    for icao24, states in by_aircraft.items():
        # A state repeats its last position until a new one arrives, so keep each position once,
        # at the time it was received
        points, seen = [], set()
        for s in sorted(states, key=lambda s: s["time"]):
            pos_t = number(s["lastposupdate"]) or float(s["time"])
            if s["onground"] or number(s["lat"]) is None or pos_t in seen:
                continue
            seen.add(pos_t)
            points.append({**s, "t": pos_t})
        points.sort(key=lambda p: p["t"])
        groups, current = [], []
        for p in points:
            if current and p["t"] - current[-1]["t"] > PASS_GAP_S:
                groups.append(current)
                current = []
            current.append(p)
        if current:
            groups.append(current)
        for g in groups:
            if len(g) < 2:
                continue
            t, d, _ = closest_approach([(p["t"], float(p["lat"]), float(p["lon"]), None) for p in g])
            if d > radius or not begin <= t <= end:
                continue
            gaps = [b["t"] - a["t"] for a, b in zip(g, g[1:])]
            near = min(range(len(g)), key=lambda i: abs(g[i]["t"] - t))
            geo = interpolate(g, t, "geoaltitude")
            baro = interpolate(g, t, "baroaltitude")
            callsigns = [str(p["callsign"]).strip() for p in g if p.get("callsign")]
            passes.append({
                "closest_utc": iso(t), "t": t, "icao24": icao24,
                "callsign": max(set(callsigns), key=callsigns.count) if callsigns else "",
                "distance_m": round(d),
                "geo_msl_m": round(geo - geoid) if geo is not None else "",
                "baro_alt_m": round(baro) if baro is not None else "",
                "positions": len(g), "point_gap_s": round(max(gaps[max(0, near - 1):near + 1] or [0]), 1),
                "receivers": int(max(number(p["receivers"]) or 0 for p in g)),
            })
    return sorted(passes, key=lambda p: p["t"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="begin", required=True, help="UTC, e.g. 2026-11-05T08:00Z")
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--radius", type=float, default=3000, help="metres from NMT6 (default 3000, as WebTrak)")
    parser.add_argument("--geoid", type=float, default=45.0, help="geoid height at NMT6 in metres (default 45)")
    args = parser.parse_args()
    begin, end = parse_time(args.begin), parse_time(args.end)

    from pyopensky.trino import Trino  # Here, so --help works without the virtual environment

    margin = args.radius + BOX_MARGIN_M
    dlat = math.degrees(margin / 6371000)
    dlon = dlat / math.cos(math.radians(NMT6[0]))
    box = (NMT6[0] - dlat, NMT6[0] + dlat, NMT6[1] - dlon, NMT6[1] + dlon)
    trino = Trino()
    rows = []
    for hour in hour_partitions(begin, end):
        got = query_hour(trino, hour, begin, end, box)
        print(f"Trino: {iso(hour)}: {len(got)} state vectors", file=sys.stderr)
        rows += got
    passes = passes_from_states(rows, begin, end, args.radius, args.geoid)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"nmt6-trino-{iso(begin)[:16].replace(':', '')}.csv")
    fields = ["closest_utc", "callsign", "icao24", "distance_m", "geo_msl_m", "baro_alt_m", "positions",
              "point_gap_s", "receivers"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(passes)
    print(f"{len(passes)} aircraft passes within {args.radius:.0f} m of NMT6 -> {os.path.relpath(out)}")

    web = webtrak_passes(begin, end, args.radius)
    events = webtrak_events(begin, end)
    print(f"\nWebTrak: {len(web)} radar tracks within {args.radius:.0f} m, {len(events)} NMT6 events\n")
    print(f"{'closest (UTC)':20} {'WebTrak':10} {'type':5} {'dist':>5} {'alt':>5} | "
          f"{'OpenSky':9} {'dist':>5} {'geo':>5} {'baro':>5} {'dt':>4} {'gap':>4} {'rx':>3} | {'dalt':>5} | NMT6 LAmax")
    pairs = pair(web, passes, MATCH_S)
    diffs = []
    for w, o in pairs:
        t = (w or o)["t"]
        ev = min(events, key=lambda e: abs(e["t"] - t), default=None)
        ev_text = f"{float(ev['lmax_db']):.1f} dB" if ev and abs(ev["t"] - t) <= 60 else ""
        left = (f"{w['callsign']:10} {w['type']:5} {w['distance_m']:5.0f} {float(w['altitude_m'] or 'nan'):5.0f}"
                if w else " " * 28)
        offset = f"{o['t'] - w['t']:+.0f}" if w and o else ""
        right = (f"{o['callsign']:9} {o['distance_m']:5} {o['geo_msl_m']:>5} {o['baro_alt_m']:>5} {offset:>4} "
                 f"{o['point_gap_s']:>4} {o['receivers']:>3}") if o else " " * 40
        dalt = ""
        if w and o and w["altitude_m"] and o["geo_msl_m"] != "":
            diffs.append(o["geo_msl_m"] - float(w["altitude_m"]))
            dalt = f"{diffs[-1]:+.0f}"
        print(f"{iso(t):20} {left} | {right} | {dalt:>5} | {ev_text}")
    print(f"\nIn both: {sum(1 for w, o in pairs if w and o)}. WebTrak only: {sum(1 for w, o in pairs if not o)}. "
          f"OpenSky only: {sum(1 for w, o in pairs if not w)}.")
    if diffs:
        diffs.sort()
        print(f"OpenSky GPS height minus WebTrak altitude: median {diffs[len(diffs) // 2]:+.0f} m, "
              f"range {diffs[0]:+.0f} to {diffs[-1]:+.0f} m")
    print("alt = WebTrak altitude above sea level (m); geo = OpenSky GPS height minus geoid (m); baro = pressure "
          "altitude, uncorrected (m); dt = OpenSky minus WebTrak closest time (s); gap = seconds between OpenSky "
          "positions there; rx = most receivers hearing it; dalt = geo minus alt.")


if __name__ == "__main__":
    main()

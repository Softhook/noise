"""OpenSky positions near NMT6 as the ADS-B logger's hourly files, so `adsb analyse` and its viewer read them unchanged.

  .venv/bin/python -m opensky logs --from 2026-10-28T00:00Z --to 2026-10-29T00:00Z --out data/2026-10-28/adsb
  python3 -m adsb analyse --config ../opensky/nmt6-site.json --logs data/2026-10-28/adsb --out data/2026-10-28/results

It uses the same whole-hour queries as `compare`, so hours already fetched come from pyopensky's
cache. Each record has the logger's field names: heights in feet, as readsb gives them, with
`alt_geom` as GPS height above the WGS84 ellipsoid (OpenSky's geoaltitude), which `adsb analyse`
corrects with the config's geoid_height_m. OpenSky gives no ground speed, track or aircraft type
here, and `adsb analyse` doesn't need them: it works out headings from the positions.

SOURCE.txt says where the files came from, so they can't be mistaken for the logger's own record.
OpenSky's research terms limit redistribution: keep the files private and publish only summaries.
"""

from __future__ import annotations

import collections
import datetime as dt
import gzip
import json
import os

from . import aircraft, trino
from .common import NMT6, iso, number, parse_time
from .compare import QUERY_BOX_M
from .geometry import box_around
from .passes import positions

FEET_PER_M = 1 / 0.3048


def records(states, db=None):
    """Logger records, one per position, in time order, with r, t, dbFlags and desc from the aircraft database."""
    db = db or {}
    by_aircraft = collections.defaultdict(list)
    for s in states:
        by_aircraft[s["icao24"]].append(s)
    out = []
    for icao24, rows in by_aircraft.items():
        found = db.get(icao24.lower())
        details = {}
        if found:
            details = {key: value for key, value in (("r", found.registration), ("t", found.type),
                                                     ("dbFlags", found.db_flags), ("desc", found.description))
                       if value not in ("", None, 0)}  # readsb leaves out dbFlags 0, as missing fields
        for p in positions(rows):
            record = {"now": round(p["t"], 2), "hex": icao24.lower(), "lat": float(p["lat"]),
                      "lon": float(p["lon"]), "seen_pos": 0.0, "type": "opensky"}
            callsign = p.get("callsign")
            if isinstance(callsign, str) and callsign.strip():
                record["flight"] = callsign.strip()
            for key, column in (("alt_baro", "baroaltitude"), ("alt_geom", "geoaltitude")):
                metres = number(p.get(column))
                if metres is not None:
                    record[key] = round(metres * FEET_PER_M)
            receivers = number(p.get("receivers"))
            if receivers is not None:
                record["receivers"] = int(receivers)
            record.update(details)
            out.append(record)
    return sorted(out, key=lambda r: r["now"])


def hour_name(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H")


def write_logs(recs, out_dir, begin, end, db_name="none"):
    """The hourly files and SOURCE.txt. Returns the number of hourly files."""
    os.makedirs(out_dir, exist_ok=True)
    if any(name.endswith(".jsonl.gz") for name in os.listdir(out_dir)):
        raise SystemExit(f"{out_dir} already holds log files; choose an empty folder")
    hours = collections.defaultdict(list)
    for r in recs:
        hours[hour_name(r["now"])].append(r)
    for hour, rows in sorted(hours.items()):
        with gzip.open(os.path.join(out_dir, f"{hour}.jsonl.gz"), "wt") as f:
            f.writelines(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)
    made = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    codes = {r["hex"] for r in recs}
    typed = {r["hex"] for r in recs if r.get("t")}
    with open(os.path.join(out_dir, "SOURCE.txt"), "w") as f:
        f.write(
            "Source: OpenSky Network research database (Trino), state_vectors_data4\n"
            "NOT the logger's own record. Converted by `opensky logs`.\n"
            f"Converted: {made}\n"
            f"Period: {iso(begin)} to {iso(end)}\n"
            f"Kept: airborne positions within {QUERY_BOX_M / 1000:g} km either side of NMT6 (a box)\n"
            f"Positions: {len(recs):,} from {len(codes):,} aircraft, in {len(hours)} hourly files\n"
            f"Aircraft types: tar1090-db, {db_name}; {len(typed):,} of {len(codes):,} aircraft found\n"
            "Licence: OpenSky's research terms. Keep private; publish only summaries, citing OpenSky.\n"
        )
    return len(hours)


def add_arguments(parser):
    parser.add_argument("--from", dest="begin", required=True, help="UTC, e.g. 2026-10-28T00:00Z")
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--out", required=True, help="an empty folder for the hourly files")
    parser.add_argument("--aircraft-db", help="a saved copy of tar1090-db (default: the newest in data/aircraft-db)")


def run(args, client=None, db=None, db_path="given"):
    begin, end = parse_time(args.begin), parse_time(args.end)
    if db is None:
        db_path, db = aircraft.database(getattr(args, "aircraft_db", None))
    states = trino.fetch_states(begin, end, box_around(NMT6, QUERY_BOX_M), client)
    recs = records(states, db)
    callsigns = {}
    for r in recs:
        callsigns.setdefault(r["hex"], r.get("flight", ""))
    aircraft.report_unknown(db, callsigns.items())
    count = write_logs(recs, args.out, begin, end, os.path.basename(db_path))
    print(f"{len(recs):,} positions from {len({r['hex'] for r in recs}):,} aircraft "
          f"-> {count} hourly files in {os.path.relpath(args.out)}")

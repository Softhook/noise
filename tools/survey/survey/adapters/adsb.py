"""ADS-B-family sources: our logger, adsb.lol and OpenSky, all as `adsb analyse` results.

Each of them reaches the survey the same way: hourly log files (the logger's own, or converted by
`adsb traces` or `opensky logs`), then `adsb analyse --all-positions`. This adapter reads that
results folder (flights.csv, positions.csv, summary.txt), and the logs folder's SOURCE.txt if
the manifest gives `logs`. It never imports the adsb package.

Manifest entry:
    "opensky": {"adapter": "adsb", "results": "../opensky/data/2026-11-05/results",
                "logs": "../opensky/data/2026-11-05/adsb"}
"""

from __future__ import annotations

import csv
import os
import re

from ..common import iso, number, parse_time, registration

KNOTS_TO_MS = 0.514444
DIRECTIONS = {"rwy27_arrival": "A", "rwy09_departure": "D"}
PERIOD = re.compile(r"^Period: (\S+) to (\S+)")
SITE = re.compile(r"^Site: .*\(([-\d.]+), ([-\d.]+)\)$")
BOX = re.compile(r"within ([\d.]+) km either side of")
# adsb analyse's defaults: it drops positions above this pressure altitude, or further than this
# from its site. A manifest gives ceiling_ft or max_km if its config's "analysis" changed them.
ANALYSE_CEILING_FT = 10000
ANALYSE_MAX_KM = 15.0
FEET = 0.3048
COVERED = re.compile(r"^Time covered: (\S+) to (\S+)")
GAP = re.compile(r"^GAP over 30 minutes.*?: (\S+) to (\S+)$")


def _rows(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found; run adsb analyse first")
    with open(path, newline="") as f:
        yield from csv.DictReader(f)


def coverage(name, spec, start, end):
    """When the source has data: the converted logs' period if SOURCE.txt gives one (OpenSky's
    query period, which holds even when the sky was quiet), otherwise the analysis's time covered,
    less its gaps."""
    rows = []
    logs = spec.get("logs")
    if logs:
        source_txt = os.path.join(logs, "SOURCE.txt")
        if os.path.exists(source_txt):
            with open(source_txt) as f:
                for line in f:
                    m = PERIOD.match(line.strip())
                    if m:
                        a, b = max(start, parse_time(m.group(1))), min(end, parse_time(m.group(2)))
                        if a < b:
                            rows.append({"source": name, "start_utc": iso(a), "end_utc": iso(b), "note": "queried"})
            if rows:
                return rows
    covered, gaps = None, []
    summary = os.path.join(spec["results"], "summary.txt")
    if os.path.exists(summary):
        with open(summary) as f:
            for line in f:
                line = line.strip()
                if (m := COVERED.match(line)) and m.group(1) != "-":
                    covered = (parse_time(m.group(1)), parse_time(m.group(2)) + 60)
                elif m := GAP.match(line):
                    gaps.append((parse_time(m.group(1)), parse_time(m.group(2))))
    if not covered:
        return rows
    cursor = covered[0]
    for a, b in sorted(gaps) + [(covered[1], covered[1])]:
        lo, hi = max(start, cursor), min(end, a)
        if lo < hi:
            rows.append({"source": name, "start_utc": iso(lo), "end_utc": iso(hi), "note": "data"})
        cursor = max(cursor, b)
    return rows


def limits(spec):
    """What the source can see (explain.py's limits): adsb analyse's ceiling, and its radius around
    the site in summary.txt; and, if the logs' SOURCE.txt gives one, the box they were cut to
    (`opensky logs` keeps a box around NMT6, and its results are analysed with NMT6 as the site)."""
    site, areas = None, []
    summary = os.path.join(spec["results"], "summary.txt")
    if os.path.exists(summary):
        with open(summary) as f:
            for line in f:
                if m := SITE.match(line.strip()):
                    site = float(m.group(1)), float(m.group(2))
                    break
    if site:
        areas.append(("circle", *site, float(spec.get("max_km", ANALYSE_MAX_KM))))
        source_txt = os.path.join(spec.get("logs") or "", "SOURCE.txt")
        if spec.get("logs") and os.path.exists(source_txt):
            with open(source_txt) as f:
                for line in f:
                    if line.startswith("Kept:") and (m := BOX.search(line)):
                        areas.append(("box", *site, float(m.group(1))))
    return {"ceiling_m": float(spec.get("ceiling_ft", ANALYSE_CEILING_FT)) * FEET, "areas": areas, "any": False}


def read(name, spec, start, end, warnings):
    """(flights, positions, coverage) rows for the common tables, for flights overlapping start to end."""
    results = spec["results"]
    flights, by_id = [], {}
    for row in _rows(os.path.join(results, "flights.csv")):
        first, last = parse_time(row["first_seen_utc"]), parse_time(row["last_seen_utc"])
        if last < start or first > end:
            continue
        # Stable across reruns of adsb analyse, unlike its flight_id
        source_id = f"{row['hex']}-{iso(first)[:19].replace('-', '').replace(':', '')}"
        by_id[row["flight_id"]] = source_id
        flights.append({
            "source": name, "source_id": source_id, "first_utc": iso(first), "last_utc": iso(last),
            "registration": registration(row.get("registration")), "callsign": (row.get("callsign") or "").strip(),
            "callsign_kind": "icao" if row.get("callsign") else "", "type": row.get("type") or "",
            "squawk": "", "direction": DIRECTIONS.get(row.get("label"), ""), "origin": "", "destination": "",
            "hex": row["hex"], "_height_kind": row.get("height_source") or "",
        })
    positions, seen = [], set()
    for row in _rows(os.path.join(results, "positions.csv")):
        source_id = by_id.get(row["flight_id"])
        if source_id is None:
            continue
        t = parse_time(row["emission_time_utc"])
        if not start - 600 <= t <= end + 600:
            continue
        seen.add(row["flight_id"])
        speed = number(row.get("ground_speed_kt"))
        positions.append({
            "source": name, "source_id": source_id, "t": round(t, 2), "lat": float(row["lat"]),
            "lon": float(row["lon"]), "height_m": number(row.get("height_used_amsl_m")),
            "height_kind": "", "speed_ms": None if speed is None else round(speed * KNOTS_TO_MS, 1),
        })
    kinds = {f["source_id"]: f.pop("_height_kind") for f in flights}
    for p in positions:
        p["height_kind"] = kinds.get(p["source_id"], "")
    missing = len(by_id) - len(seen)
    if missing:
        warnings.append(f"{name}: {missing} of {len(by_id)} flights have no positions; "
                        f"run adsb analyse with --all-positions")
    return flights, positions, coverage(name, spec, start, end)

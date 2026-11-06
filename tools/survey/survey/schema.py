"""The common tables: their columns, and reading and writing them as CSV, safely for a reader.

Every row carries `source` and the source's own id (`source_id`), so any result can be traced
back. Times are UTC ISO strings, except `t` in positions and levels, which is Unix seconds: those
tables have a row for every second or so, and are read as numbers. Heights are metres above mean
sea level, with their kind. A true flag is "1", a false one empty.

positions and levels (PARTITIONED) are a folder of files, one per UTC day (positions/2026-11-05.csv),
so the survey app reads only the days it's asked for, however long the deployment. A flight's
positions all go in the file for the day of its first_utc, so its track is never split; a level
goes in the file for its own day.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile

TABLES = {
    # The places flights are measured from, from the manifest
    "receptors": ["id", "name", "label", "lat", "lon", "ground_elevation_m", "mic_height_m", "public"],
    # One row per flight per source
    "flights": ["source", "source_id", "first_utc", "last_utc", "registration", "callsign", "callsign_kind",
                "type", "squawk", "direction", "origin", "destination", "hex"],
    # Every position, t in Unix seconds. height_kind: geometric, qnh or radar, or empty without a height
    "positions": ["source", "source_id", "t", "lat", "lon", "height_m", "height_kind", "speed_ms"],
    # Noise events at a receptor. event_class: "aircraft", "other" or "unknown", as the source classed it
    "noise_events": ["source", "receptor", "start_utc", "lmax_utc", "end_utc", "lmax_db", "sel_db", "leq_db",
                     "event_class"],
    # Sound levels, one per second where the source has them, t in Unix seconds
    "levels": ["source", "receptor", "t", "level_db", "flag"],
    # When each source has data
    "coverage": ["source", "start_utc", "end_utc", "note"],
    # Each flight's closest approach to each receptor (worked out by the core). at_track_end: the
    # closest point is the track's first or last position, so the aircraft may have come closer
    # outside the source's data, and the approach isn't a true closest approach
    "approaches": ["source", "source_id", "receptor", "t", "ground_m", "height_m", "slant_m", "at_track_end"],
    # Flights from different sources that are the same aircraft movement
    "passes": ["pass_id", "source", "source_id", "evidence"],
    # Each pass, and each source with no flight in it, with why (explain.py): "no data" (no data
    # then), "outside its area", "above its ceiling", or "unexplained", when it should have seen it
    "unseen": ["pass_id", "source", "reason"],
}
# The tables an adapter may fill. The rest are worked out by the core (build.py).
SOURCE_TABLES = ("flights", "positions", "noise_events", "levels", "coverage")
# The tables kept as a file per UTC day
PARTITIONED = ("positions", "levels")


def write_table(folder, name, rows, filename=None):
    """Write one table's rows (dicts) as folder/<filename or name>.csv."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{filename or name}.csv")
    # A temporary file of its own, so two writers never share one
    fd, temp = tempfile.mkstemp(prefix=f".{filename or name}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, TABLES[name], extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: "" if value is None else value for key, value in row.items()})
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise
    return path


def table_days(folder, name):
    """The days a partitioned table has a file for, in order."""
    part = os.path.join(folder, name)
    if not os.path.isdir(part):
        return []
    return sorted(f[:-4] for f in os.listdir(part) if f.endswith(".csv") and not f.startswith("."))


def read_rows(folder, name, days=None):
    """A table's rows, one dict at a time. For a partitioned table, only the files for days (all of
    them if None), in day order."""
    if name in PARTITIONED:
        paths = [os.path.join(folder, name, f"{day}.csv") for day in (table_days(folder, name) if days is None else days)]
    else:
        paths = [os.path.join(folder, f"{name}.csv")]
    for path in paths:
        if os.path.exists(path):
            with open(path, newline="") as f:
                yield from csv.DictReader(f)


def read_table(folder, name, days=None):
    """A table's rows, as a list of dicts (see read_rows)."""
    return list(read_rows(folder, name, days))


def write_tables(folder, tables):
    """Write every table into a new folder, then put it in place of the old one, so a reader (the
    survey app, while `make build` runs) sees either the old tables or the new ones, never a mixture.
    tables: {name: rows}, except a PARTITIONED table, which is {day: rows}."""
    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".common.new.", dir=parent)
    try:
        for name, rows in tables.items():
            if name in PARTITIONED:
                os.makedirs(os.path.join(staging, name))
                for day, day_rows in sorted(rows.items()):
                    write_table(os.path.join(staging, name), name, day_rows, filename=day)
            else:
                write_table(staging, name, rows)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    old = None
    if os.path.exists(folder):
        old = tempfile.mkdtemp(prefix=".common.old.", dir=parent)
        os.rmdir(old)
        os.rename(folder, old)
    os.rename(staging, folder)
    if old:
        shutil.rmtree(old, ignore_errors=True)


def write_json(path, data):
    """Write a JSON file in one step, so a reader never sees half of it."""
    fd, temp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def read_json(path):
    """A JSON file, or None if it isn't there."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)

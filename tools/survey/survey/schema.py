"""The common tables: their columns, and reading and writing them as CSV, safely for a reader.

Every row carries `source` and the source's own id (`source_id`), so any result can be traced
back. Times are UTC ISO strings; heights are metres above mean sea level with their kind.
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
    # Every position. height_kind: geometric, qnh or radar
    "positions": ["source", "source_id", "t", "lat", "lon", "height_m", "height_kind", "speed_ms"],
    # Noise events at a receptor. event_class: "aircraft", "other" or "unknown", as the source classed it
    "noise_events": ["source", "receptor", "start_utc", "lmax_utc", "end_utc", "lmax_db", "sel_db", "leq_db",
                     "event_class"],
    # Sound levels, one per second where the source has them
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


def write_table(folder, name, rows):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.csv")
    # A temporary file of its own, so two writers never share one
    fd, temp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=folder)
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


def read_table(folder, name):
    path = os.path.join(folder, f"{name}.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_tables(folder, tables):
    """Write every table into a new folder, then put it in place of the old one, so a reader (the
    survey app, while `make build` runs) sees either the old tables or the new ones, never a mixture."""
    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".common.new.", dir=parent)
    try:
        for name, rows in tables.items():
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

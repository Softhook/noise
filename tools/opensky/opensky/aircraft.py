"""Aircraft type and registration for each icao24, from a dated copy of tar1090-db.

OpenSky's state vectors give no aircraft type, so it's looked up here in the same database readsb
uses on the garden Pi (https://github.com/wiedehopf/tar1090-db, csv branch), so both sources give the
same ICAO type codes, such as E190, BCS1 or A20N.

Copies are kept in data/raw/opensky/aircraft-db/ as aircraft-<date downloaded>.csv.gz, and the newest is used.
If there's none, one is downloaded. `opensky aircraft --update` downloads a newer one. To reproduce
a result, pass the copy it used (printed with every run) as --aircraft-db.

The file has one aircraft per line, separated by semicolons:
  icao24;registration;type;flags;description;year;owner;...
flags is a string of 0s and 1s: military, interesting, PIA, LADD. It's turned into readsb's dbFlags
number (1, 2, 4, 8), as in the logger's records.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import gzip
import os
import sys
import urllib.request
from dataclasses import dataclass

from .common import RAW_DIR

DB_DIR = os.path.join(RAW_DIR, "aircraft-db")
DB_URL = "https://raw.githubusercontent.com/wiedehopf/tar1090-db/csv/aircraft.csv.gz"
MIN_ROWS = 100000  # A download with fewer aircraft than this is taken to be broken


@dataclass(frozen=True)
class Aircraft:
    registration: str
    type: str  # ICAO type code
    db_flags: int
    description: str


def db_flags(text):
    """tar1090-db's flags string ("1000") as readsb's dbFlags number (military 1, interesting 2, PIA 4, LADD 8)."""
    return sum(1 << i for i, c in enumerate(text[:4]) if c == "1")


def load(path):
    """{icao24 in lower case: Aircraft}"""
    db = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.reader(f, delimiter=";"):
            if not row or not row[0]:
                continue
            row += [""] * (5 - len(row))
            db[row[0].strip().lower()] = Aircraft(row[1].strip(), row[2].strip(), db_flags(row[3]), row[4].strip())
    return db


def saved_copies(db_dir=None):
    return sorted(glob.glob(os.path.join(db_dir or DB_DIR, "aircraft-*.csv.gz")))


def download(db_dir=None, url=DB_URL, log=None):
    """Save today's copy of the database. Returns its path."""
    log = log or sys.stderr
    db_dir = db_dir or DB_DIR
    os.makedirs(db_dir, exist_ok=True)
    path = os.path.join(db_dir, f"aircraft-{dt.date.today().isoformat()}.csv.gz")
    partial = path + ".part"
    print(f"Aircraft database: downloading {url}", file=log)
    request = urllib.request.Request(url, headers={"User-Agent": "noise-opensky-tool"})
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
    count = len(load(partial))
    if count < MIN_ROWS:
        os.remove(partial)
        raise SystemExit(f"Aircraft database download from {url} has only {count} aircraft; not kept")
    os.replace(partial, path)
    print(f"Aircraft database: {count:,} aircraft -> {os.path.relpath(path)}", file=log)
    return path


def database(path=None, log=None):
    """(path, {icao24: Aircraft}): the given copy, or the newest saved one, downloading one if none is saved."""
    log = log or sys.stderr
    if path is None:
        copies = saved_copies()
        path = copies[-1] if copies else download(log=log)
    db = load(path)
    print(f"Aircraft database: {os.path.relpath(path)}, {len(db):,} aircraft", file=log)
    return path, db


def report_unknown(db, aircraft, log=None):
    """Warn about every (icao24, callsign) with no type in the database. Returns how many there were."""
    log = log or sys.stderr
    unknown = sorted({(icao24, callsign) for icao24, callsign in aircraft
                      if not (db.get(icao24.lower()) and db[icao24.lower()].type)})
    for icao24, callsign in unknown:
        print(f"WARNING: no aircraft type for {icao24} ({callsign or 'no callsign'})", file=log)
    return len(unknown)


def add_arguments(parser):
    parser.add_argument("--update", action="store_true", help="download today's copy of tar1090-db")


def run(args):
    if args.update:
        download()
    copies = saved_copies()
    if not copies:
        print("No saved copy. Run with --update, or run compare or logs, which download one.")
    for path in copies:
        print(os.path.relpath(path))

"""The common tables: their columns and types, and storing them as Parquet, queried with DuckDB.

Every row carries `source` and the source's own id (`source_id`), so any result can be traced
back. Heights are metres above mean sea level, with their kind.

Each column has a type (TEXT, REAL, FLAG or TIME), which is how it's stored, so the tables can
be queried as a database (connect(), or `noise sql`) without converting anything. In Python, the
core holds a row as a dict, and read_rows gives it back the same way:
    TEXT  a str, "" when missing (stored as NULL)
    REAL  a float, or None when missing
    FLAG  a bool
    TIME  a UTC ISO string to the millisecond (common.iso: 2026-11-05T08:12:31.250Z), "" when
          missing; stored as a UTC timestamp to the millisecond
`t` in positions and levels is REAL, Unix seconds: those tables have a row for every second or so,
and are compared as numbers.

A build's tables are a folder (common/) with a Parquet file per table. positions and levels
(PARTITIONED) are a folder of files instead, one per UTC day (positions/2026-11-05.parquet), so
the survey app reads only the days it's asked for, however long the deployment. A flight's
positions all go in the file for the day of its first_utc, so its track is never split; a level
goes in the file for its own day.

Parquet, rather than a DuckDB database file, because a build replaces the folder whole
(write_tables) while the app may be reading it: plain files need no lock between the two, and
any tool (DuckDB, pandas, R) reads them. DuckDB is the query engine over them (connect()).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import shutil
import tempfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .common import epoch_ms

TEXT, REAL, FLAG, TIME = "text", "real", "flag", "time"

TABLES = {
    # The places flights are measured from, from the manifest
    "receptors": {"id": TEXT, "name": TEXT, "label": TEXT, "lat": REAL, "lon": REAL, "ground_elevation_m": REAL,
                  "mic_height_m": REAL, "public": FLAG},
    # One row per flight per source
    "flights": {"source": TEXT, "source_id": TEXT, "first_utc": TIME, "last_utc": TIME, "registration": TEXT,
                "callsign": TEXT, "callsign_kind": TEXT, "type": TEXT, "squawk": TEXT, "direction": TEXT,
                "origin": TEXT, "destination": TEXT, "hex": TEXT},
    # Every position, t in Unix seconds. height_kind: geometric, qnh or radar, or empty without a height
    "positions": {"source": TEXT, "source_id": TEXT, "t": REAL, "lat": REAL, "lon": REAL, "height_m": REAL,
                  "height_kind": TEXT, "speed_ms": REAL},
    # Noise events at a receptor. event_class: "aircraft", "other" or "unknown", as the source classed it
    "noise_events": {"source": TEXT, "receptor": TEXT, "start_utc": TIME, "lmax_utc": TIME, "end_utc": TIME,
                     "lmax_db": REAL, "sel_db": REAL, "leq_db": REAL, "event_class": TEXT},
    # Sound levels, one per second where the source has them, t in Unix seconds. flag: the source's own
    "levels": {"source": TEXT, "receptor": TEXT, "t": REAL, "level_db": REAL, "flag": TEXT},
    # When each source has data
    "coverage": {"source": TEXT, "start_utc": TIME, "end_utc": TIME, "note": TEXT},
    # Each flight's closest approach to each receptor (worked out by the core). at_track_end: the
    # closest point is the track's first or last position, so the aircraft may have come closer
    # outside the source's data, and the approach isn't a true closest approach. path_angle_deg: the
    # flight path's angle there (geometry.path_angle), positive climbing, empty without enough heights
    "approaches": {"source": TEXT, "source_id": TEXT, "receptor": TEXT, "t": TIME, "ground_m": REAL,
                   "height_m": REAL, "slant_m": REAL, "at_track_end": FLAG, "path_angle_deg": REAL},
    # Flights from different sources that are the same aircraft movement
    "passes": {"pass_id": TEXT, "source": TEXT, "source_id": TEXT, "evidence": TEXT},
    # Each pass, and each source with no flight in it, with why (explain.py): "no data" (no data
    # then), "outside its area", "above its ceiling", or "unexplained", when it should have seen it
    "unseen": {"pass_id": TEXT, "source": TEXT, "reason": TEXT},
    # Each pass's registration and type (resolve.py). type_source: register:<code> or manual (the
    # fleet table), or the source whose type was taken. disagree: sources that give another type,
    # or a transponder address other than the register's. fleet: why the fleet table didn't settle
    # the type (no registration, not in the table, not found, no type), or empty if it did
    "identity": {"pass_id": TEXT, "registration": TEXT, "type": TEXT, "model": TEXT, "type_source": TEXT,
                 "fleet": TEXT, "disagree": TEXT},
    # Each noise event, and the pass that made it (match.py), keyed on source, receptor and
    # lmax_utc. track_source, track_id: the flight whose track predicted the sound; emitted_utc and
    # arrival_utc: when the sound left its closest point and reached the receptor; offset_s: LAmax
    # minus arrival, as measured; window_centre_s: the day's clock offset the window was centred
    # on, empty if not established; slant_m, ground_m, height_m, path_angle_deg: its closest
    # point. others: pass ids, ";"-joined, that may have added to the level. flags: match.FLAGS, ";"-joined
    "event_matches": {"source": TEXT, "receptor": TEXT, "lmax_utc": TIME, "lmax_db": REAL, "event_class": TEXT,
                      "pass_id": TEXT, "track_source": TEXT, "track_id": TEXT, "emitted_utc": TIME,
                      "arrival_utc": TIME, "offset_s": REAL, "window_centre_s": REAL, "slant_m": REAL,
                      "ground_m": REAL, "height_m": REAL, "path_angle_deg": REAL, "others": TEXT, "flags": TEXT},
    # Every pass whose predicted arrival fitted an event in time (match.py), matched or not.
    # below_match_db: how much quieter than the matched pass it was predicted, empty if none was
    "event_candidates": {"source": TEXT, "receptor": TEXT, "lmax_utc": TIME, "pass_id": TEXT, "matched": FLAG,
                         "offset_s": REAL, "slant_m": REAL, "track_source": TEXT, "below_match_db": REAL},
}
# The tables' format, kept in build.json. Raise it whenever a table's columns, their types, what
# they mean, or how they're stored change: the survey app then asks for a rebuild instead of
# reading a build made before, so neither it nor the page needs to cope with older tables. Builds
# are derived, so a rebuild loses nothing. 2: Parquet, typed, instead of CSV.
FORMAT = 2
# The tables an adapter may fill. The rest are worked out by the core (build.py).
SOURCE_TABLES = ("flights", "positions", "noise_events", "levels", "coverage")
# The tables kept as a file per UTC day
PARTITIONED = ("positions", "levels")

EXTENSION = ".parquet"
BATCH_ROWS = 100_000  # Rows converted and written at a time (a Parquet row group), so a table is never all in memory
ARROW_TYPES = {TEXT: pa.string(), REAL: pa.float64(), FLAG: pa.bool_(), TIME: pa.timestamp("ms", tz="UTC")}
SQL_TYPES = {TEXT: "VARCHAR", REAL: "DOUBLE", FLAG: "BOOLEAN", TIME: "TIMESTAMPTZ"}


def _text(value):
    return None if value is None or value == "" else str(value)


def _real(value):
    if value is None or value == "":
        return None
    f = float(value)  # A value that isn't a number is a mistake in the code that made it: raise
    return None if math.isnan(f) else f


def _flag(value):
    if not isinstance(value, bool):
        raise TypeError(f"a flag must be True or False, not {value!r}")
    return value


def _time(value):
    if value is None or value == "":
        return None
    return epoch_ms(value)


TO_STORE = {TEXT: _text, REAL: _real, FLAG: _flag, TIME: _time}
# What reading a table raises when its files go part-way through, as when a build replaces them
READ_ERRORS = (OSError, duckdb.IOException)


def arrow_schema(name):
    return pa.schema([(column, ARROW_TYPES[kind]) for column, kind in TABLES[name].items()])


def table_path(folder, name, day=None):
    """Where a table is kept in a build's tables folder: <name>.parquet, or for a PARTITIONED
    table, <name>/<day>.parquet."""
    if name in PARTITIONED:
        if day is None:
            raise ValueError(f"{name} is kept by day: give the day")
        return os.path.join(folder, name, f"{day}{EXTENSION}")
    return os.path.join(folder, f"{name}{EXTENSION}")


def write_table(folder, name, rows, filename=None):
    """Write one table's rows (dicts, any iterable) as folder/<filename or name>.parquet, converting
    each column to its type. Every row has every column, and only those: a missing or extra key
    raises, as a value of the wrong kind does, since either is a mistake in the code that made it."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{filename or name}{EXTENSION}")
    columns, schema = TABLES[name], arrow_schema(name)
    # A temporary file of its own, so two writers never share one
    fd, temp = tempfile.mkstemp(prefix=f".{filename or name}.", suffix=".tmp", dir=folder)
    os.close(fd)
    try:
        with pq.ParquetWriter(temp, schema, compression="zstd") as writer:
            batch = []
            for row in rows:
                if row.keys() != columns.keys():
                    missing, extra = columns.keys() - row.keys(), row.keys() - columns.keys()
                    raise ValueError(f"{name}: " + "; ".join(
                        f"{what}: {', '.join(sorted(keys))}"
                        for what, keys in (("missing", missing), ("not a column", extra)) if keys))
                batch.append(row)
                if len(batch) == BATCH_ROWS:
                    writer.write_table(_arrow(name, batch, schema))
                    batch = []
            if batch:
                writer.write_table(_arrow(name, batch, schema))
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise
    return path


def _arrow(name, rows, schema):
    arrays = []
    for column, kind in TABLES[name].items():
        convert = TO_STORE[kind]
        try:
            values = [convert(row[column]) for row in rows]
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name}.{column}: {error}") from None
        arrays.append(pa.array(values, ARROW_TYPES[kind]))
    return pa.Table.from_arrays(arrays, schema=schema)


def table_days(folder, name):
    """The days a partitioned table has a file for, in order."""
    part = os.path.join(folder, name)
    if not os.path.isdir(part):
        return []
    return sorted(f[:-len(EXTENSION)] for f in os.listdir(part) if f.endswith(EXTENSION) and not f.startswith("."))


def table_files(folder, name, days=None):
    """The files that hold a table (for a partitioned one, those for days, all if None), that exist."""
    if name in PARTITIONED:
        paths = [table_path(folder, name, day) for day in (table_days(folder, name) if days is None else days)]
    else:
        paths = [table_path(folder, name)]
    return [p for p in paths if os.path.exists(p)]


def _literal(text):
    return "'" + text.replace("'", "''") + "'"


def connect(folder, days=None):
    """A DuckDB connection, in memory, with a view per table over a build's tables folder: query it
    with SQL (db.execute("SELECT ... FROM flights").fetchall()), then close it. A partitioned
    table's view covers the files for days (all if None). A table with no file is an empty view of
    the right columns, so a query never fails for want of rows. Times are UTC (TIMESTAMPTZ), and
    the connection's time zone is UTC too."""
    db = duckdb.connect()
    try:
        db.execute("SET TimeZone = 'UTC'")
        for name, columns in TABLES.items():
            files = table_files(folder, name, days)
            if files:
                body = f"SELECT * FROM read_parquet([{', '.join(_literal(f) for f in files)}])"
            else:
                body = ("SELECT " + ", ".join(f"CAST(NULL AS {SQL_TYPES[kind]}) AS {column}"
                                              for column, kind in columns.items()) + " WHERE false")
            db.execute(f"CREATE VIEW {name} AS {body}")
    except BaseException:
        db.close()
        raise
    return db


# How read_rows selects each type, to give it back as the core holds it
_FROM_STORE = {TEXT: "coalesce({0}, '')", REAL: "{0}", FLAG: "coalesce({0}, false)",
               TIME: "coalesce(strftime({0}, '%Y-%m-%dT%H:%M:%S.%gZ'), '')"}


def _rows(db, name):
    columns = TABLES[name]
    select = ", ".join(_FROM_STORE[kind].format(column) for column, kind in columns.items())
    cursor = db.execute(f"SELECT {select} FROM {name}")
    while batch := cursor.fetchmany(10_000):
        for values in batch:
            yield dict(zip(columns, values))


def read_rows(folder, name, days=None):
    """A table's rows, one dict at a time, as the core holds them (see the top of this module). For
    a partitioned table, only the files for days (all of them if None), in day order, and in the
    order each file was written."""
    with contextlib.closing(connect(folder, days)) as db:
        yield from _rows(db, name)


def read_table(folder, name, days=None):
    """A table's rows, as a list of dicts (see read_rows)."""
    return list(read_rows(folder, name, days))


def read_tables(folder, names, days=None):
    """{name: read_table's rows} for several tables, through one connection."""
    with contextlib.closing(connect(folder, days)) as db:
        return {name: list(_rows(db, name)) for name in names}


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


class NotBuilt(Exception):
    """A deployment with no tables to read: never built, or built in another FORMAT, by an older
    version, so it needs a rebuild."""


def build_info(out_dir):
    """A deployment's build.json, from out_dir (a manifest's out_dir), or None if it isn't built or
    was built in another FORMAT. Everything that reads a build's tables checks this first."""
    info = read_json(os.path.join(out_dir, "build.json"))
    return info if info and info.get("format") == FORMAT else None


def built_tables(m):
    """The tables folder of manifest m's build (manifest.load's), or NotBuilt saying why there's none."""
    if build_info(m["out_dir"]) is None:
        if os.path.exists(os.path.join(m["out_dir"], "build.json")):
            raise NotBuilt(f"{m['deployment']} was built by an older version of the survey; rebuild it "
                           f"(make build DEPLOYMENT={m['deployment']})")
        raise NotBuilt(f"{m['deployment']} isn't built yet (make build DEPLOYMENT={m['deployment']})")
    return os.path.join(m["out_dir"], "common")


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

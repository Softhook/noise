"""State vectors from OpenSky's research database, kept within its guidelines.

https://openskynetwork.github.io/opensky-api/trino.html. OpenSky suspends accounts that keep
ignoring them, so every query here:
- filters on the `hour` partition (Trino rejects queries without one), and covers one hour;
- also filters on time and a small latitude/longitude box, so it scans little;
- runs one at a time (each user may have 2 running and 2 queued);
- drops stale states, which OpenSky keeps for up to 300 s after it last heard an aircraft.

pyopensky caches each result by its exact SQL, so a rerun doesn't query again. Only hours that
ended more than SETTLED_S ago are cached: OpenSky may still be processing more recent ones, and a
cached partial result would never be refreshed.

Login: pyopensky reads your OpenSky username and password from its settings.conf (on a Mac,
~/Library/Application Support/pyopensky/settings.conf), or opens a browser to log in if they're
blank. Never put them in this repository.
"""

from __future__ import annotations

import sys
import time

from .common import iso

HOUR_S = 3600
STALE_S = 15  # OpenSky's recommended limit on time - lastcontact
SETTLED_S = 24 * 3600  # Only cache an hour's result once it ended this long ago


def hour_partitions(begin, end):
    """The `hour` partitions holding states from begin to end: Unix seconds at each UTC hour's start."""
    return list(range(int(begin) // HOUR_S * HOUR_S, int(end) + 1, HOUR_S))


def states_sql(hour, begin, end, box):
    """One hour partition's airborne and grounded states in box, from begin to end."""
    lat0, lat1, lon0, lon1 = box
    # Keep this text unchanged where possible: pyopensky's cache is keyed on it
    return f"""
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


def settled(hour, now=None):
    return hour + HOUR_S < (time.time() if now is None else now) - SETTLED_S


def fetch_states(begin, end, box, client=None, log=sys.stderr):
    """Every state in box from begin to end, as dicts, one query per hour partition in turn.

    client: something with pyopensky's Trino.query(sql, cached=...) -> DataFrame or None;
    by default a pyopensky Trino client.
    """
    if client is None:
        from pyopensky.trino import Trino  # Here, so the rest of the tool runs without pyopensky
        client = Trino()
    rows = []
    for hour in hour_partitions(begin, end):
        sql = states_sql(hour, max(begin, hour), min(end, hour + HOUR_S - 1), box)
        df = client.query(sql, cached=settled(hour))
        got = [] if df is None else df.to_dict("records")
        print(f"Trino: {iso(hour)}: {len(got)} state vectors", file=log)
        rows += got
    return rows

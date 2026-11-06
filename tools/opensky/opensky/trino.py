"""State vectors from OpenSky's research database, kept within its guidelines and fetched as little as possible.

https://openskynetwork.github.io/opensky-api/trino.html. OpenSky suspends accounts that keep
ignoring them, so every query here:
- filters on the `hour` partition (Trino rejects queries without one), and covers one hour;
- also filters on a small latitude/longitude box, so it returns little;
- runs one at a time (each user may have 2 running and 2 queued);
- drops stale states, which OpenSky keeps for up to 300 s after it last heard an aircraft.

To fetch as little as possible:
- Each query asks for a whole hour in a fixed box, whatever the period and radius, so its text, and
  pyopensky's cache key, is the same for every run that needs that hour. The rows are cut to the
  period here.
- OpenSky drops ground states (the box takes in London City's runway: about half the rows), and
  sends each position once. A state vector repeats the last position until a new one arrives, so
  states with the same lastposupdate are grouped into one, keeping the first state's heights.
- Only the columns the tool uses are fetched, unsorted.
- Hours that haven't started yet aren't queried.

pyopensky caches each result by its exact SQL, so a rerun doesn't query again. Only hours that
ended more than SETTLED_S ago are cached: OpenSky may still be processing more recent ones, and a
cached partial result would never be refreshed.

Login: pyopensky reads your OpenSky username and password from its settings.conf (on a Mac,
~/Library/Application Support/pyopensky/settings.conf), or opens a browser to log in if they're
blank. Never put them in this repository.
"""

from __future__ import annotations

import math
import sys
import time

from .common import iso

HOUR_S = 3600
STALE_S = 15  # OpenSky's recommended limit on time - lastcontact
SETTLED_S = 24 * 3600  # Only cache an hour's result once it ended this long ago


def hour_partitions(begin, end):
    """The `hour` partitions holding states from begin up to end: Unix seconds at each UTC hour's start."""
    return list(range(int(begin) // HOUR_S * HOUR_S, max(math.ceil(end), int(begin) + 1), HOUR_S))


def states_sql(hour, box):
    """One hour partition's airborne positions in box, each once."""
    lat0, lat1, lon0, lon1 = box
    # Keep this text unchanged where possible: pyopensky's cache is keyed on it
    return f"""
        SELECT icao24, lastposupdate, min(time) AS time, max(callsign) AS callsign,
               min_by(lat, time) AS lat, min_by(lon, time) AS lon,
               min_by(baroaltitude, time) AS baroaltitude, min_by(geoaltitude, time) AS geoaltitude,
               max(cardinality(serials)) AS receivers
        FROM state_vectors_data4
        WHERE hour = {hour}
          AND lat BETWEEN {lat0:.5f} AND {lat1:.5f}
          AND lon BETWEEN {lon0:.5f} AND {lon1:.5f}
          AND NOT onground
          AND time - lastcontact <= {STALE_S}
        GROUP BY icao24, lastposupdate
    """


def settled(hour, now=None):
    return hour + HOUR_S < (time.time() if now is None else now) - SETTLED_S


def fetch_states(begin, end, box, client=None, log=None):
    """Every airborne position in box from begin to end, as dicts, one query per hour partition in turn.

    client: something with pyopensky's Trino.query(sql, cached=...) -> DataFrame or None;
    by default a pyopensky Trino client.
    """
    log = log or sys.stderr
    now = time.time()
    hours = [hour for hour in hour_partitions(begin, end) if hour <= now]
    if hours and client is None:
        from pyopensky.trino import Trino  # Here, so the rest of the tool runs without pyopensky
        client = Trino()
    rows = []
    for hour in hours:
        df = client.query(states_sql(hour, box), cached=settled(hour, now))
        got = [] if df is None else df.to_dict("records")
        print(f"Trino: {iso(hour)}: {len(got)} positions", file=log)
        rows += [r for r in got if begin <= r["time"] <= end]
    return rows

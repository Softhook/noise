"""Download METARs for a period from the Iowa Environmental Mesonet archive, for adsb analyse --weather.

  python3 -m adsb metars --from 2026-10-28 --to 2026-10-29 --out eglc_metars.csv [--station EGLC]

It asks for a day either side of the period, because the analysis uses the latest report before each
position, so the last report before the period starts matters too. The request is the one tested in
docs/analysis.md: routine and special reports (METAR and SPECI), times in UTC.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import re
import sys
import urllib.parse
import urllib.request

from .common import parse_utc

ARCHIVE = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
DAY_S = 86400


def metar_url(station, start, end):
    """The archive's URL for station's reports from a day before start to a day after end (Unix times)."""
    first = dt.datetime.fromtimestamp(start - DAY_S, dt.timezone.utc)
    last = dt.datetime.fromtimestamp(end + DAY_S, dt.timezone.utc)
    query = [
        ("station", station), ("data", "metar"),
        ("year1", first.year), ("month1", first.month), ("day1", first.day),
        ("year2", last.year), ("month2", last.month), ("day2", last.day),
        ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "no"), ("missing", "empty"),
        ("trace", "empty"), ("direct", "no"), ("report_type", 3), ("report_type", 4),
    ]
    return f"{ARCHIVE}?{urllib.parse.urlencode(query)}"


def check(text):
    """How many reports with a QNH the archive's CSV holds. Raises ValueError if it isn't that CSV."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or not {"valid", "metar"} <= set(rows[0]):
        raise ValueError("not the archive's METAR CSV: " + text[:200].strip())
    return sum(1 for row in rows if re.search(r"\bQ\d{4}\b", row.get("metar") or ""))


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start", required=True, help="first UTC date or time, such as 2026-10-28")
    parser.add_argument("--to", dest="end", required=True, help="UTC date or time to stop before")
    parser.add_argument("--out", required=True, help="CSV file to write")
    parser.add_argument("--station", default="EGLC", help="ICAO code (default EGLC, London City)")
    args = parser.parse_args(argv)
    url = metar_url(args.station, parse_utc(args.start), parse_utc(args.end))
    request = urllib.request.Request(url, headers={"User-Agent": "noise-adsb-tool"})
    with urllib.request.urlopen(request, timeout=120) as response:
        text = response.read().decode("utf-8", "replace")
    try:
        count = check(text)
    except ValueError as error:
        print(f"{args.station}: {error}", file=sys.stderr)
        return 1
    if not count:
        print(f"{args.station}: no reports with a QNH for that period", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(text)
    print(f"{args.station}: {count} reports with a QNH -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

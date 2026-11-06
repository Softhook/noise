#!/usr/bin/env python3
"""Turn readsb track files into the logger's hourly files, so adsb analyse can read them unchanged.

  python3 -m adsb traces --config site.json --out OUT_DIR --source NAME INPUT [INPUT ...]

INPUT is a folder of readsb's track files (a --write-globe-history folder, or one day of it), or
an archive of one: a .tar file, or the parts of a split one (.tar.aa, .tar.ab, ...), which are read
in order without unpacking. It's for adsb.lol's public daily archives, which combine many receivers:
an independent source for checking our coverage and clock (see docs/traces.md).

Only positions within max_km of the site are kept. The inputs are only ever read. The output is
written in UTC hours, like the logger's, with SOURCE.txt saying where it came from, so it can't be
mistaken for our own log. readsb thins its track files (a point at least every 30 s, more often
when the track or height changes), so they are coarser than the logger's stream.

The track format is readsb's README-json.md, "trace jsons".
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import tarfile
import tempfile

from .geometry import distance_km

TRACE_NAME = re.compile(r"trace_full_(~?[0-9a-fA-F]{6})\.json$")
SPLIT_PART = re.compile(r"^(.*\.tar)\.[a-z]{2}$")
# Each point: [seconds after timestamp, lat, lon, altitude, gs, track, flags, vertical rate,
#              details or null, source type, geometric altitude, geometric rate, ias, roll]
FLAG_STALE, FLAG_NEW_LEG, FLAG_RATE_GEOM, FLAG_ALT_GEOM = 1, 2, 4, 8
# Carried forward from the last point that had details, because they describe the aircraft or
# flight rather than this one position. Quality fields such as nic are not carried.
STICKY = ("flight", "squawk", "category")


def point_records(trace):
    """Yield one log record per point of one aircraft's track, in the logger's field names."""
    code = trace.get("icao")
    base = trace.get("timestamp")
    if not isinstance(code, str) or not isinstance(base, (int, float)):
        return
    aircraft = {key: trace[key] for key in ("r", "t", "desc", "dbFlags") if trace.get(key) is not None}
    sticky = {}
    for point in trace.get("trace") or []:
        if not isinstance(point, list) or len(point) < 8:
            continue
        offset, lat, lon, altitude, gs, track, flags, rate = point[:8]
        if not all(isinstance(v, (int, float)) for v in (offset, lat, lon)):
            continue
        flags = flags if isinstance(flags, int) else 0
        details = point[8] if len(point) > 8 and isinstance(point[8], dict) else None
        record = {}
        if details:
            record.update(details)
            sticky.update({key: details[key] for key in STICKY if key in details})
        else:
            record.update(sticky)
        record.update(aircraft)
        record.update({"now": round(base + offset, 2), "hex": code.lower(), "lat": lat, "lon": lon,
                       "seen_pos": 0.0, "trace_flags": flags})
        if altitude == "ground":
            record["alt_baro"] = "ground"
        elif isinstance(altitude, (int, float)):
            record["alt_geom" if flags & FLAG_ALT_GEOM else "alt_baro"] = altitude
        if len(point) > 10 and isinstance(point[10], (int, float)):
            record["alt_geom"] = point[10]
        if isinstance(rate, (int, float)):
            record["geom_rate" if flags & FLAG_RATE_GEOM else "baro_rate"] = rate
        if len(point) > 9 and isinstance(point[9], str):
            record["type"] = point[9]
        for key, value in (("gs", gs), ("track", track)):
            if isinstance(value, (int, float)):
                record[key] = value
        yield record


def load_trace(data):
    """A track file's JSON. readsb gzips them even though they're named .json."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data)


class Parts(io.RawIOBase):
    """Read the parts of a split archive one after another, as one stream."""

    def __init__(self, paths):
        self.paths = list(paths)
        self.current = None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.current is None:
                if not self.paths:
                    return 0
                self.current = open(self.paths.pop(0), "rb")
            count = self.current.readinto(buffer)
            if count:
                return count
            self.current.close()
            self.current = None

    def close(self):
        if self.current:
            self.current.close()
        super().close()


def group_inputs(inputs):
    """Folders, whole archives, and split archives with their parts in order."""
    folders, archives, split = [], [], {}
    for path in inputs:
        match = SPLIT_PART.match(os.path.basename(path))
        if os.path.isdir(path):
            folders.append(path)
        elif match:
            split.setdefault(os.path.join(os.path.dirname(path), match.group(1)), []).append(path)
        else:
            archives.append([path])
    archives.extend(sorted(parts) for _, parts in sorted(split.items()))
    return folders, archives


def traces_in(inputs, report):
    """Yield (name, raw bytes) for every track file in the inputs."""
    folders, archives = group_inputs(inputs)
    for folder in folders:
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            dirs[:] = [d for d in dirs if d != "internal_state"]
            for name in sorted(files):
                if TRACE_NAME.search(name):
                    with open(os.path.join(root, name), "rb") as f:
                        yield name, f.read()
    for parts in archives:
        stream = io.BufferedReader(Parts(parts), buffer_size=1 << 20)
        try:
            with tarfile.open(fileobj=stream, mode="r|*") as archive:
                for member in archive:
                    if member.isfile() and TRACE_NAME.search(member.name):
                        yield member.name, archive.extractfile(member).read()
        except (tarfile.TarError, EOFError, OSError) as error:
            report["damaged"].append(f"{os.path.basename(parts[0])}: {error}")
        finally:
            stream.close()


def hour_name(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H")


def convert(inputs, out_dir, site_lat, site_lon, max_km, source, progress=None):
    """Write the hourly files and SOURCE.txt. Returns the report."""
    report = {"traces": 0, "unreadable": 0, "aircraft_kept": 0, "points": 0, "kept": 0, "damaged": [],
              "hours": 0}
    os.makedirs(out_dir, exist_ok=True)
    existing = [n for n in os.listdir(out_dir) if n.endswith(".jsonl.gz")]
    if existing:
        raise SystemExit(f"{out_dir} already holds log files; choose an empty folder")
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".work-") as work:
        hours = {}
        for name, data in traces_in(inputs, report):
            report["traces"] += 1
            if progress and report["traces"] % 20000 == 0:
                progress(f"{report['traces']:,} track files read, {report['aircraft_kept']:,} aircraft kept")
            try:
                trace = load_trace(data)
            except (ValueError, OSError, EOFError):
                report["unreadable"] += 1
                continue
            kept_any = False
            for record in point_records(trace):
                report["points"] += 1
                if distance_km(site_lat, site_lon, record["lat"], record["lon"]) > max_km:
                    continue
                hour = hour_name(record["now"])
                if hour not in hours:
                    hours[hour] = open(os.path.join(work, hour), "a")
                hours[hour].write(json.dumps(record, separators=(",", ":")) + "\n")
                report["kept"] += 1
                kept_any = True
            report["aircraft_kept"] += kept_any
        for f in hours.values():
            f.close()
        # Each hour sorted by time, as the logger writes them
        for hour in sorted(hours):
            with open(os.path.join(work, hour)) as f:
                lines = sorted(f, key=lambda line: json.loads(line)["now"])
            with gzip.open(os.path.join(out_dir, f"{hour}.jsonl.gz"), "wt") as f:
                f.writelines(lines)
        report["hours"] = len(hours)
    with open(os.path.join(out_dir, "SOURCE.txt"), "w") as f:
        f.write(source_note(inputs, source, max_km, report))
    return report


def source_note(inputs, source, max_km, report):
    made = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"Source: {source}",
        "NOT the logger's own record. Converted from readsb track files by `adsb traces`.",
        f"Converted: {made}",
        "Inputs: " + ", ".join(os.path.basename(os.path.normpath(p)) for p in inputs),
        f"Kept: positions within {max_km:g} km of the site",
        f"Track files: {report['traces']:,} read, {report['unreadable']:,} unreadable, "
        f"{report['aircraft_kept']:,} with positions kept",
        f"Positions: {report['points']:,} read, {report['kept']:,} kept, in {report['hours']} hourly files",
    ]
    lines += [f"Damaged: {d}" for d in report["damaged"]]
    return "\n".join(lines) + "\n"


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", metavar="INPUT", help="folder, .tar, or the parts of a split .tar")
    parser.add_argument("--config", required=True, help="site.json, for the site's location")
    parser.add_argument("--out", required=True, help="an empty folder for the hourly files")
    parser.add_argument("--source", required=True,
                        help="where the files came from, written to SOURCE.txt, e.g. 'adsb.lol prod 2026-11-05'")
    parser.add_argument("--max-km", type=float, help="default: the logger's max_km from the config, or 30")
    args = parser.parse_args(argv)
    with open(args.config) as f:
        config = json.load(f)
    site = config["site"]
    max_km = args.max_km or float((config.get("logger") or {}).get("max_km", 30))
    for path in args.inputs:
        if not os.path.exists(path):
            parser.error(f"no such file or folder: {path}")
    report = convert(args.inputs, args.out, float(site["lat"]), float(site["lon"]), max_km, args.source,
                     progress=lambda text: print(text, file=sys.stderr, flush=True))
    with open(os.path.join(args.out, "SOURCE.txt")) as f:
        print(f.read(), end="")
    return 1 if report["damaged"] or not report["kept"] else 0


if __name__ == "__main__":
    sys.exit(main())

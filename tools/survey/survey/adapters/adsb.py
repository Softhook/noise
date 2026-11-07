"""ADS-B-family sources: our logger, adsb.lol and OpenSky, all as `adsb analyse` results.

Each of them reaches the survey the same way: hourly log files (the logger's own, or converted by
`adsb traces` or `opensky logs`), then `adsb analyse --all-positions`. The build runs that
analysis itself (prepare(), below), for the deployment's window, into its derived folder, and only
when what it reads has changed: the window's log files, the site config, the weather, the adsb
code or the Python version, compared by content. This adapter then reads
the results folder (flights.csv, positions.csv, summary.txt), and the logs folder's SOURCE.txt.
It runs adsb as a separate program and never imports it.

Manifest entries (data paths relative to the data folder, `site` relative to the manifest):
    "opensky": {"adapter": "adsb", "logs": "raw/opensky/2026-11-05",
                "site": "../../opensky/nmt6-site.json", "weather": "raw/metars/eglc-2026-11-05.csv"}
    "adsb": {"adapter": "adsb", "logs": "raw/adsb/garden", "site": "../../adsb/site.json",
             "weather": "raw/metars/eglc-2026-11-20.csv"}

`weather` is optional. A source can give `results` instead of `site`, for results analysed by
hand; then nothing is run. For our logger, `logs` is a copy of its log_dir, whose health log says
when it was listening.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from .. import paths
from ..common import iso, number, parse_time, registration, stamp

PATHS = ("results", "logs", "weather")
MANIFEST_PATHS = ("site",)
INPUTS_FILE = ".inputs.sha256"  # In a results folder: the fingerprint of what it was analysed from

KNOTS_TO_MS = 0.514444
HEIGHT_KINDS = ("geometric", "qnh")  # adsb analyse's height_source, as the positions table keeps it
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
# The logger writes a health record every 5 minutes. Two records further apart than this mean it
# wasn't running in between (adsb.health.logger_was_listening uses the same limit).
HEALTH_SPACING_S = 900


# What adsb analyse reads from a logs folder: SOURCE.txt, hourly log files (in any subfolder) and
# the health log's daily files. Nothing else there (SHA256SUMS, notes) changes an analysis.
LOG_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2})(?:\.\d+)?\.jsonl\.gz$")
HEALTH_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
# The window's analysis reads positions from this long either side of it, so a flight crossing its
# edge is whole. A log file is taken if its hour is within FILE_MARGIN_S of that (adsb.logs reads
# lines up to 2 hours outside their file's hour, so this is more than it needs), a health file if
# its day is within a day of it.
ANALYSIS_PAD_S = 3600
FILE_MARGIN_S = 3 * 3600


def _utc(text, fmt):
    return dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc).timestamp()


def window_files(logs, start, end):
    """The files of a logs folder that adsb analyse reads for start to end: {relative path: path}."""
    picked = {}
    for folder, _, names in os.walk(logs):
        for name in names:
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, logs)
            log, health = LOG_FILE.match(name), HEALTH_FILE.match(name)
            if rel == "SOURCE.txt":
                picked[rel] = path
            elif log:
                hour = _utc(log.group(1), "%Y-%m-%dT%H")
                if start - FILE_MARGIN_S <= hour + 3600 and hour - FILE_MARGIN_S < end:
                    picked[rel] = path
            elif health and os.path.basename(folder) == "health":
                day = _utc(health.group(1), "%Y-%m-%d")
                if start - 86400 <= day + 86400 and day - 86400 < end:
                    picked[rel] = path
    return dict(sorted(picked.items()))


class Hashes:
    """Content hashes of files, kept beside the analysis (out_dir + ".hashes.json") by path, size
    and modification time, so a file is only read again when it may have changed."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path) as f:
                self.old = json.load(f)
        except (OSError, ValueError):
            self.old = {}
        self.new = {}

    def __call__(self, path):
        st = os.stat(path)
        key = [st.st_size, st.st_mtime_ns]
        got = self.old.get(path)
        if not got or got[:2] != key:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            got = key + [h.hexdigest()]
        self.new[path] = got
        return got[2]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path + ".tmp", "w") as f:
            json.dump(self.new, f)
        os.replace(self.path + ".tmp", self.path)


def fingerprint(files, site, weather, window, hashes):
    """What an analysis depends on, by content, never by where it is: the window, the files it
    reads (by their path in the logs folder), the site config, the weather, the adsb code and the
    Python version. The same data copied to another folder or computer gives the same fingerprint."""
    tool = paths.ADSB_TOOL
    code = sorted(os.path.join(d, f) for d, _, names in os.walk(os.path.join(tool, "adsb"))
                  for f in names if f.endswith((".py", ".html")))
    parts = {
        "window": window,
        "python": list(sys.version_info[:2]),
        "logs": [[rel, hashes(path)] for rel, path in files.items()],
        "site": hashes(site),
        "weather": hashes(weather) if weather else None,
        "code": [[os.path.relpath(path, tool), hashes(path)] for path in code],
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def prepare(name, spec, context, out_dir, log, warnings):
    """Run `adsb analyse` on the source's logs for the deployment's window, into out_dir, unless
    it's already been run on the same inputs; return the spec with `results` set to it, or None to
    leave the source out. A spec that gives `results` is returned as it is.

    analyse is given a folder of links to just the window's files (window_files), so a logs
    folder that grows over the survey, such as the garden's, never makes it read or redo more."""
    if spec.get("results"):
        return spec
    logs, site, weather = spec.get("logs"), spec.get("site"), spec.get("weather")
    if not logs or not site:
        raise ValueError(f"source {name}: give logs and site (to analyse), or results")
    for label, path in (("site", site), ("logs", logs)):
        if not os.path.exists(path):
            warnings.append(f"source {name}: its {label} {path} isn't there, so it's left out")
            return None
    if weather and not os.path.exists(weather):
        warnings.append(f"source {name}: its weather {weather} isn't there, so heights aren't corrected for it")
        weather = None
    start, end = context.start - ANALYSIS_PAD_S, context.end + ANALYSIS_PAD_S
    # In whole seconds: adsb analyse doesn't read fractions
    window = [dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") for t in (start, end)]
    files = window_files(logs, start, end)
    hashes = Hashes(out_dir + ".hashes.json")
    stamp_now = fingerprint(files, site, weather, window, hashes)
    hashes.save()
    try:
        with open(os.path.join(out_dir, INPUTS_FILE)) as f:
            if f.read().strip() == stamp_now:
                return {**spec, "results": out_dir}
    except OSError:
        pass
    print(f"{name}: analysing {len(files)} files of {os.path.relpath(logs)} (adsb analyse)", file=log)
    temp, view = out_dir + ".tmp", out_dir + ".logs"
    for path in (temp, view):
        shutil.rmtree(path, ignore_errors=True)
    for rel, path in files.items():
        link = os.path.join(view, rel)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(os.path.abspath(path), link)
    os.makedirs(view, exist_ok=True)
    command = ["analyse", "--config", site, "--logs", view, "--out", temp, "--all-positions",
               "--from", window[0], "--to", window[1]] + (["--weather", weather] if weather else [])
    try:  # The editable install (make setup) puts tools/adsb's package on the path
        done = subprocess.run([sys.executable, "-m", "adsb", *command],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    finally:
        shutil.rmtree(view, ignore_errors=True)
    if done.returncode:
        shutil.rmtree(temp, ignore_errors=True)
        raise RuntimeError(f"source {name}: adsb analyse failed:\n{done.stdout[-3000:]}")
    with open(os.path.join(temp, INPUTS_FILE), "w") as f:
        f.write(stamp_now + "\n")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(os.path.dirname(out_dir), exist_ok=True)
    os.rename(temp, out_dir)
    return {**spec, "results": out_dir}


def _rows(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found; the analysis has no {os.path.basename(path)}")
    with open(path, newline="") as f:
        yield from csv.DictReader(f)


def _health(logs):
    """The logger's health records (logs/health/*.jsonl), in time order."""
    entries = []
    for path in sorted(glob.glob(os.path.join(logs, "health", "*.jsonl"))):
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry["time"] = float(entry["time"])
                except (ValueError, KeyError, TypeError):
                    continue
                entries.append(entry)
    return sorted(entries, key=lambda e: e["time"])


def _listening(a, b):
    """True if two neighbouring health records show the logger running, connected, receiving,
    keeping what it received and with its clock synchronised, all the way from a to b."""
    if b["time"] - a["time"] > HEALTH_SPACING_S or a.get("event") == "stop" or b.get("event") in ("start", "disconnected"):
        return False
    if a.get("connected") is False or b.get("connected") is False:
        return False
    if any((e.get("clock") or {}).get("synchronised") is False for e in (a, b)):
        return False
    if b.get("dropped_disk_full") or b.get("dropped_write_error"):
        return False
    # The counts are since the previous record. An event record a few seconds after another may
    # have none yet, but a 5-minute one with no lines at all means nothing was coming in.
    return bool(b.get("lines")) or b["time"] - a["time"] <= 60


def health_coverage(name, logs, start, end):
    """When the logger was listening, from its health log, as coverage rows; None if it has no health log.

    This is finer than summary.txt's gaps, which only lists those over 30 minutes: a 10-minute
    outage would otherwise count as data, and every pass in it would look like a miss."""
    entries = _health(logs)
    if not entries:
        return None
    rows, run = [], None
    for a, b in zip(entries, entries[1:]):
        if _listening(a, b):
            if run and a["time"] <= run[1]:
                run[1] = b["time"]
            else:
                if run:
                    rows.append(run)
                run = [a["time"], b["time"]]
    if run:
        rows.append(run)
    out = []
    for a, b in rows:
        a, b = max(start, a), min(end, b)
        if a < b:
            out.append({"source": name, "start_utc": iso(a), "end_utc": iso(b), "note": "health log"})
    return out


def coverage(name, spec, start, end):
    """When the source has data: the converted logs' period if SOURCE.txt gives one (OpenSky's
    query period, which holds even when the sky was quiet); otherwise when the logger's health log
    shows it listening; otherwise the analysis's time covered, less its gaps over 30 minutes."""
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
        listening = health_coverage(name, logs, start, end)
        if listening is not None:
            return listening
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


def limits(spec, context):
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


def read(name, spec, context, warnings):
    """Flights overlapping the window, with their whole tracks, and the source's coverage.
    Positions come as a generator, read from positions.csv as the build takes them."""
    start, end = context.start, context.end
    results = spec["results"]
    flights, by_id, kinds = [], {}, {}
    for row in _rows(os.path.join(results, "flights.csv")):
        first, last = parse_time(row["first_seen_utc"]), parse_time(row["last_seen_utc"])
        if last < start or first > end:
            continue
        source_id = f"{row['hex']}-{stamp(first)}"  # Stable across reruns of adsb analyse, unlike its flight_id
        by_id[row["flight_id"]] = source_id
        kind = row.get("height_source") or ""
        kinds[source_id] = kind if kind in HEIGHT_KINDS else ""  # adsb analyse's "none": no height
        callsign = (row.get("callsign") or "").strip()
        flights.append({
            "source": name, "source_id": source_id, "first_utc": iso(first), "last_utc": iso(last),
            "registration": registration(row.get("registration")), "callsign": callsign,
            "callsign_kind": "icao" if callsign else "", "type": row.get("type") or "",
            "squawk": "", "direction": DIRECTIONS.get(row.get("label"), ""), "origin": "", "destination": "",
            "hex": row["hex"],
        })
    return {"flights": flights, "positions": _positions(name, results, by_id, kinds, warnings),
            "coverage": coverage(name, spec, start, end)}


def _positions(name, results, by_id, kinds, warnings):
    """The positions of the flights in by_id, as rows; then a warning if any flight had none."""
    seen = set()
    for row in _rows(os.path.join(results, "positions.csv")):
        source_id = by_id.get(row["flight_id"])
        if source_id is None:
            continue
        # A flight's whole track is kept, even the part outside the window, so that its closest
        # approach isn't cut short (and flagged at_track_end) where the window happens to end
        seen.add(row["flight_id"])
        speed = number(row.get("ground_speed_kt"))
        yield {
            "source": name, "source_id": source_id, "t": round(parse_time(row["emission_time_utc"]), 2),
            "lat": float(row["lat"]), "lon": float(row["lon"]), "height_m": number(row.get("height_used_amsl_m")),
            "height_kind": kinds[source_id], "speed_ms": None if speed is None else round(speed * KNOTS_TO_MS, 1),
        }
    missing = len(by_id) - len(seen)
    if missing:
        warnings.append(f"{name}: {missing} of {len(by_id)} flights have no positions; "
                        f"run adsb analyse with --all-positions")

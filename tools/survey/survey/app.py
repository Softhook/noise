"""What the survey app's page asks for: the deployments, a day of one, and a rebuild. No HTTP here (server.py).

App's methods return what's sent back as JSON, or raise BadRequest. A new request for the page is
a method on App and a route in server.py.

A build (build.py) replaces a deployment's tables folder whole, and then build.json. A Deployment
reads the tables again only when that has happened, and never while it's happening. It keeps the
small tables in memory, and reads positions and levels a day at a time, as the page asks for them.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import threading
import time

from . import build, link, manifest, schema
from .common import number, parse_time

TRACK_SPACING_S = 2.0  # Positions closer together than this are thinned for drawing
DAY_S = 86400
READ_ATTEMPTS = 5  # Tries at reading a build's tables while another build is replacing them
DAYS_KEPT = 4  # Days whose tracks and levels are kept in memory, the most recently asked for
# Every table but the daily ones (schema.PARTITIONED), which are read a day at a time
SMALL_TABLES = [name for name in schema.TABLES if name not in schema.PARTITIONED]


class BadRequest(Exception):
    """A request the app can't answer as asked. The page is told why."""


class Deployment:
    """One deployment: its manifest, and its built tables, kept until a build changes them."""

    def __init__(self, path, locks=None):
        self.manifest_path = path
        self.m = manifest.load(path)
        self.stamp = None
        self.tables = None
        self.days = {}  # Day -> read_day(), for the last few days asked for
        # lock: held while the tables are read and indexed, so two requests don't both read them.
        # building: held while the page's Rebuild runs, so a second press is refused. The two are
        # separate, so a day being read never makes a Rebuild look like it's already running, and
        # a request during a rebuild gets the old tables (a build swaps the new ones in whole).
        # The App keeps one pair per deployment name, so they outlive a re-read of the manifest.
        self.lock, self.building = locks or (threading.Lock(), threading.Lock())

    @property
    def folder(self):
        return os.path.join(self.m["out_dir"], "common")

    @property
    def build_json(self):
        return os.path.join(self.m["out_dir"], "build.json")

    def build_info(self):
        return schema.read_json(self.build_json)

    def _identity(self):
        """What changes when a build finishes: build.json's time, and the tables' folder, which a
        build replaces as a whole (schema.write_tables)."""
        try:
            return os.path.getmtime(self.build_json), os.stat(self.folder).st_ino
        except FileNotFoundError:
            return None

    def load(self, day=None):
        """The small tables, indexed (index()), read again only if a build has finished since; and
        with a day, (tables, that day's tracks and levels (read_day())). A day's are kept for the
        last DAYS_KEPT days asked for."""
        with self.lock:
            for _ in range(READ_ATTEMPTS):
                before = self._identity()
                if before is None:
                    if not os.path.exists(self.build_json):
                        raise BadRequest(f"{self.m['deployment']} isn't built yet")
                    time.sleep(0.1)  # A build outside the app is putting its tables in place
                    continue
                fresh = before != self.stamp
                tables = index({name: schema.read_table(self.folder, name) for name in SMALL_TABLES}) if fresh else self.tables
                kept = {} if fresh else self.days
                got = None
                if day is not None:
                    got = kept.pop(day, None) or read_day(self.folder, day)
                if self._identity() == before:  # No build finished while they were read
                    self.tables, self.stamp, self.days = tables, before, kept
                    if day is None:
                        return tables
                    kept[day] = got  # The most recent last
                    while len(kept) > DAYS_KEPT:
                        kept.pop(next(iter(kept)))
                    return tables, got
            raise BadRequest(f"{self.m['deployment']} is being rebuilt; try again in a moment")

    def coverage(self):
        """Only the coverage table: enough to list the days, without reading every position."""
        return schema.read_table(self.folder, "coverage")


def index(t):
    """The small tables, with what a day's request needs worked out once: times as numbers, and
    approaches and pass membership by flight."""
    for f in t["flights"]:
        f["_first"], f["_last"] = parse_time(f["first_utc"]), parse_time(f["last_utc"])
    for e in t["noise_events"]:
        e["_lmax"] = parse_time(e["lmax_utc"])
    for c in t["coverage"]:
        c["_start"], c["_end"] = parse_time(c["start_utc"]), parse_time(c["end_utc"])
    approaches = {}
    for a in t["approaches"]:
        approaches.setdefault((a["source"], a["source_id"]), {})[a["receptor"]] = {
            "t": a["t"], "ground_m": number(a["ground_m"]), "height_m": number(a["height_m"]),
            "slant_m": number(a["slant_m"]), "at_track_end": a["at_track_end"] == "1",
            # Missing from a build made before the column was added, until it's rebuilt
            "path_angle_deg": number(a.get("path_angle_deg"))}
    return {**t, "approach_index": approaches,
            "pass_index": {(p["source"], p["source_id"]): p for p in t["passes"]}}


def read_day(folder, day):
    """One day's tracks and levels, from the daily files (schema.PARTITIONED): {"tracks": {(source,
    source_id): [(t, lat, lon, height)]}, "height_kinds": {(source, source_id): kind}, "levels":
    [(t, receptor, dB)]}. Tracks come from the day before too: a flight's positions are filed by
    the day it started, so one that crossed midnight is in the earlier day's file."""
    before = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
    tracks, kinds = {}, {}
    for p in schema.read_rows(folder, "positions", [before, day]):
        key = (p["source"], p["source_id"])
        tracks.setdefault(key, []).append((float(p["t"]), float(p["lat"]), float(p["lon"]), number(p["height_m"])))
        kinds.setdefault(key, p["height_kind"])
    for pts in tracks.values():
        pts.sort()
    levels = sorted((float(lv["t"]), lv["receptor"], float(lv["level_db"]))
                    for lv in schema.read_rows(folder, "levels", [day]))
    return {"tracks": tracks, "height_kinds": kinds, "levels": levels}


def days(start, end):
    """Each UTC day from start to end, as YYYY-MM-DD."""
    day = dt.datetime.fromtimestamp(start, dt.timezone.utc).date()
    last = dt.datetime.fromtimestamp(end - 1, dt.timezone.utc).date()
    while day <= last:
        yield day.isoformat()
        day += dt.timedelta(days=1)


def day_bounds(day):
    """(start, end) of a YYYY-MM-DD day, in Unix seconds; BadRequest for anything else."""
    try:
        start = parse_time(f"{day}T00:00:00Z")
    except ValueError:
        raise BadRequest(f"bad day {day!r}") from None
    return start, start + DAY_S


def minutes_covered(coverage, lo, hi):
    """{source: minutes of data between lo and hi}, from coverage rows. A source's rows may overlap
    (two periods in SOURCE.txt, say), so they're merged first and no minute counts twice."""
    spans = {}
    for c in coverage:
        a, b = max(lo, parse_time(c["start_utc"])), min(hi, parse_time(c["end_utc"]))
        if a < b:
            spans.setdefault(c["source"], []).append((a, b))
    minutes = {}
    for source, runs in spans.items():
        total, end = 0.0, None
        for a, b in sorted(runs):
            if end is not None and a < end:
                a = end
            if a < b:
                total += b - a
            end = b if end is None else max(end, b)
        minutes[source] = round(total / 60)
    return minutes


def thinned(points):
    """A track for drawing: [t, lat, lon, height] at most one per TRACK_SPACING_S, to about a metre."""
    out, last = [], None
    for t, lat, lon, height in points:
        if last is not None and t - last < TRACK_SPACING_S:
            continue
        last = t
        out.append([round(t, 1), round(lat, 5), round(lon, 5), None if height is None else round(height, 1)])
    return out


def receptor_view(r):
    """A receptors table row, as the page uses it."""
    return {"id": r["id"], "name": r["name"], "label": r["label"], "lat": float(r["lat"]),
            "lon": float(r["lon"]), "public": r["public"] in ("1", "True")}  # "True" from builds before 2026-11-06


class App:
    def __init__(self, deployments_dir=None):
        self.dir = deployments_dir or manifest.DEPLOYMENTS_DIR
        self.cache = {}
        self.locks = {}  # Deployment name -> its lock, kept when its manifest is read again
        self.lock = threading.Lock()

    def deployment(self, name):
        """A deployment, read again whenever its manifest file changes."""
        for path in manifest.all_manifests(self.dir):
            if os.path.splitext(os.path.basename(path))[0] == name:
                stamp = os.path.getmtime(path)
                with self.lock:
                    cached = self.cache.get(name)
                    if not cached or cached[0] != (path, stamp):
                        locks = self.locks.setdefault(name, (threading.Lock(), threading.Lock()))
                        self.cache[name] = ((path, stamp), Deployment(path, locks))
                    return self.cache[name][1]
        raise BadRequest(f"no deployment {name!r}")

    def _listing(self, name, path):
        d = self.deployment(name)
        info = d.build_info()
        coverage = d.coverage() if info else []
        return {
            "deployment": name,
            "description": d.m["description"],
            "manifest": os.path.relpath(path, manifest.TOOLS_DIR),
            "built": info is not None,
            "built_utc": info and info["built_utc"],
            "sources": link.ranked(d.m["sources"]),
            "receptors": [{"id": r["id"], "name": r["name"], "label": r["label"]} for r in d.m["receptors"].values()],
            "days": [{"day": day, "minutes": minutes_covered(coverage, *day_bounds(day))}
                     for day in days(d.m["start"], d.m["end"])] if info else [],
            "warnings": (info or {}).get("warnings", d.m["warnings"]),
        }

    def deployments(self):
        """Every deployment, with its days and how much data each source has on each."""
        found = []
        for path in manifest.all_manifests(self.dir):
            name = os.path.splitext(os.path.basename(path))[0]
            try:
                found.append(self._listing(name, path))
            except (manifest.ManifestError, ValueError, OSError) as error:
                found.append({"deployment": name, "error": str(error)})
        return found

    def rebuild(self, body):
        """Build a deployment again, unless it's being built already, here or by `make build`."""
        d = self.deployment(str(body.get("deployment", "")))
        if not d.building.acquire(blocking=False):
            raise BadRequest(f"{d.m['deployment']} is already being rebuilt")
        try:
            d.m = manifest.load(d.manifest_path)
            return build.build(d.m, log=io.StringIO(), wait=False)
        except build.Busy as error:
            raise BadRequest(str(error)) from None
        finally:
            d.building.release()

    def day(self, query):
        """Everything the page draws for one day of a deployment."""
        d = self.deployment(query.get("deployment", ""))
        day = query.get("day", "")
        lo, hi = day_bounds(day)
        if day not in days(d.m["start"], d.m["end"]):
            raise BadRequest(f"{day} isn't in {d.m['deployment']}'s window")
        t, today = d.load(day)

        flights = []
        for f in t["flights"]:
            if f["_last"] < lo or f["_first"] >= hi:
                continue
            key = (f["source"], f["source_id"])
            member = t["pass_index"].get(key, {})
            flights.append({**{k: v for k, v in f.items() if not k.startswith("_")},
                            "pass_id": member.get("pass_id", ""), "evidence": member.get("evidence", ""),
                            "height_kind": today["height_kinds"].get(key, ""),
                            "approaches": t["approach_index"].get(key, {})})
        day_passes = {f["pass_id"] for f in flights}
        unseen = {}
        for u in t["unseen"]:
            if u["pass_id"] in day_passes:
                unseen.setdefault(u["pass_id"], {})[u["source"]] = u["reason"]
        identity = {i["pass_id"]: {k: v for k, v in i.items() if k != "pass_id"}
                    for i in t["identity"] if i["pass_id"] in day_passes}
        levels = [lv for lv in today["levels"] if lo <= lv[0] < hi]
        return {
            "deployment": d.m["deployment"],
            "day": day,
            "start": lo,
            "sources": link.ranked(d.m["sources"]),  # The order the page lists them in
            "receptors": [receptor_view(r) for r in t["receptors"]],
            "coverage": [{k: v for k, v in c.items() if not k.startswith("_")}
                         for c in t["coverage"] if c["_end"] > lo and c["_start"] < hi],
            "flights": flights,
            "unseen": unseen,
            "identity": identity,  # Pass id -> its resolved registration and type (resolve.py)
            "tracks": {f"{f['source']}|{f['source_id']}": thinned(today["tracks"].get((f["source"], f["source_id"]), []))
                       for f in flights},
            "events": [{k: v for k, v in e.items() if not k.startswith("_")}
                       for e in t["noise_events"] if lo <= e["_lmax"] < hi],
            "levels": [[round(lt - lo, 1), receptor, db] for lt, receptor, db in levels],
        }

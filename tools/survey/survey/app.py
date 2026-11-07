"""What the survey app's page asks for: the deployments, a day of one, and a rebuild. No HTTP here (server.py).

App's methods return what's sent back as JSON, or raise BadRequest. A new request for the page is
a method on App and a route in server.py.

A build (build.py) replaces a deployment's tables folder whole, and then build.json. A Deployment
reads the tables again only when that has happened, and never while it's happening. It keeps the
small tables in memory, and reads positions and levels a day at a time, as the page asks for them.
A build of another format than schema.FORMAT (made by an older version) counts as not built: the
page asks for a rebuild rather than reading it.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import time

from . import build, manifest, paths, schema
from .common import number, parse_time, ranked

TRACK_SPACING_S = 2.0  # Positions closer together than this are thinned for drawing
DAY_S = 86400
READ_ATTEMPTS = 5  # Tries at reading a build's tables while another build is replacing them
DAYS_KEPT = 4  # Days whose tracks and levels are kept in memory, the most recently asked for
# Every table but the daily ones (schema.PARTITIONED), which are read a day at a time
SMALL_TABLES = [name for name in schema.TABLES if name not in schema.PARTITIONED]
# What the page is given of each event's match, beside the event itself
MATCH_FIELDS = ("pass_id", "track_source", "arrival_utc", "offset_s", "slant_m", "others", "flags")


class BadRequest(Exception):
    """A request the app can't answer as asked. The page is told why."""


class BuildJob:
    """A rebuild started from the page: its progress, as the build prints it, and how it ended.

    It's a file-like log for build.build, so its lines (such as "opensky: analysing ...") can be
    shown while it runs. Only the last LOG_LINES are kept."""

    LOG_LINES = 200

    def __init__(self, deployment):
        self.deployment = deployment
        self.started = time.time()
        self.finished = None
        self.lines = []
        self.partial = ""
        self.error = None
        self.summary = None
        self._lock = threading.Lock()

    def write(self, text):
        with self._lock:
            self.partial += text
            *done, self.partial = self.partial.split("\n")
            self.lines = (self.lines + [line for line in done if line])[-self.LOG_LINES:]
        return len(text)

    def flush(self):
        pass

    def status(self):
        with self._lock:
            return {"deployment": self.deployment, "running": self.finished is None, "started": self.started,
                    "finished": self.finished, "log": list(self.lines), "error": self.error,
                    "passes": (self.summary or {}).get("passes")}


class Deployment:
    """One deployment: its manifest, read again whenever the file changes, and its built tables,
    kept until a build changes them. The App keeps one per deployment for as long as it runs."""

    def __init__(self, path):
        self.manifest_path = path
        self._manifest = (None, None)  # (the file's modification time, manifest.load's)
        self.stamp = None
        self.tables = None
        self.days = {}  # Day -> read_day(), for the last few days asked for
        # lock: held while the tables are read and indexed, so two requests don't both read them.
        # building: held while the page's Rebuild runs, so a second press is refused. The two are
        # separate, so a day being read never makes a Rebuild look like it's already running, and
        # a request during a rebuild gets the old tables (a build swaps the new ones in whole).
        self.lock, self.building = threading.Lock(), threading.Lock()

    @property
    def m(self):
        """The manifest (manifest.load's), read again if its file has changed. ManifestError if it's bad."""
        stamp = os.path.getmtime(self.manifest_path)
        if self._manifest[0] != stamp:
            self._manifest = (stamp, manifest.load(self.manifest_path))
        return self._manifest[1]

    @property
    def folder(self):
        return os.path.join(self.m["out_dir"], "common")

    @property
    def build_json(self):
        return os.path.join(self.m["out_dir"], "build.json")

    def build_info(self):
        """build.json, or None if it isn't built or was built in another format (schema.FORMAT)."""
        info = schema.read_json(self.build_json)
        return info if info and info.get("format") == schema.FORMAT else None

    def outdated(self):
        """Whether it was built, but in another format, by an older version: it needs a rebuild."""
        return self.build_info() is None and os.path.exists(self.build_json)

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
                if fresh and self.build_info() is None:
                    raise BadRequest(f"{self.m['deployment']} was built by an older version of the survey; rebuild it")
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
    matches = {(m["source"], m["receptor"], m["lmax_utc"]): m for m in t["event_matches"]}
    for e in t["noise_events"]:
        e["_lmax"] = parse_time(e["lmax_utc"])
        got = matches[(e["source"], e["receptor"], e["lmax_utc"])]  # match.py gives every event a row
        e.update({key: got[key] for key in MATCH_FIELDS})
    for c in t["coverage"]:
        c["_start"], c["_end"] = parse_time(c["start_utc"]), parse_time(c["end_utc"])
    approaches = {}
    for a in t["approaches"]:
        approaches.setdefault((a["source"], a["source_id"]), {})[a["receptor"]] = {
            "t": a["t"], "ground_m": number(a["ground_m"]), "height_m": number(a["height_m"]),
            "slant_m": number(a["slant_m"]), "at_track_end": a["at_track_end"] == "1",
            "path_angle_deg": number(a["path_angle_deg"])}
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
            "lon": float(r["lon"]), "public": r["public"] == "1"}


class App:
    def __init__(self, deployments_dir=None):
        self.dir = deployments_dir or paths.DEPLOYMENTS_DIR
        self.known = {}  # Deployment name -> its Deployment
        self.jobs = {}  # Deployment name -> its latest BuildJob, started from the page
        self.lock = threading.Lock()

    def deployment(self, name):
        """The deployment whose manifest is deployments_dir/<name>.json, or BadRequest."""
        for path in manifest.all_manifests(self.dir):
            if manifest.name_of(path) == name:
                with self.lock:
                    if name not in self.known:
                        self.known[name] = Deployment(path)
                    return self.known[name]
        raise BadRequest(f"no deployment {name!r}")

    def _listing(self, name, path):
        d = self.deployment(name)
        info = d.build_info()
        coverage = d.coverage() if info else []
        return {
            "deployment": name,
            "description": d.m["description"],
            "manifest": os.path.relpath(path, paths.TOOLS_DIR),
            "built": info is not None,
            "outdated": d.outdated(),
            "built_utc": info and info["built_utc"],
            "sources": ranked(d.m["sources"]),
            "receptors": [{"id": r["id"], "name": r["name"], "label": r["label"]} for r in d.m["receptors"].values()],
            "days": [{"day": day, "minutes": minutes_covered(coverage, *day_bounds(day))}
                     for day in days(d.m["start"], d.m["end"])] if info else [],
            "warnings": (info or {}).get("warnings", d.m["warnings"]),
        }

    def deployments(self):
        """Every deployment, with its days and how much data each source has on each."""
        found = []
        for path in manifest.all_manifests(self.dir):
            name = manifest.name_of(path)
            try:
                found.append(self._listing(name, path))
            except (manifest.ManifestError, ValueError, OSError) as error:
                found.append({"deployment": name, "error": str(error)})
        return found

    def rebuild(self, body, background=True):
        """Build a deployment again, unless it's being built already, here or by `make build`.

        In the background (as the page asks for it), this returns at once with the job's status,
        and build_status() follows it: a build may run adsb analyse, which can take minutes. With
        background=False it returns the build's summary when done, or raises BadRequest."""
        name = str(body.get("deployment", ""))
        d = self.deployment(name)
        if not d.building.acquire(blocking=False):
            raise BadRequest(f"{d.m['deployment']} is already being rebuilt")
        job = BuildJob(name)
        with self.lock:
            self.jobs[name] = job

        def run():
            try:
                job.summary = build.build(d.m, log=job, wait=False)
            except build.Busy as error:
                job.error = str(error)
            except Exception as error:  # reported to the page, which polls for it
                job.error = f"{type(error).__name__}: {error}"
            finally:
                job.finished = time.time()
                d.building.release()

        if background:
            threading.Thread(target=run, name=f"build {name}", daemon=True).start()
            return job.status()
        run()
        if job.error:
            raise BadRequest(job.error)
        return job.summary

    def build_status(self, query):
        """The latest rebuild started from the page for a deployment, or {"running": False} if none."""
        name = str(query.get("deployment", ""))
        self.deployment(name)  # BadRequest if there's no such deployment
        with self.lock:
            job = self.jobs.get(name)
        return job.status() if job else {"deployment": name, "running": False, "log": [], "error": None}

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
            "sources": ranked(d.m["sources"]),  # The order the page lists them in
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

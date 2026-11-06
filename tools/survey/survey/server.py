"""The survey app: every source's tracks, heights and noise for a day, on one page.

    python3 -m survey serve            then open http://127.0.0.1:8766

It only listens on this computer, and reads only built deployments (python3 -m survey build), so
it never touches a source's own files. Rebuild from the page, or on the command line, after
fetching more data. Downloads stay in each tool: the WebTrak app (python3 -m webtrak serve) and
`make viewer` in tools/opensky.
"""

from __future__ import annotations

import bisect
import datetime as dt
import http.server
import io
import json
import os
import threading
import time
import urllib.parse

from . import build, manifest, schema
from .common import number, parse_time

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACK_SPACING_S = 2.0  # Positions closer together than this are thinned for drawing
DAY_S = 86400
READ_ATTEMPTS = 5  # Tries at reading a build's tables while another build is replacing them


class BadRequest(Exception):
    pass


def _days(start, end):
    day = dt.datetime.fromtimestamp(start, dt.timezone.utc).date()
    last = dt.datetime.fromtimestamp(end - 1, dt.timezone.utc).date()
    while day <= last:
        yield day.isoformat()
        day += dt.timedelta(days=1)


def _day_bounds(day):
    start = parse_time(f"{day}T00:00:00Z")
    return start, start + DAY_S


class Deployment:
    """One deployment's built tables, read once and kept until build.json changes."""

    def __init__(self, path, lock=None):
        self.manifest_path = path
        self.m = manifest.load(path)
        self.folder = os.path.join(self.m["out_dir"], "common")
        self.stamp = None
        self.tables = None
        # Held while this deployment is rebuilt, and while its tables are read, so a request never
        # sees half-written tables. Other deployments, and the list of them, don't wait for it.
        # The App keeps one per deployment name, so it outlives a re-read of the manifest.
        self.lock = lock or threading.Lock()

    def build_info(self):
        path = os.path.join(self.m["out_dir"], "build.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def _identity(self):
        """What changes when a build finishes: build.json's time, and the tables' folder, which a
        build replaces as a whole (build.write_tables)."""
        path = os.path.join(self.m["out_dir"], "build.json")
        try:
            return os.path.getmtime(path), os.stat(self.folder).st_ino
        except FileNotFoundError:
            return None

    def load(self):
        with self.lock:
            for _ in range(READ_ATTEMPTS):
                before = self._identity()
                if before is None:
                    if not os.path.exists(os.path.join(self.m["out_dir"], "build.json")):
                        raise BadRequest(f"{self.m['deployment']} isn't built yet")
                    time.sleep(0.1)  # A build outside the app is putting its tables in place
                    continue
                if before == self.stamp:
                    return self.tables
                tables = index({name: schema.read_table(self.folder, name) for name in schema.TABLES})
                if self._identity() == before:  # No build finished while they were read
                    self.tables, self.stamp = tables, before
                    return tables
            raise BadRequest(f"{self.m['deployment']} is being rebuilt; try again in a moment")

    def coverage(self):
        """Only the coverage table: enough to list the days, without reading every position."""
        return schema.read_table(self.folder, "coverage")


def index(t):
    """The tables, with what a day's request needs worked out once: times as numbers, positions by
    track as tuples (far smaller than a dict per row), and levels in time order."""
    for f in t["flights"]:
        f["_first"], f["_last"] = parse_time(f["first_utc"]), parse_time(f["last_utc"])
    tracks, kinds = {}, {}
    for p in t["positions"]:
        key = (p["source"], p["source_id"])
        tracks.setdefault(key, []).append((float(p["t"]), float(p["lat"]), float(p["lon"]), number(p["height_m"])))
        kinds.setdefault(key, p["height_kind"])
    for pts in tracks.values():
        pts.sort()
    levels = sorted((float(lv["t"]), lv["receptor"], float(lv["level_db"])) for lv in t["levels"])
    approaches = {}
    for a in t["approaches"]:
        approaches.setdefault((a["source"], a["source_id"]), {})[a["receptor"]] = {
            "t": a["t"], "ground_m": number(a["ground_m"]), "height_m": number(a["height_m"]),
            "slant_m": number(a["slant_m"]), "at_track_end": a["at_track_end"] == "1"}
    return {**t, "positions": None, "levels": None, "tracks": tracks, "height_kinds": kinds,
            "level_rows": levels, "level_times": [lv[0] for lv in levels], "approach_index": approaches,
            "pass_index": {(p["source"], p["source_id"]): p for p in t["passes"]}}


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
                        lock = self.locks.setdefault(name, threading.Lock())
                        self.cache[name] = ((path, stamp), Deployment(path, lock))
                    return self.cache[name][1]
        raise BadRequest(f"no deployment {name!r}")

    def deployments(self):
        found = []
        for path in manifest.all_manifests(self.dir):
            name = os.path.splitext(os.path.basename(path))[0]
            try:
                d = self.deployment(name)
            except (manifest.ManifestError, ValueError, OSError) as error:
                found.append({"deployment": name, "error": str(error)})
                continue
            info = d.build_info()
            days = []
            if info:
                coverage = d.coverage()
                for day in _days(d.m["start"], d.m["end"]):
                    lo, hi = _day_bounds(day)
                    minutes = {}
                    for c in coverage:
                        a, b = max(lo, parse_time(c["start_utc"])), min(hi, parse_time(c["end_utc"]))
                        if a < b:
                            minutes[c["source"]] = minutes.get(c["source"], 0) + (b - a) / 60
                    days.append({"day": day, "minutes": {k: round(v) for k, v in minutes.items()}})
            found.append({
                "deployment": name,
                "description": d.m["description"],
                "manifest": os.path.relpath(path, manifest.TOOLS_DIR),
                "built": info is not None,
                "built_utc": info and info["built_utc"],
                "sources": list(d.m["sources"]),
                "receptors": [{"id": r["id"], "name": r["name"], "label": r["label"]} for r in d.m["receptors"].values()],
                "days": days,
                "warnings": (info or {}).get("warnings", d.m["warnings"]),
            })
        return found

    def rebuild(self, body):
        d = self.deployment(str(body.get("deployment", "")))
        if not d.lock.acquire(blocking=False):
            raise BadRequest(f"{d.m['deployment']} is already being rebuilt")
        try:
            d.m = manifest.load(d.manifest_path)
            return build.build(d.m, log=io.StringIO())
        finally:
            d.lock.release()

    def day(self, query):
        d = self.deployment(query.get("deployment", ""))
        day = query.get("day", "")
        try:
            lo, hi = _day_bounds(day)
        except ValueError:
            raise BadRequest(f"bad day {day!r}") from None
        t = d.load()
        in_day = lambda text: lo <= parse_time(text) < hi  # noqa: E731

        flights, day_passes = [], set()
        for f in t["flights"]:
            if f["_last"] < lo or f["_first"] >= hi:
                continue
            key = (f["source"], f["source_id"])
            link = t["pass_index"].get(key, {})
            day_passes.add(link.get("pass_id", ""))
            flights.append({**{k: v for k, v in f.items() if not k.startswith("_")},
                            "pass_id": link.get("pass_id", ""), "evidence": link.get("evidence", ""),
                            "height_kind": t["height_kinds"].get(key, ""),
                            "approaches": t["approach_index"].get(key, {})})
        tracks = {}
        for f in flights:
            key = (f["source"], f["source_id"])
            out, last = [], None
            for tt, lat, lon, height in t["tracks"].get(key, []):
                if last is not None and tt - last < TRACK_SPACING_S:
                    continue
                last = tt
                out.append([round(tt, 1), lat, lon, height])
            tracks[f"{key[0]}|{key[1]}"] = out
        unseen = {}
        for u in t["unseen"]:
            if u["pass_id"] in day_passes:
                unseen.setdefault(u["pass_id"], {})[u["source"]] = u["reason"]
        receptors = []
        for r in t["receptors"]:
            receptors.append({"id": r["id"], "name": r["name"], "label": r["label"], "lat": float(r["lat"]),
                              "lon": float(r["lon"]), "public": r["public"] == "True",
                              "mic_amsl_m": (number(r["ground_elevation_m"]) or 0) + (number(r["mic_height_m"]) or 0)})
        times = t["level_times"]
        levels = t["level_rows"][bisect.bisect_left(times, lo):bisect.bisect_left(times, hi)]
        return {
            "deployment": d.m["deployment"],
            "day": day,
            "start": lo,
            "sources": list(d.m["sources"]),
            "receptors": receptors,
            "coverage": [c for c in t["coverage"] if parse_time(c["end_utc"]) > lo and parse_time(c["start_utc"]) < hi],
            "flights": flights,
            "unseen": unseen,
            "tracks": tracks,
            "events": [e for e in t["noise_events"] if in_day(e["lmax_utc"])],
            "levels": [[round(lt - lo, 1), receptor, db] for lt, receptor, db in levels],
        }


class Handler(http.server.BaseHTTPRequestHandler):
    app: App = None
    server_version = "survey"

    def log_message(self, fmt, *args):
        pass

    def _local_host(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _run(self, fn, *args):
        try:
            self._send(200, fn(*args))
        except BadRequest as error:
            self._send(400, {"error": str(error)})
        except Exception as error:  # report it to the page rather than drop the connection
            self._send(500, {"error": f"{type(error).__name__}: {error}"})

    def do_GET(self):
        if not self._local_host():  # refuse pages reached through another host name (DNS rebinding)
            return self._send(403, {"error": "local use only"})
        url = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path in ("/", "/index.html"):
            with open(os.path.join(PACKAGE_DIR, "ui.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        routes = {"/api/deployments": self.app.deployments, "/api/day": lambda: self.app.day(query)}
        if url.path in routes:
            return self._run(routes[url.path])
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # JSON only: a page on another site can't send that without the browser asking first.
        if not self._local_host() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(403, {"error": "local use only"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad JSON"})
        if self.path == "/api/build":
            return self._run(self.app.rebuild, body)
        self._send(404, {"error": "not found"})


def serve(port=8766, open_browser=True, deployments_dir=None):
    Handler.app = App(deployments_dir)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Survey app at {url}  (Ctrl-C to close it)", flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def main(args):
    return serve(args.port, not args.no_browser)

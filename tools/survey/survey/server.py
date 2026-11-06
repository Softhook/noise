"""The survey app: every source's tracks, heights and noise for a day, on one page.

    python3 -m survey serve            then open http://127.0.0.1:8766

It only listens on this computer, and reads only built deployments (python3 -m survey build), so
it never touches a source's own files. Rebuild from the page, or on the command line, after
fetching more data. Downloads stay in each tool: the WebTrak app (python3 -m webtrak serve) and
`make viewer` in tools/opensky.
"""

from __future__ import annotations

import datetime as dt
import http.server
import io
import json
import os
import threading
import urllib.parse

from . import build, manifest, schema
from .common import number, parse_time

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACK_SPACING_S = 2.0  # Positions closer together than this are thinned for drawing
DAY_S = 86400


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

    def __init__(self, path):
        self.manifest_path = path
        self.m = manifest.load(path)
        self.folder = os.path.join(self.m["out_dir"], "common")
        self.stamp = None
        self.tables = None
        # Held while this deployment is rebuilt, and while its tables are read, so a request never
        # sees half-written tables. Other deployments, and the list of them, don't wait for it.
        self.lock = threading.Lock()

    def build_info(self):
        path = os.path.join(self.m["out_dir"], "build.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def load(self):
        with self.lock:
            path = os.path.join(self.m["out_dir"], "build.json")
            stamp = os.path.getmtime(path) if os.path.exists(path) else None
            if stamp is None:
                raise BadRequest(f"{self.m['deployment']} isn't built yet")
            if stamp != self.stamp:
                self.tables = {name: schema.read_table(self.folder, name) for name in schema.TABLES}
                self.stamp = stamp
            return self.tables

    def coverage(self):
        """Only the coverage table: enough to list the days, without reading every position."""
        return schema.read_table(self.folder, "coverage")


class App:
    def __init__(self, deployments_dir=None):
        self.dir = deployments_dir or manifest.DEPLOYMENTS_DIR
        self.cache = {}
        self.lock = threading.Lock()

    def deployment(self, name):
        """A deployment, read again whenever its manifest file changes."""
        for path in manifest.all_manifests(self.dir):
            if os.path.splitext(os.path.basename(path))[0] == name:
                stamp = os.path.getmtime(path)
                with self.lock:
                    cached = self.cache.get(name)
                    if not cached or cached[0] != (path, stamp):
                        self.cache[name] = ((path, stamp), Deployment(path))
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

        passes = {(p["source"], p["source_id"]): p for p in t["passes"]}
        approaches = {}
        for a in t["approaches"]:
            approaches.setdefault((a["source"], a["source_id"]), {})[a["receptor"]] = {
                "t": a["t"], "ground_m": number(a["ground_m"]), "height_m": number(a["height_m"]),
                "slant_m": number(a["slant_m"]), "at_track_end": a["at_track_end"] == "1"}
        flights, day_passes = [], set()
        for f in t["flights"]:
            if parse_time(f["last_utc"]) < lo or parse_time(f["first_utc"]) >= hi:
                continue
            key = (f["source"], f["source_id"])
            link = passes.get(key, {})
            day_passes.add(link.get("pass_id", ""))
            flights.append({**f, "pass_id": link.get("pass_id", ""), "evidence": link.get("evidence", ""),
                            "approaches": approaches.get(key, {})})
        keys = {(f["source"], f["source_id"]) for f in flights}
        tracks, last = {}, {}
        for p in t["positions"]:
            key = (p["source"], p["source_id"])
            if key not in keys:
                continue
            tt = float(p["t"])
            if key in last and tt - last[key] < TRACK_SPACING_S:
                continue
            last[key] = tt
            tracks.setdefault(f"{key[0]}|{key[1]}", []).append(
                [round(tt, 1), float(p["lat"]), float(p["lon"]), number(p["height_m"])])
        unseen = {}
        for u in t["unseen"]:
            if u["pass_id"] in day_passes:
                unseen.setdefault(u["pass_id"], {})[u["source"]] = u["reason"]
        receptors = []
        for r in t["receptors"]:
            receptors.append({"id": r["id"], "name": r["name"], "label": r["label"], "lat": float(r["lat"]),
                              "lon": float(r["lon"]), "public": r["public"] == "True",
                              "mic_amsl_m": (number(r["ground_elevation_m"]) or 0) + (number(r["mic_height_m"]) or 0)})
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
            "levels": [[round(float(lv["t"]) - lo, 1), lv["receptor"], float(lv["level_db"])]
                       for lv in t["levels"] if lo <= float(lv["t"]) < hi],
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

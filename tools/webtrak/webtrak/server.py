"""A small local web app for starting downloads, watching them and looking at the results.

    python3 -m webtrak serve            then open http://127.0.0.1:8765

It only listens on this computer. Downloads run as ordinary `webtrak fetch` / `webtrak follow`
processes in their own session, so they carry on if the app is closed; their details are kept in
OUT/<site>/jobs/ so a restarted app picks them up again. Progress is read from each monitor's
state.json, so a download started from the command line shows up too (as a writer on its monitor).
"""

from __future__ import annotations

import datetime as dt
import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse

from . import client as client_mod
from . import parse, stats, store

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(PACKAGE_DIR)
MAX_STATS_DAYS = 31


class BadRequest(Exception):
    pass


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tail(path, lines=12):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            return f.read().decode("utf-8", "replace").splitlines()[-lines:]
    except OSError:
        return []


class App:
    def __init__(self, out_root, site="lcy", python=sys.executable, client=None):
        self.out_root = out_root
        self.site = site
        self.site_dir = os.path.join(out_root, site)
        self.jobs_dir = os.path.join(self.site_dir, "jobs")
        self.python = python
        self.client = client or client_mod.Client(site=site)
        self._lock = threading.Lock()
        self._procs = {}       # job id -> Popen, for jobs started by this app
        self._progress = {}    # job id -> [(monotonic time, chunks saved)] for the download rate
        self._range = None     # (time fetched, reply) for WebTrak's range, cached briefly

    # --- reading ---------------------------------------------------------------------------

    def monitors(self):
        try:
            with open(os.path.join(self.site_dir, "monitors.json")) as f:
                known = json.load(f)
        except (OSError, ValueError):
            from .__main__ import KNOWN_MONITORS
            known = KNOWN_MONITORS.get(self.site, [])
        return [{"id": str(m["id"]), "name": m.get("name", ""), "lat": m.get("lat"), "lon": m.get("lon")}
                for m in known]

    def monitor_dir(self, monitor_id):
        if not str(monitor_id).isdigit():
            raise BadRequest(f"bad monitor id {monitor_id!r}")
        return os.path.join(self.site_dir, f"nmt{monitor_id}")

    def webtrak_range(self):
        """WebTrak's period and delay; asked for at most once every 5 minutes."""
        with self._lock:
            if self._range and time.monotonic() - self._range[0] < 300:
                return self._range[1]
        try:
            first, last = self.client.date_range()
            latest = self.client.latest_handle()
            reply = {"first": first, "last": last, "latest_utc": parse.utc_for_handle(latest + 1),
                     "lag_min": round((time.time() - parse.utc_for_handle(latest + 1)) / 60)}
        except (OSError, parse.NotAvailable) as error:
            reply = {"error": str(error)}
        with self._lock:
            self._range = (time.monotonic(), reply)
        return reply

    def plan(self, query):
        start, end, ids = self._period(query)
        first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
        todo = set()
        for mid in ids:
            saved = store.read_state(self.monitor_dir(mid)).get("saved", [])
            todo.update(h for a, b in store.gaps(saved, first, last) for h in range(a, b + 1))
        cache = store.RawCache(self.site_dir)
        downloads = sum(1 for h in todo if not cache.has(h))
        delay = max(0.5, float(query.get("delay", 2.0)))
        return {"chunks": last - first + 1, "to_save": len(todo), "to_download": downloads,
                "minutes": round(downloads * (delay + client_mod.TYPICAL_REPLY_S) / 60, 1),
                "busy": [mid for mid in ids if store.is_locked(self.monitor_dir(mid))]}

    def status(self):
        monitors = []
        names = {m["id"]: m["name"] for m in self.monitors()}
        try:
            folders = sorted(n for n in os.listdir(self.site_dir) if n.startswith("nmt") and n[3:].isdigit())
        except OSError:
            folders = []
        for folder in folders:
            mid = folder[3:]
            path = os.path.join(self.site_dir, folder)
            state = store.read_state(path)
            saved = state.get("saved", [])
            monitors.append({
                "id": mid, "name": names.get(mid, ""), "writing": store.is_locked(path),
                "chunks": sum(b - a + 1 for a, b in saved), "ranges": len(saved),
                "first_utc": parse.utc_for_handle(saved[0][0]) if saved else None,
                "last_utc": parse.utc_for_handle(saved[-1][1] + 1) if saved else None,
                "pending_events": len(state.get("pending", []))})
        return {"monitors": monitors, "jobs": [self._job_status(job) for job in self._load_jobs()],
                "now": time.time()}

    def coverage(self, query):
        """Which chunks of one local day each monitor has saved, as a string of 0s and 1s."""
        day = query.get("day") or ""
        try:
            next_day = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
            start = parse.local_to_utc(f"{day} 00:00")
        except ValueError:
            raise BadRequest(f"bad day {day!r}")
        end = parse.local_to_utc(f"{next_day} 00:00")  # 23 or 25 hours away on clock-change days
        first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
        out = {}
        for m in self.status()["monitors"]:
            saved = store.read_state(self.monitor_dir(m["id"])).get("saved", [])
            bits = bytearray(b"0" * (last - first + 1))
            for a, b in saved:
                for h in range(max(a, first), min(b, last) + 1):
                    bits[h - first] = ord("1")
            out[m["id"]] = bits.decode()
        return {"day": day, "start_utc": start, "end_utc": end, "monitors": out}

    def statistics(self, query):
        start, end, ids = self._period(query, max_days=MAX_STATS_DAYS)
        if len(ids) != 1:
            raise BadRequest("statistics are for one monitor at a time")
        return stats.summary(self.monitor_dir(ids[0]), start, end)

    def _period(self, query, max_days=None):
        try:
            start, end = parse.local_to_utc(query["from"]), parse.local_to_utc(query["to"])
        except (KeyError, ValueError):
            raise BadRequest("from and to must be local times, YYYY-MM-DD HH:MM")
        if end <= start:
            raise BadRequest("to must be after from")
        if max_days and end - start > max_days * 86400:
            raise BadRequest(f"at most {max_days} days at a time")
        ids = [m.strip() for m in str(query.get("nmt", "")).split(",") if m.strip()]
        if not ids or not all(m.isdigit() for m in ids):
            raise BadRequest("choose at least one monitor")
        return start, end, ids

    # --- jobs ------------------------------------------------------------------------------

    def start_job(self, body):
        kind = body.get("kind")
        if kind not in ("fetch", "follow"):
            raise BadRequest("kind must be fetch or follow")
        ids = [m.strip() for m in str(body.get("nmt", "")).split(",") if m.strip()]
        if not ids or not all(m.isdigit() for m in ids):
            raise BadRequest("choose at least one monitor")
        busy = [mid for mid in ids if store.is_locked(self.monitor_dir(mid))]
        if busy:
            raise BadRequest(f"NMT{', NMT'.join(busy)} already has a download writing to it; stop that first")
        delay = max(0.5, float(body.get("delay", 2.0 if kind == "fetch" else 1.0)))
        args = [kind, "--site", self.site, "--out", self.out_root, "--nmt", ",".join(ids), "--delay", f"{delay:g}"]
        job = {"kind": kind, "nmt": ids, "delay": delay, "started": time.time()}
        if kind == "fetch":
            start, end, _ = self._period(body)
            args += ["--from", body["from"].replace("T", " "), "--to", body["to"].replace("T", " "), "--quiet"]
            job.update(start_utc=start, end_utc=end, **{"from": body["from"], "to": body["to"]})
        else:
            backfill = min(48.0, max(0.0, float(body.get("backfill", 1.0))))
            args += ["--backfill", f"{backfill:g}"]
            job["backfill"] = backfill

        os.makedirs(self.jobs_dir, exist_ok=True)
        job_id = time.strftime("%Y%m%d-%H%M%S") + f"-{kind}"
        job.update(id=job_id, log=os.path.join(self.jobs_dir, f"{job_id}.log"), args=args)
        env = dict(os.environ, PYTHONPATH=TOOL_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""),
                   PYTHONUNBUFFERED="1")
        with open(job["log"], "w") as log:
            proc = subprocess.Popen([self.python, "-m", "webtrak", *args], cwd=TOOL_DIR, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        job["pid"] = proc.pid
        with self._lock:
            self._procs[job_id] = proc
        self._write_job(job)
        return self._job_status(job)

    def stop_job(self, body):
        job = self._find_job(body.get("id"))
        if job.get("exit") is None and _alive(job["pid"]):
            os.kill(job["pid"], signal.SIGTERM)  # stops between chunks; see Stop in __main__
        return self._job_status(job)

    def forget_job(self, body):
        job = self._find_job(body.get("id"))
        if self._running(job):
            raise BadRequest("stop the job first")
        for path in (os.path.join(self.jobs_dir, f"{job['id']}.json"), job["log"]):
            try:
                os.remove(path)
            except OSError:
                pass
        return {"forgotten": job["id"]}

    def _find_job(self, job_id):
        for job in self._load_jobs():
            if job["id"] == job_id:
                return job
        raise BadRequest(f"no job {job_id!r}")

    def _write_job(self, job):
        path = os.path.join(self.jobs_dir, f"{job['id']}.json")
        with open(path + ".tmp", "w") as f:
            json.dump(job, f, indent=1)
        os.replace(path + ".tmp", path)

    def _load_jobs(self):
        jobs = []
        try:
            names = sorted(os.listdir(self.jobs_dir), reverse=True)
        except OSError:
            return jobs
        for name in names:
            if name.endswith(".json"):
                try:
                    with open(os.path.join(self.jobs_dir, name)) as f:
                        jobs.append(json.load(f))
                except (OSError, ValueError):
                    continue
        return jobs

    def _running(self, job):
        with self._lock:
            proc = self._procs.get(job["id"])
        if proc is not None:
            code = proc.poll()
            if code is None:
                return True
            if job.get("exit") is None:
                job["exit"], job["ended"] = code, time.time()
                self._write_job(job)
            return False
        if job.get("exit") is None and not _alive(job["pid"]):
            job["exit"], job["ended"] = "unknown", time.time()  # ended while the app was closed
            self._write_job(job)
        return job.get("exit") is None

    def _job_status(self, job):
        running = self._running(job)
        out = {k: job.get(k) for k in ("id", "kind", "nmt", "from", "to", "backfill", "delay", "started",
                                       "ended", "exit", "pid")}
        out.update(running=running, log=_tail(job["log"]))
        states = [store.read_state(self.monitor_dir(mid)) for mid in job["nmt"]]
        if job["kind"] == "fetch":
            first = parse.handle_for_utc(job["start_utc"])
            last = parse.handle_for_utc(job["end_utc"] - 1)
            done = min(store.count_saved(s.get("saved", []), first, last) for s in states)
            total = last - first + 1
            out.update(total=total, done=done)
            samples = self._progress.setdefault(job["id"], [])
            now = time.monotonic()
            if running and (not samples or samples[-1][1] != done or now - samples[-1][0] > 5):
                samples.append((now, done))
                del samples[:-30]
            rate = None
            if len(samples) >= 2 and samples[-1][0] > samples[0][0]:
                rate = (samples[-1][1] - samples[0][1]) / (samples[-1][0] - samples[0][0]) * 60
            out.update(per_minute=round(rate, 1) if rate else None,
                       eta_min=round((total - done) / rate, 1) if rate and running else None)
        else:
            lasts = [s["saved"][-1][1] for s in states if s.get("saved")]
            out["last_utc"] = parse.utc_for_handle(min(lasts) + 1) if lasts else None
        return out


class Handler(http.server.BaseHTTPRequestHandler):
    app: App = None
    server_version = "webtrak"

    def log_message(self, fmt, *args):  # quiet: the status page polls every few seconds
        pass

    def _local_host(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "[::1]")

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
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
        app = self.app
        routes = {"/api/status": lambda: app.status(), "/api/monitors": lambda: app.monitors(),
                  "/api/range": lambda: app.webtrak_range(), "/api/plan": lambda: app.plan(query),
                  "/api/coverage": lambda: app.coverage(query), "/api/stats": lambda: app.statistics(query)}
        if url.path in ("/", "/index.html", "/ui.html"):
            with open(os.path.join(PACKAGE_DIR, "ui.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
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
        routes = {"/api/jobs": self.app.start_job, "/api/jobs/stop": self.app.stop_job,
                  "/api/jobs/forget": self.app.forget_job}
        if self.path in routes:
            return self._run(routes[self.path], body)
        self._send(404, {"error": "not found"})


def serve(out_root, site="lcy", port=8765, open_browser=True):
    Handler.app = App(out_root, site)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"WebTrak app at {url}  (Ctrl-C to close it; downloads carry on)", flush=True)
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

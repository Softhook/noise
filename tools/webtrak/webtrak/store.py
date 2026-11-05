"""Write chunks to CSV files for one monitor, and match its events to aircraft.

Layout, under OUT/<site>/nmt<id>/:

    levels/YYYY-MM-DD.csv     one row per second: UTC, local time, level, flag
    aircraft/YYYY-MM-DD.csv   radar positions within --radius of the monitor
    events.csv                one row per noise event, with the aircraft that passed closest
    state.json                which chunks are saved, and events still waiting for radar
    lock                      held while a process writes here, so two can't at once

and, shared by every monitor, OUT/<site>/raw/YYYY-MM-DD/<handle>.txt.gz: each chunk as received
(the folder is the UTC day), so that a chunk is downloaded only once whichever monitors are wanted.

An event is listed once, in the chunk where it starts, but the radar for the minute after its
LAmax can be in the next chunks. So events wait in state.json until every chunk in their
matching window is saved (or the data has moved GIVE_UP_S past it), and are matched then.

Folders under levels/ and aircraft/ use local (Europe/London) days. Times in the files are ISO 8601, UTC with a Z, and local
with its offset.
"""

from __future__ import annotations

import collections
import csv
import dataclasses
import datetime as dt
import gzip
import json
import math
import os

try:
    import fcntl
except ImportError:  # Windows: no locking
    fcntl = None

from . import parse

LEVEL_FIELDS = ["time_utc", "time_local", "level_db", "flag"]
AIRCRAFT_FIELDS = ["time_utc", "time_local", "track", "callsign", "type", "registration", "direction",
                   "airport", "origin", "destination", "lat", "lon", "height_m", "altitude_m", "speed_ms",
                   "distance_m", "slant_m"]
EVENT_FIELDS = ["start_utc", "start_local", "lmax_time_local", "end_local", "duration_s", "lmax_db", "sel_db",
                "leq_db", "epnl_db", "event_class", "callsign", "type", "direction", "airport", "track",
                "closest_time_local", "closest_distance_m", "closest_height_m", "closest_slant_m",
                "lmax_after_closest_s", "candidates"]

MATCH_WINDOW_S = 60      # look this far either side of the LAmax time for aircraft
GIVE_UP_S = 10 * 60      # match with what we have once the data is this far past the window
KEEP_S = 2 * 3600        # keep this much radar in memory either side of the newest chunk


def iso_utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_local(t, offset_s):
    zone = dt.timezone(dt.timedelta(seconds=offset_s))
    return dt.datetime.fromtimestamp(t, zone).isoformat()


def local_day(t, offset_s):
    return dt.datetime.fromtimestamp(t + offset_s, dt.timezone.utc).strftime("%Y-%m-%d")


def ground_distance(lat1, lon1, lat2, lon2):
    """Metres, by an equirectangular approximation: well under 0.1% error within 20 km."""
    mean = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(mean) * 6371008.8
    dy = math.radians(lat2 - lat1) * 6371008.8
    return math.hypot(dx, dy)


def _round(value, places=1):
    if value is None:
        return ""
    r = round(value, places)
    return int(r) if places == 0 else r


def match_event(event, positions, monitor, window=MATCH_WINDOW_S):
    """Pick the aircraft whose closest approach to the monitor, near the event's LAmax, was nearest.

    Returns a dict for the event row; its values are blank if no aircraft was in range.
    """
    tracks = collections.defaultdict(list)
    for p in positions:
        if abs(p.utc - event.lmax_time) <= window:
            tracks[p.track].append(p)
    best = None
    for points in tracks.values():
        for p in points:
            d = ground_distance(monitor["lat"], monitor["lon"], p.lat, p.lon)
            slant = math.hypot(d, p.height_m or 0.0)
            if best is None or slant < best[0]:
                best = (slant, d, p)
    if best is None:
        return {"candidates": 0}
    slant, d, p = best
    return {"callsign": p.callsign, "type": p.aircraft_type, "direction": p.direction, "airport": p.airport,
            "track": p.track, "closest_time_local": iso_local(p.utc, event.offset_s),
            "closest_distance_m": round(d), "closest_height_m": _round(p.height_m, 0),
            "closest_slant_m": round(slant), "lmax_after_closest_s": round(event.lmax_time - p.utc),
            "candidates": len(tracks)}


def match_handles(event, window=MATCH_WINDOW_S):
    """The chunks whose radar the event's match needs."""
    return range(parse.handle_for_utc(event.lmax_time - window), parse.handle_for_utc(event.lmax_time + window) + 1)


def _position_from_row(row):
    def number(key):
        return float(row[key]) if row.get(key) else None
    t = dt.datetime.strptime(row["time_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    return parse.Position(
        utc=t, track=row["track"], direction=row["direction"], airport=row["airport"], aircraft_type=row["type"],
        callsign=row["callsign"], registration=row["registration"], squawk="", lat=float(row["lat"]),
        lon=float(row["lon"]), height_m=number("height_m"), altitude_m=number("altitude_m"),
        speed_ms=number("speed_ms"), origin=row["origin"], destination=row["destination"])


class RawCache:
    """Chunks as received, gzipped, shared by all monitors of a site."""

    def __init__(self, site_dir):
        self.dir = os.path.join(site_dir, "raw")

    def path(self, handle):
        day = dt.datetime.fromtimestamp(parse.utc_for_handle(handle), dt.timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.dir, day, f"{handle}.txt.gz")

    def has(self, handle):
        return os.path.exists(self.path(handle))

    def get(self, handle):
        try:
            with gzip.open(self.path(handle), "rt", encoding="utf-8") as f:
                return f.read()
        except (OSError, EOFError):
            return None

    def put(self, handle, text):
        path = self.path(handle)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + ".tmp"
        with gzip.open(temp, "wt", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp, path)


class MonitorStore:
    def __init__(self, root, monitor, radius_m=3000.0):
        self.monitor = monitor
        self.dir = os.path.join(root, f"nmt{monitor['id']}")
        self.radius_m = radius_m
        self.state_path = os.path.join(self.dir, "state.json")
        self.events_path = os.path.join(self.dir, "events.csv")
        os.makedirs(self.dir, exist_ok=True)
        self.state = self._load_state()
        self.pending = []
        for d in self.state.get("pending", []):
            try:
                self.pending.append(parse.Event(**d))
            except TypeError:
                continue
        self.seen_events = self._load_event_keys() | {e.key for e in self.pending}
        self.radar = collections.defaultdict(list)  # handle -> nearby positions in that chunk
        self.loaded = set()                         # handles whose nearby radar is in self.radar
        self._lock_file = None

    def lock(self):
        """Stop a second process writing to this monitor's files at the same time."""
        if fcntl is None:
            return
        self._lock_file = open(os.path.join(self.dir, "lock"), "w")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit(f"another webtrak process is writing to {self.dir}; stop it first")

    # --- state ----------------------------------------------------------------------------

    def _load_state(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        self.state["monitor"] = self.monitor
        self.state["pending"] = [dataclasses.asdict(e) for e in self.pending]
        temp = self.state_path + ".tmp"
        with open(temp, "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(temp, self.state_path)

    @property
    def last_handle(self):
        ranges = self.state.get("saved", [])
        return ranges[-1][1] if ranges else None

    def has(self, handle):
        return any(a <= handle <= b for a, b in self.state.get("saved", []))

    def _mark_saved(self, handle):
        ranges = self.state.setdefault("saved", [])
        ranges.append([handle, handle])
        ranges.sort()
        merged = []
        for a, b in ranges:
            if merged and a <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        self.state["saved"] = merged

    def gaps(self, first, last):
        """Handles between first and last (inclusive) that haven't been saved, as (a, b) ranges."""
        out, cursor = [], first
        for a, b in self.state.get("saved", []):
            if b < cursor:
                continue
            if a > last:
                break
            if a > cursor:
                out.append((cursor, a - 1))
            cursor = max(cursor, b + 1)
        if cursor <= last:
            out.append((cursor, last))
        return out

    # --- radar for matching ---------------------------------------------------------------

    def _load_aircraft_day(self, day, wanted=None, since=None):
        """Read saved nearby radar for one local day into memory."""
        path = os.path.join(self.dir, "aircraft", f"{day}.csv")
        try:
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
        except OSError:
            return
        for row in rows:
            try:
                p = _position_from_row(row)
            except (KeyError, ValueError):
                continue
            h = parse.handle_for_utc(p.utc)
            if h in self.loaded or (wanted is not None and h not in wanted) or (since is not None and p.utc < since):
                continue
            self.radar[h].append(p)

    def prime_buffer(self):
        """After a restart, reload recent nearby radar so waiting events can still be matched."""
        if self.last_handle is None:
            return
        since = parse.utc_for_handle(self.last_handle) - KEEP_S
        folder = os.path.join(self.dir, "aircraft")
        try:
            days = sorted(n[:-4] for n in os.listdir(folder) if n.endswith(".csv"))[-2:]
        except OSError:
            return
        for day in days:
            self._load_aircraft_day(day, since=since)
        self.loaded.update(h for h in range(parse.handle_for_utc(since), self.last_handle + 1) if self.has(h))

    def _positions_for(self, event):
        handles = [h for h in match_handles(event) if self.has(h)]
        missing = {h for h in handles if h not in self.loaded}
        if missing:  # saved in an earlier run and no longer in memory: read them back
            days = {local_day(parse.utc_for_handle(h) + dx, event.offset_s) for h in missing for dx in (0, 29)}
            for day in sorted(days):
                self._load_aircraft_day(day, wanted=missing)
            self.loaded.update(missing)
        return [p for h in handles for p in self.radar.get(h, ())]

    def _prune(self, handle):
        keep = KEEP_S // parse.WINDOW_S
        needed = {h for e in self.pending for h in match_handles(e)}
        for h in [h for h in self.loaded | set(self.radar) if abs(h - handle) > keep and h not in needed]:
            self.radar.pop(h, None)
            self.loaded.discard(h)

    def _load_event_keys(self):
        keys = set()
        try:
            with open(self.events_path, newline="") as f:
                for row in csv.DictReader(f):
                    start = dt.datetime.strptime(row["start_utc"], "%Y-%m-%dT%H:%M:%SZ")
                    keys.add((self.monitor["id"], round(start.replace(tzinfo=dt.timezone.utc).timestamp())))
        except (OSError, KeyError, ValueError):
            pass
        return keys

    # --- writing --------------------------------------------------------------------------

    def _append(self, path, fields, rows):
        if not rows:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if new:
                writer.writeheader()
            writer.writerows(rows)

    def _event_row(self, event):
        off = event.offset_s
        row = {"start_utc": iso_utc(event.start), "start_local": iso_local(event.start, off),
               "lmax_time_local": iso_local(event.lmax_time, off), "end_local": iso_local(event.end, off),
               "duration_s": event.duration, "lmax_db": event.lmax, "sel_db": event.sel, "leq_db": event.leq,
               "epnl_db": event.epnl, "event_class": event.event_class}
        row.update(match_event(event, self._positions_for(event), self.monitor))
        return row

    def _match(self, ready):
        """Match and write the events for which ready(event) is true; return their rows."""
        done = [e for e in self.pending if ready(e)]
        if not done:
            return []
        self.pending = [e for e in self.pending if not ready(e)]
        rows = [self._event_row(e) for e in sorted(done, key=lambda e: e.start)]
        self._append(self.events_path, EVENT_FIELDS, rows)
        return rows

    def finish(self, up_to_handle):
        """Match waiting events whose window starts by up_to_handle, with whatever radar is saved.

        For the end of a historical fetch; events after it, such as ones from following, keep waiting.
        """
        rows = self._match(lambda e: match_handles(e)[0] <= up_to_handle)
        if rows:
            self._save_state()
        return rows

    def save(self, chunk, text=None):
        """Save one chunk and return a summary for the console, or None if it was saved before.

        The summary's events are the ones matched now, which may have come from earlier chunks.
        """
        if self.has(chunk.handle):
            return None
        mid = self.monitor["id"]
        off = chunk.offset_s

        levels = sorted((lv for lv in chunk.levels if lv.monitor == mid), key=lambda lv: lv.utc)
        by_day = collections.defaultdict(list)
        for lv in levels:
            by_day[local_day(lv.utc, off)].append({"time_utc": iso_utc(lv.utc), "time_local": iso_local(lv.utc, off),
                                                   "level_db": lv.level, "flag": lv.flag})
        for day, rows in by_day.items():
            self._append(os.path.join(self.dir, "levels", f"{day}.csv"), LEVEL_FIELDS, rows)

        near = []
        for p in chunk.positions:
            d = ground_distance(self.monitor["lat"], self.monitor["lon"], p.lat, p.lon)
            if d <= self.radius_m:
                near.append((p, d))
        by_day = collections.defaultdict(list)
        for p, d in sorted(near, key=lambda item: item[0].utc):
            self.radar[parse.handle_for_utc(p.utc)].append(p)
            by_day[local_day(p.utc, off)].append({
                "time_utc": iso_utc(p.utc), "time_local": iso_local(p.utc, off), "track": p.track,
                "callsign": p.callsign, "type": p.aircraft_type, "registration": p.registration,
                "direction": p.direction, "airport": p.airport, "origin": p.origin, "destination": p.destination,
                "lat": p.lat, "lon": p.lon, "height_m": p.height_m, "altitude_m": p.altitude_m,
                "speed_ms": p.speed_ms, "distance_m": round(d), "slant_m": round(math.hypot(d, p.height_m or 0.0))})
        for day, rows in by_day.items():
            self._append(os.path.join(self.dir, "aircraft", f"{day}.csv"), AIRCRAFT_FIELDS, rows)
        self.loaded.add(chunk.handle)
        self._mark_saved(chunk.handle)

        for event in chunk.events:
            if event.monitor != mid or event.key in self.seen_events:
                continue
            self.seen_events.add(event.key)
            self.pending.append(event)
        chunk_end = chunk.start_utc + parse.WINDOW_S
        matched = self._match(lambda e: all(self.has(h) for h in match_handles(e))
                              or chunk_end >= e.lmax_time + MATCH_WINDOW_S + GIVE_UP_S)
        self._save_state()
        self._prune(chunk.handle)

        values = [lv.level for lv in levels]
        leq = 10 * math.log10(sum(10 ** (v / 10) for v in values) / len(values)) if values else None
        return {"handle": chunk.handle, "start": iso_local(chunk.start_utc, off), "seconds": len(values),
                "leq": leq, "max": max(values) if values else None, "events": matched,
                "aircraft": len({p.track for p, _ in near}), "radar_status": chunk.radar_status}

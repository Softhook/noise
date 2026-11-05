"""Write chunks to CSV files for one monitor, and match its events to aircraft.

Layout, under OUT/<site>/nmt<id>/:

    levels/YYYY-MM-DD.csv     one row per second: UTC, local time, level, flag
    aircraft/YYYY-MM-DD.csv   radar positions within --radius of the monitor
    events.csv                one row per noise event, with the aircraft that passed closest
    state.json                the last chunk saved, so a restart carries on without gaps
    raw/YYYY-MM-DD/*.txt.gz   the chunks as received, only with --keep-raw

Days are local (Europe/London) days. Times in the files are ISO 8601, UTC with a Z, and local
with its offset.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import gzip
import json
import math
import os

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
BUFFER_S = 20 * 60       # keep this much radar in memory for matching


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
            "track": p.track, "closest_time_local": iso_local(p.utc, event_offset(event)),
            "closest_distance_m": round(d), "closest_height_m": _round(p.height_m, 0),
            "closest_slant_m": round(slant), "lmax_after_closest_s": round(event.lmax_time - p.utc),
            "candidates": len(tracks)}


def event_offset(event):
    return getattr(event, "offset_s", 0)


class MonitorStore:
    def __init__(self, root, monitor, radius_m=3000.0, keep_raw=False):
        self.monitor = monitor
        self.dir = os.path.join(root, f"nmt{monitor['id']}")
        self.radius_m = radius_m
        self.keep_raw = keep_raw
        self.state_path = os.path.join(self.dir, "state.json")
        self.events_path = os.path.join(self.dir, "events.csv")
        os.makedirs(self.dir, exist_ok=True)
        self.state = self._load_state()
        self.seen_events = self._load_event_keys()
        self.buffer = collections.deque()

    # --- state ----------------------------------------------------------------------------

    def _load_state(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_state(self):
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

    def prime_buffer(self):
        """After a restart, reload recent nearby radar so the first events can still be matched."""
        folder = os.path.join(self.dir, "aircraft")
        try:
            latest = sorted(n for n in os.listdir(folder) if n.endswith(".csv"))[-2:]
        except OSError:
            return
        cutoff = None
        if self.last_handle is not None:
            cutoff = parse.utc_for_handle(self.last_handle) - BUFFER_S
        for name in latest:
            with open(os.path.join(folder, name), newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        t = dt.datetime.strptime(row["time_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                            tzinfo=dt.timezone.utc).timestamp()
                        if cutoff is not None and t < cutoff:
                            continue
                        self.buffer.append(parse.Position(
                            utc=t, track=row["track"], direction=row["direction"], airport=row["airport"],
                            aircraft_type=row["type"], callsign=row["callsign"], registration=row["registration"],
                            squawk="", lat=float(row["lat"]), lon=float(row["lon"]),
                            height_m=float(row["height_m"]) if row["height_m"] else None,
                            altitude_m=float(row["altitude_m"]) if row["altitude_m"] else None,
                            speed_ms=float(row["speed_ms"]) if row["speed_ms"] else None,
                            origin=row["origin"], destination=row["destination"]))
                    except (KeyError, ValueError):
                        continue

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

    def save(self, chunk, text=None):
        """Save one chunk and return a summary for the console, or None if it was saved before."""
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
        # Chunks normally arrive in order. If this one is from another period (a historical fetch
        # after following, say), the buffered radar is no use for matching, so start afresh.
        if self.buffer and not (chunk.start_utc - BUFFER_S <= self.buffer[-1].utc <= chunk.start_utc + parse.WINDOW_S):
            self.buffer.clear()
        by_day = collections.defaultdict(list)
        for p, d in sorted(near, key=lambda item: item[0].utc):
            self.buffer.append(p)
            by_day[local_day(p.utc, off)].append({
                "time_utc": iso_utc(p.utc), "time_local": iso_local(p.utc, off), "track": p.track,
                "callsign": p.callsign, "type": p.aircraft_type, "registration": p.registration,
                "direction": p.direction, "airport": p.airport, "origin": p.origin, "destination": p.destination,
                "lat": p.lat, "lon": p.lon, "height_m": p.height_m, "altitude_m": p.altitude_m,
                "speed_ms": p.speed_ms, "distance_m": round(d), "slant_m": round(math.hypot(d, p.height_m or 0.0))})
        for day, rows in by_day.items():
            self._append(os.path.join(self.dir, "aircraft", f"{day}.csv"), AIRCRAFT_FIELDS, rows)
        while self.buffer and self.buffer[0].utc < chunk.start_utc - BUFFER_S:
            self.buffer.popleft()

        new_events = []
        for event in chunk.events:
            if event.monitor != mid or event.key in self.seen_events:
                continue
            self.seen_events.add(event.key)
            event.offset_s = off
            row = {"start_utc": iso_utc(event.start), "start_local": iso_local(event.start, off),
                   "lmax_time_local": iso_local(event.lmax_time, off), "end_local": iso_local(event.end, off),
                   "duration_s": event.duration, "lmax_db": event.lmax, "sel_db": event.sel, "leq_db": event.leq,
                   "epnl_db": event.epnl, "event_class": event.event_class}
            row.update(match_event(event, self.buffer, self.monitor))
            new_events.append(row)
        self._append(self.events_path, EVENT_FIELDS, new_events)

        if self.keep_raw and text is not None:
            day = local_day(chunk.start_utc, off)
            raw_dir = os.path.join(self.dir, "raw", day)
            os.makedirs(raw_dir, exist_ok=True)
            with gzip.open(os.path.join(raw_dir, f"{chunk.handle}.txt.gz"), "wt") as f:
                f.write(text)

        self._mark_saved(chunk.handle)
        self.state["monitor"] = self.monitor
        self._save_state()

        values = [lv.level for lv in levels]
        leq = 10 * math.log10(sum(10 ** (v / 10) for v in values) / len(values)) if values else None
        return {"handle": chunk.handle, "start": iso_local(chunk.start_utc, off), "seconds": len(values),
                "leq": leq, "max": max(values) if values else None, "events": new_events,
                "aircraft": len({p.track for p, _ in near}), "radar_status": chunk.radar_status}

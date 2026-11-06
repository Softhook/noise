#!/usr/bin/env python3
"""Get London City's flights near NMT6 from OpenSky, and compare them with saved WebTrak data.

  python3 tools/opensky/nmt6_flights.py --from 2026-11-05T08:00Z --to 2026-11-05T11:00Z

For each EGLC arrival and departure in the period, OpenSky's track for that flight gives its closest
approach to NMT6 (St Pauls Church, Thamesmead). Those within --radius are written to
tools/opensky/data/nmt6-<from>.csv, then lined up against WebTrak's radar tracks and NMT6 events
for the same period (tools/webtrak/data/lcy/nmt106).

Credentials come from OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET, or from
~/.config/opensky/credentials.json ({"clientId": ..., "clientSecret": ...}). Never put them in
the repository. Standard library only.

Limits worth knowing:
- Only flights to or from EGLC are found: OpenSky can't search by area for past times.
- OpenSky's tracks are waypoints, not every position, so the closest approach is interpolated
  between points that may be tens of seconds apart.
- OpenSky's track heights are barometric (pressure altitude, 1013.25 hPa) and come in steps of
  1000 ft (304.8 m), so they are no use for heights near NMT6. Use WebTrak's or our own logger's.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WEBTRAK_DIR = os.path.join(HERE, "..", "webtrak", "data", "lcy", "nmt106")
OUT_DIR = os.path.join(HERE, "data")
NMT6 = (51.50535, 0.11075)  # From WebTrak's monitor list
API = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
CREDENTIALS = os.path.expanduser("~/.config/opensky/credentials.json")
USER_AGENT = "thamesmead-noise-survey/0.1 (personal, non-commercial noise research)"
PAD_S = 20 * 60  # Flights landing or taking off this long either side of the period may pass NMT6 inside it
MATCH_S = 90  # Closest approaches this close in time are taken to be the same flight


def parse_time(text):
    text = text.strip().replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(text)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def credentials():
    cid, secret = os.environ.get("OPENSKY_CLIENT_ID"), os.environ.get("OPENSKY_CLIENT_SECRET")
    if cid and secret:
        return cid, secret
    try:
        with open(CREDENTIALS) as f:
            data = json.load(f)
        return data["clientId"], data["clientSecret"]
    except (OSError, ValueError, KeyError):
        sys.exit(f"No OpenSky credentials: set OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET or write {CREDENTIALS}")


class OpenSky:
    def __init__(self, client_id, secret):
        self.client_id, self.secret = client_id, secret
        self.token, self.expires = None, 0.0

    def _token(self):
        if self.token and time.time() < self.expires - 60:
            return self.token
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.client_id,
                                       "client_secret": self.secret}).encode()
        req = urllib.request.Request(TOKEN_URL, data=body, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        self.token, self.expires = data["access_token"], time.time() + data.get("expires_in", 1800)
        return self.token

    def get(self, path, **params):
        """JSON from the API, or None when OpenSky has nothing (404)."""
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(4):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._token()}",
                                                       "User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    remaining = r.headers.get("X-Rate-Limit-Remaining")
                    if remaining is not None:
                        self.credits_left = remaining
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code == 429:
                    wait = int(e.headers.get("X-Rate-Limit-Retry-After-Seconds", "60"))
                    sys.exit(f"OpenSky's rate limit is used up; try again in {wait // 60} minutes.")
                if e.code >= 500 and attempt < 3:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise
        return None


def local_xy(lat, lon):
    """Metres east and north of NMT6; flat-earth is fine over a few kilometres."""
    x = math.radians(lon - NMT6[1]) * 6371000 * math.cos(math.radians(NMT6[0]))
    y = math.radians(lat - NMT6[0]) * 6371000
    return x, y


def closest_approach(points):
    """(time, ground distance m, height m) of the closest point, interpolated between neighbours.

    points: [(t, lat, lon, height or None)] in time order.
    """
    best = None
    for i in range(len(points)):
        t0, lat0, lon0, h0 = points[i]
        x0, y0 = local_xy(lat0, lon0)
        candidates = [(0.0, x0, y0)]
        if i + 1 < len(points):
            t1, lat1, lon1, h1 = points[i + 1]
            x1, y1 = local_xy(lat1, lon1)
            dx, dy = x1 - x0, y1 - y0
            if dx or dy:
                f = max(0.0, min(1.0, -(x0 * dx + y0 * dy) / (dx * dx + dy * dy)))
                candidates.append((f, x0 + f * dx, y0 + f * dy))
        for f, x, y in candidates:
            d = math.hypot(x, y)
            if best is None or d < best[1]:
                if f and i + 1 < len(points):
                    t = t0 + f * (t1 - t0)
                    h = h0 + f * (h1 - h0) if h0 is not None and h1 is not None else (h0 if f < 0.5 else h1)
                else:
                    t, h = t0, h0
                best = (t, d, h)
    return best


def opensky_passes(api, begin, end, radius):
    flights = []
    for kind in ("arrival", "departure"):
        found = api.get(f"/flights/{kind}", airport="EGLC", begin=int(begin - PAD_S), end=int(end + PAD_S)) or []
        for f in found:
            f["kind"] = kind
        flights += found
        print(f"OpenSky: {len(found)} EGLC {kind}s", file=sys.stderr)
    passes = []
    for f in flights:
        mid = (f["firstSeen"] + f["lastSeen"]) // 2
        track = api.get("/tracks/all", icao24=f["icao24"], time=mid)
        path = [(p[0], p[1], p[2], p[3]) for p in (track or {}).get("path", []) if p[1] is not None]
        if len(path) < 2:
            print(f"  no track for {f['icao24']} {(f.get('callsign') or '').strip()}", file=sys.stderr)
            continue
        t, d, h = closest_approach(path)
        if d > radius or not begin <= t <= end:
            continue
        gaps = [b[0] - a[0] for a, b in zip(path, path[1:])]
        near = min(range(len(path)), key=lambda i: abs(path[i][0] - t))
        passes.append({
            "closest_utc": iso(t), "t": t,
            "callsign": (f.get("callsign") or "").strip(), "icao24": f["icao24"], "direction": f["kind"][0].upper(),
            "from": f.get("estDepartureAirport") or "", "to": f.get("estArrivalAirport") or "",
            "distance_m": round(d), "baro_alt_m": round(h) if h is not None else "",
            "point_gap_s": round(max(gaps[max(0, near - 1):near + 1] or [0])),
        })
    return sorted(passes, key=lambda p: p["t"])


def webtrak_passes(begin, end, radius):
    """WebTrak's closest point per radar track, from its saved aircraft files."""
    tracks = {}
    day = dt.datetime.fromtimestamp(begin, dt.timezone.utc).date()
    while day <= dt.datetime.fromtimestamp(end, dt.timezone.utc).date():
        path = os.path.join(WEBTRAK_DIR, "aircraft", f"{day}.csv")
        if os.path.exists(path):
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    t = parse_time(row["time_utc"])
                    if not begin <= t <= end or not row["distance_m"]:
                        continue
                    d = float(row["distance_m"])
                    best = tracks.get(row["track"])
                    if d <= radius and (best is None or d < best["distance_m"]):
                        tracks[row["track"]] = {"t": t, "closest_utc": row["time_utc"], "callsign": row["callsign"],
                                                "type": row["type"], "direction": row["direction"],
                                                "airport": row["airport"], "distance_m": d,
                                                "height_m": row["height_m"], "altitude_m": row["altitude_m"]}
        day += dt.timedelta(days=1)
    return sorted(tracks.values(), key=lambda p: p["t"])


def webtrak_events(begin, end):
    path = os.path.join(WEBTRAK_DIR, "events.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if begin <= parse_time(r["lmax_time_local"]) <= end]
    for r in rows:
        r["t"] = parse_time(r["lmax_time_local"])
    return rows


def pair(a, b, within):
    """Greedy one-to-one matching on time, closest first. Returns [(a or None, b or None)]."""
    options = sorted((abs(x["t"] - y["t"]), i, j) for i, x in enumerate(a) for j, y in enumerate(b)
                     if abs(x["t"] - y["t"]) <= within)
    used_a, used_b, pairs = set(), set(), []
    for _, i, j in options:
        if i not in used_a and j not in used_b:
            used_a.add(i), used_b.add(j)
            pairs.append((a[i], b[j]))
    pairs += [(a[i], None) for i in range(len(a)) if i not in used_a]
    pairs += [(None, b[j]) for j in range(len(b)) if j not in used_b]
    return sorted(pairs, key=lambda p: (p[0] or p[1])["t"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--from", dest="begin", required=True, help="UTC, e.g. 2026-11-05T08:00Z")
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--radius", type=float, default=3000, help="metres from NMT6 (default 3000, as WebTrak)")
    args = parser.parse_args()
    begin, end = parse_time(args.begin), parse_time(args.end)

    api = OpenSky(*credentials())
    passes = opensky_passes(api, begin, end, args.radius)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"nmt6-{iso(begin)[:16].replace(':', '')}.csv")
    fields = ["closest_utc", "callsign", "icao24", "direction", "from", "to", "distance_m", "baro_alt_m", "point_gap_s"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(passes)
    print(f"{len(passes)} OpenSky flights within {args.radius:.0f} m of NMT6 -> {os.path.relpath(out)}")
    if hasattr(api, "credits_left"):
        print(f"OpenSky credits left today: {api.credits_left}")

    web = [w for w in webtrak_passes(begin, end, args.radius) if w["airport"] == "LCY"]
    events = webtrak_events(begin, end)
    print(f"\nWebTrak: {len(web)} LCY tracks within {args.radius:.0f} m, {len(events)} NMT6 events\n")
    print(f"{'closest (UTC)':20} {'WebTrak':10} {'type':5} {'dir':3} {'dist':>5} {'hgt':>5} | "
          f"{'OpenSky':9} {'dir':3} {'dist':>5} {'baro':>5} {'dt':>4} {'gap':>4} | NMT6 LAmax")
    pairs = pair(web, passes, MATCH_S)
    both = 0
    for w, o in pairs:
        t = (w or o)["t"]
        ev = min(events, key=lambda e: abs(e["t"] - t), default=None)
        ev_text = f"{float(ev['lmax_db']):.1f} dB ({ev['callsign'] or '-'})" if ev and abs(ev["t"] - t) <= 60 else ""
        left = (f"{w['callsign']:10} {w['type']:5} {w['direction']:3} {w['distance_m']:5.0f} "
                f"{float(w['height_m'] or 'nan'):5.0f}") if w else " " * 32
        offset = f"{o['t'] - w['t']:+.0f}" if w and o else ""
        right = (f"{o['callsign']:9} {o['direction']:3} {o['distance_m']:5} {o['baro_alt_m']:>5} "
                 f"{offset:>4} {o['point_gap_s']:>4}") if o else " " * 35
        both += bool(w and o)
        print(f"{iso(t):20} {left} | {right} | {ev_text}")
    print(f"\nIn both: {both}. WebTrak only: {sum(1 for w, o in pairs if not o)}. "
          f"OpenSky only: {sum(1 for w, o in pairs if not w)}.")
    print("dist = closest ground distance (m); hgt = WebTrak height above aerodrome (m); baro = OpenSky "
          "pressure altitude (m); dt = OpenSky minus WebTrak closest time (s); gap = seconds between OpenSky points there.")


if __name__ == "__main__":
    main()

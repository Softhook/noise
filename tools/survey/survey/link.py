"""Link flights from different sources that are the same aircraft movement into passes.

Evidence, strongest first (ARCHITECTURE.md, Link):
1. `registration`: the same registration, with overlapping times;
2. `track`: no registration to compare, but the closest approaches to the same receptor came
   within TRACK_TIME_S of each other, and the aircraft were within TRACK_DISTANCE_M of each other
   then, and within TRACK_HEIGHT_M in height when both have one.

Flights whose registrations differ are never linked, and two flights from the same source are
never in one pass. A pass id is stable across rebuilds: its closest approach to the first receptor,
to the minute, and its registration, or a source id when there's none.
"""

from __future__ import annotations

import datetime as dt
import math

from .common import parse_time

OVERLAP_SLACK_S = 120
TRACK_TIME_S = 30
TRACK_DISTANCE_M = 500
TRACK_HEIGHT_M = 200


def _overlap(a, b):
    return parse_time(a["first_utc"]) - OVERLAP_SLACK_S <= parse_time(b["last_utc"]) and \
        parse_time(b["first_utc"]) - OVERLAP_SLACK_S <= parse_time(a["last_utc"])


def _position_at(points, t):
    """(lat, lon, height) interpolated at time t from a time-ordered track."""
    for a, b in zip(points, points[1:]):
        if a["t"] <= t <= b["t"]:
            f = 0 if b["t"] == a["t"] else (t - a["t"]) / (b["t"] - a["t"])
            h = None if a["height_m"] is None or b["height_m"] is None else a["height_m"] + f * (b["height_m"] - a["height_m"])
            return a["lat"] + f * (b["lat"] - a["lat"]), a["lon"] + f * (b["lon"] - a["lon"]), h
    p = min(points, key=lambda p: abs(p["t"] - t))
    return p["lat"], p["lon"], p["height_m"]


def _apart_m(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111195, (a[1] - b[1]) * 111195 * math.cos(lat))


def link(flights, tracks, approaches, first_receptor):
    """Rows for the passes table. tracks: {(source, source_id): [position dicts, time-ordered]};
    approaches: {(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)}."""
    keys = [(f["source"], f["source_id"]) for f in flights]
    by_key = dict(zip(keys, flights))
    parent = {k: k for k in keys}
    members = {k: [k] for k in keys}  # Each pass's flights, kept on its root
    evidence = {}

    def root(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def join(a, b, why):
        ra, rb = root(a), root(b)
        if ra == rb or {k[0] for k in members[ra]} & {k[0] for k in members[rb]}:
            return
        if len({by_key[k]["registration"] for k in members[ra] + members[rb]} - {""}) > 1:
            return
        parent[rb] = ra
        members[ra] += members.pop(rb)
        evidence[a] = evidence.get(a) or why
        evidence[b] = evidence.get(b) or why

    ordered = sorted(flights, key=lambda f: f["first_utc"])
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b["first_utc"] > a["last_utc"] and parse_time(b["first_utc"]) - parse_time(a["last_utc"]) > OVERLAP_SLACK_S:
                break
            if a["source"] == b["source"] or not _overlap(a, b):
                continue
            ka, kb = (a["source"], a["source_id"]), (b["source"], b["source_id"])
            if a["registration"] and a["registration"] == b["registration"]:
                join(ka, kb, "registration")
            elif not (a["registration"] and b["registration"]):
                ca, cb = approaches.get((*ka, first_receptor)), approaches.get((*kb, first_receptor))
                if not ca or not cb or abs(ca[0] - cb[0]) > TRACK_TIME_S:
                    continue
                t = (ca[0] + cb[0]) / 2
                pa, pb = _position_at(tracks[ka], t), _position_at(tracks[kb], t)
                if _apart_m(pa, pb) > TRACK_DISTANCE_M:
                    continue
                if pa[2] is not None and pb[2] is not None and abs(pa[2] - pb[2]) > TRACK_HEIGHT_M:
                    continue
                join(ka, kb, "track")

    rows, used = [], {}
    for group in sorted(members.values(), key=lambda g: sorted(g)):
        times = [approaches[(*k, first_receptor)][0] for k in group if (*k, first_receptor) in approaches]
        t = min(times) if times else parse_time(min(by_key[k]["first_utc"] for k in group))
        regs = sorted({by_key[k]["registration"] for k in group} - {""})
        name = regs[0] if regs else sorted(group)[0][1]
        pass_id = dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%dT%H%M") + "-" + name
        # Two passes can't share an id: the same airframe twice in a minute, in flights that didn't link
        used[pass_id] = used.get(pass_id, 0) + 1
        if used[pass_id] > 1:
            pass_id += f"-{used[pass_id]}"
        for k in sorted(group):
            rows.append({"pass_id": pass_id, "source": k[0], "source_id": k[1],
                         "evidence": evidence.get(k, "") if len(group) > 1 else ""})
    return sorted(rows, key=lambda r: (r["pass_id"], r["source"]))

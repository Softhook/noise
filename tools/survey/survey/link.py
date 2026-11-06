"""Link flights from different sources that are the same aircraft movement into passes.

Evidence, strongest first (ARCHITECTURE.md, Link):
1. `registration`: the same registration, with overlapping times, and tracks that agree: where
   both have positions at the same time, their median separation is under REGISTRATION_TRACK_M,
   so a registration sent by mistake doesn't join two different aircraft;
2. `track`: no registration to compare, but the closest approaches to the pass receptor came
   within TRACK_TIME_S of each other, and the aircraft were within TRACK_DISTANCE_M of each other
   then, and within TRACK_HEIGHT_M in height when both have one.

Every candidate pair is found first, and then joined best first: registration links before track
links, and closer tracks before further ones. So a flight joins the best match on offer, not the
first one found. Flights whose registrations differ are never linked, and two flights from the
same source are never in one pass.

A pass id is stable across rebuilds: the time of its closest approach to the pass receptor, to the
minute, and its registration, or a source id when there's none. Both come from the pass's flight
in the highest-ranked source (SOURCE_RANK): ADS-B sources first, WebTrak last, since WebTrak must be
removable (ARCHITECTURE.md). Adding or removing WebTrak, or any source ranked below the ones a pass
already has, leaves its id unchanged.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
import statistics

from .common import parse_time

OVERLAP_SLACK_S = 120
TRACK_TIME_S = 30
TRACK_DISTANCE_M = 500
TRACK_HEIGHT_M = 200
# Two flights with the same registration are one aircraft only if their tracks agree this well.
# Generous, as clocks may differ by a few seconds and radar positions are coarse.
REGISTRATION_TRACK_M = 2000
MAX_INTERPOLATE_S = 30  # A track is only interpolated between positions this close in time

# Which source's flight dates and names a pass. Sources not listed rank between these and WebTrak.
SOURCE_RANK = ("adsb", "adsblol", "opensky")
LAST_SOURCES = ("webtrak",)


def source_rank(source):
    if source in SOURCE_RANK:
        return (0, SOURCE_RANK.index(source), source)
    if source in LAST_SOURCES:
        return (2, LAST_SOURCES.index(source), source)
    return (1, 0, source)


def _overlap(a, b):
    return parse_time(a["first_utc"]) - OVERLAP_SLACK_S <= parse_time(b["last_utc"]) and \
        parse_time(b["first_utc"]) - OVERLAP_SLACK_S <= parse_time(a["last_utc"])


def _position_at(points, t, times=None):
    """(lat, lon, height) interpolated at time t from a time-ordered track; the nearest position
    outside it."""
    times = times or [p["t"] for p in points]
    i = bisect.bisect_left(times, t)
    if i == 0 or i == len(points):
        p = points[0] if i == 0 else points[-1]
        return p["lat"], p["lon"], p["height_m"]
    a, b = points[i - 1], points[i]
    f = 0 if b["t"] == a["t"] else (t - a["t"]) / (b["t"] - a["t"])
    h = None if a["height_m"] is None or b["height_m"] is None else a["height_m"] + f * (b["height_m"] - a["height_m"])
    return a["lat"] + f * (b["lat"] - a["lat"]), a["lon"] + f * (b["lon"] - a["lon"]), h


def _apart_m(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111195, (a[1] - b[1]) * 111195 * math.cos(lat))


def separation_m(ta, tb):
    """Median distance between two time-ordered tracks, at the times both have positions, or None
    when there are no such times. Each position of the sparser track is compared with the other
    track interpolated at its time, but never across a gap of more than MAX_INTERPOLATE_S: OpenSky's
    tracks have holes where an aircraft left its box and came back, and a line across the hole
    isn't where the aircraft was."""
    if len(ta) > len(tb):
        ta, tb = tb, ta
    times_b = [p["t"] for p in tb]
    apart = []
    for p in ta:
        i = bisect.bisect_left(times_b, p["t"])
        if i < len(tb) and times_b[i] == p["t"]:
            q = tb[i]
            apart.append(_apart_m((p["lat"], p["lon"]), (q["lat"], q["lon"])))
        elif 0 < i < len(tb) and times_b[i] - times_b[i - 1] <= MAX_INTERPOLATE_S:
            apart.append(_apart_m((p["lat"], p["lon"]), _position_at(tb, p["t"], times_b)))
    return statistics.median(apart) if apart else None


def link(flights, tracks, approaches, receptor):
    """Rows for the passes table. tracks: {(source, source_id): [position dicts, time-ordered]};
    approaches: {(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)};
    receptor: the pass receptor (manifest.load's pass_receptor)."""
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

    # Every pair that could be linked, with how strong the evidence is and how well the tracks agree
    candidates = []
    ordered = sorted(flights, key=lambda f: f["first_utc"])
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b["first_utc"] > a["last_utc"] and parse_time(b["first_utc"]) - parse_time(a["last_utc"]) > OVERLAP_SLACK_S:
                break
            if a["source"] == b["source"] or not _overlap(a, b):
                continue
            ka, kb = (a["source"], a["source_id"]), (b["source"], b["source_id"])
            if a["registration"] and a["registration"] == b["registration"]:
                apart = separation_m(tracks[ka], tracks[kb]) if ka in tracks and kb in tracks else None
                if apart is not None and apart > REGISTRATION_TRACK_M:
                    continue  # The same registration on two different aircraft
                candidates.append((0, apart or 0.0, ka, kb, "registration"))
            elif not (a["registration"] and b["registration"]):
                ca, cb = approaches.get((*ka, receptor)), approaches.get((*kb, receptor))
                if not ca or not cb or abs(ca[0] - cb[0]) > TRACK_TIME_S:
                    continue
                t = (ca[0] + cb[0]) / 2
                pa, pb = _position_at(tracks[ka], t), _position_at(tracks[kb], t)
                apart = _apart_m(pa, pb)
                if apart > TRACK_DISTANCE_M:
                    continue
                if pa[2] is not None and pb[2] is not None and abs(pa[2] - pb[2]) > TRACK_HEIGHT_M:
                    continue
                candidates.append((1, apart, ka, kb, "track"))
    for _, _, ka, kb, why in sorted(candidates):
        join(ka, kb, why)

    rows, used = [], {}
    groups = sorted(members.values(), key=lambda g: min((source_rank(k[0]), k[1]) for k in g))
    for group in groups:
        lead = sorted(group, key=lambda k: (source_rank(k[0]), (*k, receptor) not in approaches, k[1]))
        dated = [k for k in lead if (*k, receptor) in approaches]
        t = approaches[(*dated[0], receptor)][0] if dated else parse_time(by_key[lead[0]]["first_utc"])
        regs = sorted({by_key[k]["registration"] for k in group} - {""})
        name = regs[0] if regs else lead[0][1]
        pass_id = dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%dT%H%M") + "-" + name
        # Two passes can't share an id: the same airframe twice in a minute, in flights that didn't link
        used[pass_id] = used.get(pass_id, 0) + 1
        if used[pass_id] > 1:
            pass_id += f"-{used[pass_id]}"
        for k in sorted(group):
            rows.append({"pass_id": pass_id, "source": k[0], "source_id": k[1],
                         "evidence": evidence.get(k, "") if len(group) > 1 else ""})
    return sorted(rows, key=lambda r: (r["pass_id"], r["source"]))

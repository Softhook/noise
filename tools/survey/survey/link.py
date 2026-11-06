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
import statistics

from .common import parse_time
from .geometry import apart_m, position_at

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


def ranked(sources):
    """Sources in rank order: the order the survey app lists them in, everywhere."""
    return sorted(sources, key=source_rank)


def _overlap(a, b):
    return parse_time(a["first_utc"]) - OVERLAP_SLACK_S <= parse_time(b["last_utc"]) and \
        parse_time(b["first_utc"]) - OVERLAP_SLACK_S <= parse_time(a["last_utc"])


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
            apart.append(apart_m((p["lat"], p["lon"]), (q["lat"], q["lon"])))
        elif 0 < i < len(tb) and times_b[i] - times_b[i - 1] <= MAX_INTERPOLATE_S:
            apart.append(apart_m((p["lat"], p["lon"]), position_at(tb, p["t"], times_b)))
    return statistics.median(apart) if apart else None


def _evidence(a, b, tracks, approaches, receptor):
    """(strength, apart_m, kind) if flights a and b may be the same aircraft movement, else None.
    Lower strength is stronger evidence."""
    ka, kb = (a["source"], a["source_id"]), (b["source"], b["source_id"])
    if a["registration"] and a["registration"] == b["registration"]:
        apart = separation_m(tracks[ka], tracks[kb]) if ka in tracks and kb in tracks else None
        if apart is not None and apart > REGISTRATION_TRACK_M:
            return None  # The same registration on two different aircraft
        return 0, apart or 0.0, "registration"
    if a["registration"] and b["registration"]:
        return None  # Different registrations: never the same aircraft
    ca, cb = approaches.get((*ka, receptor)), approaches.get((*kb, receptor))
    if not ca or not cb or abs(ca[0] - cb[0]) > TRACK_TIME_S:
        return None
    t = (ca[0] + cb[0]) / 2
    pa, pb = position_at(tracks[ka], t), position_at(tracks[kb], t)
    apart = apart_m(pa, pb)
    if apart > TRACK_DISTANCE_M:
        return None
    if pa[2] is not None and pb[2] is not None and abs(pa[2] - pb[2]) > TRACK_HEIGHT_M:
        return None
    return 1, apart, "track"


def candidates(flights, tracks, approaches, receptor):
    """Every pair of flights that could be linked, best first: [(strength, apart_m, key_a, key_b, kind)]."""
    found = []
    ordered = sorted(flights, key=lambda f: f["first_utc"])
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b["first_utc"] > a["last_utc"] and parse_time(b["first_utc"]) - parse_time(a["last_utc"]) > OVERLAP_SLACK_S:
                break
            if a["source"] == b["source"] or not _overlap(a, b):
                continue
            got = _evidence(a, b, tracks, approaches, receptor)
            if got:
                found.append((got[0], got[1], (a["source"], a["source_id"]), (b["source"], b["source_id"]), got[2]))
    return sorted(found)


class _Groups:
    """Flights joined into passes (union-find), refusing any join that would put two flights from
    one source, or two registrations, in one pass."""

    def __init__(self, flights):
        self.flight = {(f["source"], f["source_id"]): f for f in flights}
        self.parent = {k: k for k in self.flight}
        self.members = {k: [k] for k in self.flight}  # Each pass's flights, kept on its root
        self.evidence = {}

    def root(self, k):
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def join(self, a, b, why):
        ra, rb = self.root(a), self.root(b)
        if ra == rb or {k[0] for k in self.members[ra]} & {k[0] for k in self.members[rb]}:
            return
        if len({self.flight[k]["registration"] for k in self.members[ra] + self.members[rb]} - {""}) > 1:
            return
        self.parent[rb] = ra
        self.members[ra] += self.members.pop(rb)
        self.evidence[a] = self.evidence.get(a) or why
        self.evidence[b] = self.evidence.get(b) or why


def _pass_name(group, flight, approaches, receptor):
    """A pass's id before de-duplication: its lead flight's closest approach to the receptor, to the
    minute (or its first time, without one), and its registration (or the lead's source id)."""
    lead = sorted(group, key=lambda k: (source_rank(k[0]), (*k, receptor) not in approaches, k[1]))
    dated = [k for k in lead if (*k, receptor) in approaches]
    t = approaches[(*dated[0], receptor)][0] if dated else parse_time(flight[lead[0]]["first_utc"])
    regs = sorted({flight[k]["registration"] for k in group} - {""})
    name = regs[0] if regs else lead[0][1]
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%dT%H%M") + "-" + name


def link(flights, tracks, approaches, receptor):
    """Rows for the passes table. tracks: {(source, source_id): [position dicts, time-ordered]};
    approaches: {(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)};
    receptor: the pass receptor (manifest.load's pass_receptor)."""
    groups = _Groups(flights)
    for _, _, ka, kb, why in candidates(flights, tracks, approaches, receptor):
        groups.join(ka, kb, why)

    rows, used = [], {}
    for group in sorted(groups.members.values(), key=lambda g: min((source_rank(k[0]), k[1]) for k in g)):
        pass_id = _pass_name(group, groups.flight, approaches, receptor)
        # Two passes can't share an id: the same airframe twice in a minute, in flights that didn't link
        used[pass_id] = used.get(pass_id, 0) + 1
        if used[pass_id] > 1:
            pass_id += f"-{used[pass_id]}"
        for k in sorted(group):
            rows.append({"pass_id": pass_id, "source": k[0], "source_id": k[1],
                         "evidence": groups.evidence.get(k, "") if len(group) > 1 else ""})
    return sorted(rows, key=lambda r: (r["pass_id"], r["source"]))

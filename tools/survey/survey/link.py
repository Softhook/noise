"""Link flights from different sources that are the same aircraft movement into passes.

Evidence, strongest first (ARCHITECTURE.md, Link). Two tracks are compared only where both have
positions at the same time (compare()), and only with at least MIN_COMPARED such times:
1. `registration`: the same registration, with overlapping times, and tracks that agree: their
   median separation is under REGISTRATION_TRACK_M, so a registration sent by mistake doesn't
   join two different aircraft;
   `registration, tracks not compared` (UNCHECKED): the same registration, with overlapping
   times, but too few times at which both have positions to compare the tracks;
2. `track`: no registration to compare, but the tracks agree closely: a median separation under
   TRACK_DISTANCE_M, and a median height difference under TRACK_HEIGHT_M when both have heights.
   This doesn't depend on any receptor, so a pass far from every receptor links as well as one
   overhead, and a track cut off at the edge of a source's area still compares where it overlaps.

Every candidate pair is found first, and then joined best first: registration links before track
links, and closer tracks before further ones. So a flight joins the best match on offer, not the
first one found. A registration link whose tracks couldn't be compared ranks between the two.
Flights whose registrations differ are never linked, and two flights from the
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
from .geometry import MAX_INTERPOLATE_S, apart_m, position_at

OVERLAP_SLACK_S = 120
# Two tracks without a registration to compare are one aircraft if they agree this well. Clocks
# may differ by a few seconds: 3 s at 70 m/s is 210 m.
TRACK_DISTANCE_M = 500
TRACK_HEIGHT_M = 200
# Two flights with the same registration are one aircraft only if their tracks agree this well.
# Generous, as clocks may differ by a few seconds and radar positions are coarse.
REGISTRATION_TRACK_M = 2000
# Tracks are compared only at this many times or more: one or two positions say little. Three
# radar positions are about 8 s together, as when OpenSky catches an aircraft just inside its box
MIN_COMPARED = 3
# The evidence for a registration link whose tracks couldn't be compared: they overlap in time
# only within OVERLAP_SLACK_S, or have too few positions at the same times
UNCHECKED = "registration, tracks not compared"

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


def compare(ta, tb):
    """[(ground_m, height_diff_m or None)] between two tracks, at the times both have positions.
    Each position of the sparser track is compared with the other track interpolated at its time,
    but never across a hole of more than MAX_INTERPOLATE_S: a line across the hole isn't where the
    aircraft was."""
    if len(ta) > len(tb):
        ta, tb = tb, ta
    times_b = [p[0] for p in tb]
    out = []
    for p in ta:
        i = bisect.bisect_left(times_b, p[0])
        if i < len(tb) and times_b[i] == p[0]:
            q = tb[i][1:4]
        elif 0 < i < len(tb) and times_b[i] - times_b[i - 1] <= MAX_INTERPOLATE_S:
            q = position_at(tb, p[0], times_b)
        else:
            continue
        dh = None if p[3] is None or q[2] is None else abs(p[3] - q[2])
        out.append((apart_m(p[1:3], q), dh))
    return out


def separation_m(ta, tb):
    """Median distance between two tracks at the times both have positions, or None when there are
    fewer than MIN_COMPARED such times."""
    got = compare(ta, tb)
    return statistics.median(g for g, _ in got) if len(got) >= MIN_COMPARED else None


def _evidence(a, b, tracks):
    """(strength, apart_m, kind) if flights a and b may be the same aircraft movement, else None.
    Lower strength is stronger evidence."""
    ta, tb = tracks.get((a["source"], a["source_id"])), tracks.get((b["source"], b["source_id"]))
    got = compare(ta, tb) if ta and tb else []
    if len(got) < MIN_COMPARED:
        got = None
    if a["registration"] and a["registration"] == b["registration"]:
        if got is None:
            # Too few times at which both have positions, so the tracks couldn't be checked:
            # weaker than a registration whose tracks agree, though still stronger than tracks alone
            return 1, 0.0, UNCHECKED
        apart = statistics.median(g for g, _ in got)
        if apart > REGISTRATION_TRACK_M:
            return None  # The same registration on two different aircraft
        return 0, apart, "registration"
    if (a["registration"] and b["registration"]) or got is None:
        return None  # Different registrations are never the same aircraft; nor tracks never compared
    apart = statistics.median(g for g, _ in got)
    heights = [dh for _, dh in got if dh is not None]
    if apart > TRACK_DISTANCE_M or (heights and statistics.median(heights) > TRACK_HEIGHT_M):
        return None
    return 2, apart, "track"


def candidates(flights, tracks):
    """Every pair of flights that could be linked, best first: [(strength, apart_m, key_a, key_b, kind)]."""
    found = []
    timed = sorted(((parse_time(f["first_utc"]), parse_time(f["last_utc"]), f) for f in flights),
                   key=lambda x: x[0])
    for i, (a0, a1, a) in enumerate(timed):
        for b0, b1, b in timed[i + 1:]:
            if b0 - a1 > OVERLAP_SLACK_S:
                break  # Sorted by first time, so no later flight overlaps a either
            if a["source"] == b["source"] or b1 < a0 - OVERLAP_SLACK_S:
                continue
            if a["registration"] and b["registration"] and a["registration"] != b["registration"]:
                continue  # Never the same aircraft: don't compare their tracks
            got = _evidence(a, b, tracks)
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
    """Rows for the passes table. tracks: {(source, source_id): track (geometry.py)};
    approaches: {(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)};
    receptor: the pass receptor (manifest.load's pass_receptor), which dates and names passes."""
    groups = _Groups(flights)
    for _, _, ka, kb, why in candidates(flights, tracks):
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

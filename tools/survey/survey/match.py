"""Match each noise event at a receptor to the pass that made it (ARCHITECTURE.md, Match).

For each pass near an event in time, the sound's predicted arrival at the receptor: where its track
came closest to the microphone in three dimensions (geometry.closest_slant), plus the time sound
takes to cover that distance. The track is the pass's flight in the highest-ranked source
(common.source_rank) whose closest point isn't at an edge of its data, so the ADS-B sources' before
WebTrak's, and a match never depends on WebTrak's radar when an ADS-B track is there.

The steps, for each noise source's events at a receptor:

1. **Clock offset.** The noise source's clock may be out against the tracks'. For each UTC day,
   every LAmax is compared with every clean pass's arrival (within MAX_SLANT_M, not at an edge, with
   heights) up to SEARCH_S either side. True matches pile up at one offset and chance ones spread
   out, so the CLOCK_BIN_S that holds the most of them is the day's offset, if it holds at least
   CLOCK_MIN_PAIRS and CLOCK_MIN_SHARE of the day's events. Otherwise it's not established, and 0
   is used. The window below is centred on it, so a clock a minute out still matches.
2. **Candidates:** the passes whose predicted arrival, moved by the day's offset, is within
   WINDOW_S of the event's LAmax.
3. **The match:** of the candidates within MAX_SLANT_M, the one predicted loudest: the closest,
   since sound falls off 6 dB each time the distance doubles. Each pass makes at most one event of
   a source at a receptor, so when two events want one pass it goes to the event closer in time,
   and the other takes its next candidate. Every pair is ranked first and then taken best first,
   as link does, so the result doesn't depend on the order of the events. A pass further than
   MAX_SLANT_M is never matched: at the garden, the Fusion triggers on buses and dogs too, and one
   of those near a high or distant pass isn't its sound.
4. **Others:** the other candidates predicted within CONTRIBUTE_DB of the match may have added to
   the level, such as a helicopter under an LCY departure. A pass 10 dB quieter adds under half a
   decibel. Every candidate is kept in the event_candidates table, with its numbers.

`offset_s` is LAmax minus the predicted arrival, as measured, not moved by the day's offset. Its
median over the clean matches (summary()) is the clock check, for arrivals and departures apart, as
the ADS-B plan asks: an engine is louder behind than ahead, so a departure's LAmax comes at another
point than an arrival's, and mixing them blurs the check. On a day of easterly operations NMT6
hears only departures, so both are kept.

Flags (`flags`, joined by ";"):
    unmatched     no candidate within MAX_SLANT_M
    distant       unmatched, though a pass further than MAX_SLANT_M fitted in time
    taken         there were candidates, but each made another event that fitted it better
    others        another pass may have added to the level (`others` names them)
    at_track_end  every track of the pass has its closest point at an edge of its data, so the
                  aircraft may have come closer, and sooner or later, than predicted
    no_height     no track of the pass has heights, so the arrival is from its ground distance alone
    not_aircraft  matched, though the noise source classed the event as not an aircraft
    no_clock      the day's clock offset wasn't established, so the window is centred on 0
"""

from __future__ import annotations

import bisect
import math
import statistics

from .common import day_of, iso, parse_time, rounded
from .geometry import Frame, closest_approach, closest_slant, path_angle

# The speed of sound at 15 °C. The core has no weather; at 20 °C either side it's 12 m/s faster or
# slower, which moves an arrival from 1 km by under 0.1 s.
SOUND_SPEED = 340.3
# LAmax this long before or after a pass's predicted arrival (moved by the day's clock offset) can
# still be its sound. On 5 November 2026, NMT6's events were within 3 s of their pass's arrival but
# one, at 8 s; a long event's LAmax can be further from the closest point
WINDOW_S = 20
# A pass further than this at its closest point is never matched
MAX_SLANT_M = 3000
# Another pass predicted this much quieter than the matched one or less may have added to the level
CONTRIBUTE_DB = 10
# Sound from a pass arrives this long after its track ends at most: about 20 km at the speed of sound
MAX_DELAY_S = 60
# The clock offset: looked for this far either side, in a bin this wide, which must hold this many
# pairs and this share of the day's events
SEARCH_S = 120
CLOCK_BIN_S = 4
CLOCK_MIN_PAIRS = 5
CLOCK_MIN_SHARE = 0.3
# A track this steep or more at its closest point is an arrival (descending) or a departure
# (climbing), for the clock check
LEVEL_ANGLE_DEG = 1.0
# A day's clock offset worth a warning in the build: this far out, or not established on a day
# with this many events
CLOCK_WARN_S = 5
CLOCK_WARN_EVENTS = 10

FLAGS = ("unmatched", "distant", "taken", "others", "at_track_end", "no_height", "not_aircraft", "no_clock")


def predicted(keys, tracks, frame, mic_amsl):
    """A pass's predicted sound at a receptor, from its flights [(source, source_id)] in source
    order (link.members()): {arrival, slant, ground, height, emitted, key, angle, flags}, or None
    without a track. From the highest-ranked flight whose closest point isn't at an edge of its
    data; else the highest-ranked one; else, with no heights at all, from the ground distance."""
    found = [(k, got) for k in keys if (got := closest_slant(tracks.get(k) or [], frame, mic_amsl))]
    if found:
        key, (t, slant, ground, height, edge) = next(((k, g) for k, g in found if not g[4]), found[0])
        return {"arrival": t + slant / SOUND_SPEED, "slant": slant, "ground": ground, "height": height,
                "emitted": t, "key": key, "angle": path_angle(tracks[key], frame, t),
                "flags": ["at_track_end"] if edge else []}
    for key in keys:
        got = closest_approach(tracks.get(key) or [], frame)
        if got:
            t, ground, _, _, edge = got
            return {"arrival": t + ground / SOUND_SPEED, "slant": ground, "ground": ground, "height": None,
                    "emitted": t, "key": key, "angle": None,
                    "flags": ["no_height"] + (["at_track_end"] if edge else [])}
    return None


def level_db(slant_m):
    """A pass's predicted level, but for a constant: spherical spreading only."""
    return -20 * math.log10(max(slant_m, 1.0))


def clock_offset(dts):
    """The offset (median of the densest CLOCK_BIN_S of dts) and how many fell in it, or (None, n)."""
    dts = sorted(dts)
    best = (0, 0)
    for i in range(len(dts)):
        j = bisect.bisect_right(dts, dts[i] + CLOCK_BIN_S)
        if j - i > best[1] - best[0]:
            best = (i, j)
    chosen = dts[best[0]:best[1]]
    return (statistics.median(chosen) if chosen else None), len(chosen)


def match(events, members, flights, tracks, receptors):
    """(event_matches rows, event_candidates rows, clocks), the rows in time order.

    events: the noise_events table; members: link.members(); flights: the flights table; tracks:
    {(source, source_id): track (geometry.py)}; receptors: manifest.load's receptors. clocks:
    {"<receptor> <source>": {day: {"offset_s", "pairs", "events"}}}: the offset, None where it
    wasn't established, the pairs in its bin, and the day's events. An event at a receptor that
    isn't there (a private one left out) is listed unmatched."""
    times = {(f["source"], f["source_id"]): (parse_time(f["first_utc"]), parse_time(f["last_utc"])) for f in flights}
    spans = {}  # Each pass's first and last time, over its flights
    for pass_id, keys in members.items():
        got = [times[k] for k in keys if k in times]
        if got:
            spans[pass_id] = (min(a for a, _ in got), max(b for _, b in got))

    by_group = {}
    for e in events:
        by_group.setdefault((e["receptor"], e["source"]), []).append(e)
    rows, candidates, clocks = [], [], {}
    for (rid, source), group in sorted(by_group.items()):
        group.sort(key=lambda e: parse_time(e["lmax_utc"]))
        r = receptors.get(rid)
        if r is None:
            rows += [_row(e, ["unmatched"]) for e in group]
            continue
        got_rows, got_candidates, clocks[f"{rid} {source}"] = _match_group(group, members, spans, tracks, r)
        rows += got_rows
        candidates += got_candidates
    order = lambda row: (row["lmax_utc"], row["receptor"], row["source"])  # noqa: E731
    return sorted(rows, key=order), sorted(candidates, key=lambda c: (*order(c), c["slant_m"] or 0)), clocks


def _match_group(group, members, spans, tracks, r):
    """The matches, candidates and clock offsets for one noise source's events at one receptor,
    group in LAmax order: the steps in the module's docstring, in turn."""
    frame = Frame(r["lat"], r["lon"])
    lmax = [parse_time(e["lmax_utc"]) for e in group]
    sound = _sounds(lmax, members, spans, tracks, frame, r["mic_amsl_m"])
    near = _near(lmax, sound)
    clocks = _clocks(lmax, near, sound)
    centre = [clocks[day_of(t)]["offset_s"] for t in lmax]
    # Each event's candidates, with how far each is from the window's centre
    cands = [[(p, abs(dt - (c or 0))) for p, dt in found if abs(dt - (c or 0)) <= WINDOW_S]
             for found, c in zip(near, centre)]
    chosen = _assign(cands, sound)

    rows, candidate_rows = [], []
    for i, e in enumerate(group):
        pass_id = chosen.get(i)
        ids = [p for p, _ in cands[i]]
        near_enough = [p for p in ids if sound[p]["slant"] <= MAX_SLANT_M]
        clock = [] if centre[i] is not None else ["no_clock"]
        if pass_id is None:
            flags = ["taken"] if near_enough else ["unmatched"] + (["distant"] if ids else [])
            rows.append(_row(e, flags + clock, centre[i]))
            matched_db = None
        else:
            got = sound[pass_id]
            matched_db = level_db(got["slant"])
            others = sorted((p for p in near_enough if p != pass_id
                             and matched_db - level_db(sound[p]["slant"]) < CONTRIBUTE_DB), key=lambda p: sound[p]["slant"])
            flags = (["others"] if others else []) + got["flags"] + (["not_aircraft"] if e["event_class"] == "other" else [])
            rows.append(_row(e, flags + clock, centre[i], pass_id, got, others, lmax[i]))
        for p in ids:
            candidate_rows.append({
                "source": e["source"], "receptor": e["receptor"], "lmax_utc": e["lmax_utc"], "pass_id": p,
                "matched": "1" if p == pass_id else "", "offset_s": round(lmax[i] - sound[p]["arrival"], 1),
                "slant_m": rounded(sound[p]["slant"]), "track_source": sound[p]["key"][0],
                "below_match_db": None if matched_db is None else round(matched_db - level_db(sound[p]["slant"]), 1)})
    return rows, candidate_rows, clocks


def _sounds(lmax, members, spans, tracks, frame, mic_amsl):
    """{pass_id: predicted()} for each pass that could be heard within SEARCH_S of an LAmax."""
    sound = {}
    for pass_id, (lo, hi) in spans.items():
        i = bisect.bisect_left(lmax, lo - SEARCH_S)
        if i < len(lmax) and lmax[i] <= hi + MAX_DELAY_S + SEARCH_S:
            got = predicted(members[pass_id], tracks, frame, mic_amsl)
            if got:
                sound[pass_id] = got
    return sound


def _near(lmax, sound):
    """For each event, [(pass_id, LAmax minus its predicted arrival)] for the passes within SEARCH_S."""
    near = [[] for _ in lmax]
    for pass_id, got in sound.items():
        for i in range(bisect.bisect_left(lmax, got["arrival"] - SEARCH_S),
                       bisect.bisect_right(lmax, got["arrival"] + SEARCH_S)):
            near[i].append((pass_id, lmax[i] - got["arrival"]))
    return near


def _clocks(lmax, near, sound):
    """{day: {"offset_s", "pairs", "events"}}: each day's clock offset, from its events' pairs
    with clean passes (nothing flagged, within MAX_SLANT_M), or None if none stands out."""
    by_day = {}
    for t, found in zip(lmax, near):
        day = by_day.setdefault(day_of(t), {"events": 0, "dts": []})
        day["events"] += 1
        day["dts"] += [dt for p, dt in found if not sound[p]["flags"] and sound[p]["slant"] <= MAX_SLANT_M]
    clocks = {}
    for day, d in sorted(by_day.items()):
        offset, n = clock_offset(d["dts"])
        established = offset is not None and n >= max(CLOCK_MIN_PAIRS, CLOCK_MIN_SHARE * d["events"])
        clocks[day] = {"offset_s": round(offset, 1) if established else None, "pairs": n, "events": d["events"]}
    return clocks


def _assign(cands, sound):
    """{event index: pass_id}. Every (event, candidate within MAX_SLANT_M) pair, loudest first,
    then closest in time, taken best first: each event gets one pass and each pass one event."""
    pairs = sorted((-level_db(sound[p]["slant"]), miss, i, p)
                   for i, found in enumerate(cands) for p, miss in found if sound[p]["slant"] <= MAX_SLANT_M)
    chosen, used = {}, set()
    for _, _, i, p in pairs:
        if i not in chosen and p not in used:
            chosen[i] = p
            used.add(p)
    return chosen


def _row(e, flags, centre=None, pass_id="", got=None, others=(), lmax=None):
    """An event_matches row: the event, and its match if pass_id (got: its predicted(), lmax: its time)."""
    row = {key: e[key] for key in ("source", "receptor", "lmax_utc", "lmax_db", "event_class")}
    row.update({"pass_id": pass_id, "track_source": "", "track_id": "", "emitted_utc": "", "arrival_utc": "",
                "offset_s": None, "window_centre_s": centre, "slant_m": None, "ground_m": None, "height_m": None,
                "path_angle_deg": None, "others": ";".join(others), "flags": ";".join(flags)})
    if pass_id:
        row.update({"track_source": got["key"][0], "track_id": got["key"][1], "emitted_utc": iso(got["emitted"]),
                    "arrival_utc": iso(got["arrival"]), "offset_s": round(lmax - got["arrival"], 1),
                    "slant_m": rounded(got["slant"]), "ground_m": rounded(got["ground"]),
                    "height_m": rounded(got["height"]), "path_angle_deg": rounded(got["angle"], 2)})
    return row


def clean_kind(row):
    """"arrival" or "departure" if the clock check can use the match: nothing flagged but no_clock,
    and a path angle that says which; else None."""
    angle = row["path_angle_deg"]
    if not row["pass_id"] or not set(row["flags"].split(";")) <= {"", "no_clock"} or angle in (None, ""):
        return None
    angle = float(angle)
    return "arrival" if angle <= -LEVEL_ANGLE_DEG else "departure" if angle >= LEVEL_ANGLE_DEG else None


def summary(rows, clocks):
    """build.json's matches: per receptor and noise source, how many events were matched, each
    day's clock offset (the window's centre), and the median offset of LAmax from the predicted
    arrival over the clean arrivals and, apart, the clean departures."""
    out = {}
    for row in rows:
        group = f"{row['receptor']} {row['source']}"
        s = out.setdefault(group, {"events": 0, "matched": 0, "unmatched": 0, "distant": 0, "taken": 0,
                                   "with others": 0, "offsets": {"arrival": [], "departure": []}})
        s["events"] += 1
        flags = row["flags"].split(";")
        s["matched"] += bool(row["pass_id"])
        for flag, key in (("unmatched", "unmatched"), ("distant", "distant"), ("taken", "taken"), ("others", "with others")):
            s[key] += flag in flags
        kind = clean_kind(row)
        if kind:
            s["offsets"][kind].append(row["offset_s"])
    for group, s in out.items():
        for kind, offsets in s.pop("offsets").items():
            s[f"clean {kind}s"] = len(offsets)
            s[f"median offset s, clean {kind}s"] = round(statistics.median(offsets), 1) if offsets else None
        s["clock by day"] = clocks.get(group, {})
    return out


def clock_warnings(clocks):
    """The build's warnings about clocks (match()'s clocks): a day whose offset is over
    CLOCK_WARN_S, or not established on a day of CLOCK_WARN_EVENTS events or more."""
    out = []
    for group, days in clocks.items():
        for day, clock in days.items():
            if clock["offset_s"] is not None and abs(clock["offset_s"]) > CLOCK_WARN_S:
                out.append(f"{group} on {day}: noise events are {clock['offset_s']:+.1f} s from their passes' "
                           "predicted arrivals: a clock may be out")
            elif clock["offset_s"] is None and clock["events"] >= CLOCK_WARN_EVENTS:
                out.append(f"{group} on {day}: no clock offset stands out, so matching assumed the clocks agree")
    return out

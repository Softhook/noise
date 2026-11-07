"""Match each noise event at a receptor to the pass that made it (ARCHITECTURE.md, Match).

For each pass near an event in time, the sound's predicted arrival at the receptor: where its track
came closest to the microphone in three dimensions (geometry.closest_slant), plus the time sound
takes to cover that distance. The track is the pass's flight in the highest-ranked source
(link.source_rank) whose closest point isn't at an edge of its data, so the ADS-B sources' before
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

from . import link
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

FLAGS = ("unmatched", "distant", "taken", "others", "at_track_end", "no_height", "not_aircraft", "no_clock")


def predicted(members, tracks, frame, mic_amsl):
    """A pass's predicted sound at a receptor, from its flights [(source, source_id)]: {arrival,
    slant, ground, height, emitted, key, angle, flags}, or None without a track. From the
    highest-ranked flight whose closest point isn't at an edge of its data; else the highest-ranked
    one; else, with no heights at all, from the ground distance."""
    ranked = sorted(members, key=lambda k: (link.source_rank(k[0]), k[1]))
    found = [(k, got) for k in ranked if (got := closest_slant(tracks.get(k) or [], frame, mic_amsl))]
    if found:
        key, (t, slant, ground, height, edge) = next(((k, g) for k, g in found if not g[4]), found[0])
        return {"arrival": t + slant / SOUND_SPEED, "slant": slant, "ground": ground, "height": height,
                "emitted": t, "key": key, "angle": path_angle(tracks[key], frame, t),
                "flags": ["at_track_end"] if edge else []}
    for key in ranked:
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


def match(events, passes, flights, tracks, receptors):
    """(event_matches rows, event_candidates rows, clocks), the rows in time order.

    events: the noise_events table; passes, flights: those tables; tracks: {(source, source_id):
    track (geometry.py)}; receptors: manifest.load's receptors. clocks: {"<receptor> <source>":
    {day: {"offset_s", "pairs", "events"}}}: the offset, None where it wasn't established, the pairs
    in its bin, and the day's events. An event at a
    receptor that isn't there (a private one left out) is listed unmatched."""
    members, span = {}, {}
    times = {(f["source"], f["source_id"]): (parse_time(f["first_utc"]), parse_time(f["last_utc"])) for f in flights}
    for p in passes:
        key = (p["source"], p["source_id"])
        members.setdefault(p["pass_id"], []).append(key)
        if key in times:
            lo, hi = span.get(p["pass_id"], times[key])
            span[p["pass_id"]] = (min(lo, times[key][0]), max(hi, times[key][1]))

    rows, candidates, clocks = [], [], {}
    by_group = {}
    for e in events:
        by_group.setdefault((e["receptor"], e["source"]), []).append(e)
    for (rid, source), group in sorted(by_group.items()):
        group.sort(key=lambda e: parse_time(e["lmax_utc"]))
        r = receptors.get(rid)
        if r is None:
            rows += [_row(e, None, None, ["unmatched"], [], None) for e in group]
            continue
        got_rows, got_candidates, clocks[f"{rid} {source}"] = _match_group(group, members, span, tracks, r)
        rows += got_rows
        candidates += got_candidates
    order = lambda row: (row["lmax_utc"], row["receptor"], row["source"])  # noqa: E731
    return sorted(rows, key=order), sorted(candidates, key=lambda c: (*order(c), c["slant_m"] or 0)), clocks


def _match_group(group, members, span, tracks, r):
    """The matches, candidates and clock offsets for one noise source's events at one receptor."""
    frame = Frame(r["lat"], r["lon"])
    mic = float(r["ground_elevation_m"] or 0) + float(r["mic_height_m"] or 0)
    lmax = [parse_time(e["lmax_utc"]) for e in group]

    # Each pass that could be heard within SEARCH_S of an event's LAmax, and its predicted sound
    sound = {}
    for pass_id, (lo, hi) in span.items():
        i = bisect.bisect_left(lmax, lo - SEARCH_S)
        if i < len(lmax) and lmax[i] <= hi + MAX_DELAY_S + SEARCH_S:
            got = predicted(members[pass_id], tracks, frame, mic)
            if got:
                sound[pass_id] = got

    # Every (event, pass) pair within SEARCH_S, and each day's clock offset from the clean ones
    near = [[] for _ in group]
    for pass_id, got in sound.items():
        for i in range(bisect.bisect_left(lmax, got["arrival"] - SEARCH_S),
                       bisect.bisect_right(lmax, got["arrival"] + SEARCH_S)):
            near[i].append((pass_id, lmax[i] - got["arrival"]))
    by_day = {}
    for i, t in enumerate(lmax):
        day = by_day.setdefault(day_of(t), {"events": 0, "dts": []})
        day["events"] += 1
        day["dts"] += [dt for p, dt in near[i] if not sound[p]["flags"] and sound[p]["slant"] <= MAX_SLANT_M]
    clocks = {}
    for day, d in sorted(by_day.items()):
        offset, n = clock_offset(d["dts"])
        established = offset is not None and n >= max(CLOCK_MIN_PAIRS, CLOCK_MIN_SHARE * d["events"])
        clocks[day] = {"offset_s": round(offset, 1) if established else None, "pairs": n, "events": d["events"]}
    centre = [clocks[day_of(t)]["offset_s"] for t in lmax]

    # The candidates, and every pair close enough to match, loudest first, then closest in time
    pairs, cands = [], [[] for _ in group]
    for i, found in enumerate(near):
        for pass_id, dt in found:
            if abs(dt - (centre[i] or 0)) <= WINDOW_S:
                cands[i].append(pass_id)
                if sound[pass_id]["slant"] <= MAX_SLANT_M:
                    pairs.append((-level_db(sound[pass_id]["slant"]), abs(dt - (centre[i] or 0)), i, pass_id))
    chosen, used = {}, set()
    for _, _, i, pass_id in sorted(pairs):
        if i not in chosen and pass_id not in used:
            chosen[i] = pass_id
            used.add(pass_id)

    rows, candidate_rows = [], []
    for i, e in enumerate(group):
        pass_id = chosen.get(i)
        clock = [] if centre[i] is not None else ["no_clock"]
        near_enough = [c for c in cands[i] if sound[c]["slant"] <= MAX_SLANT_M]
        if pass_id is None:
            flags = ["taken"] if near_enough else ["unmatched"] + (["distant"] if cands[i] else [])
            rows.append(_row(e, None, None, flags + clock, [], centre[i]))
            matched_db = None
        else:
            got = sound[pass_id]
            matched_db = level_db(got["slant"])
            others = [c for c in near_enough if c != pass_id and matched_db - level_db(sound[c]["slant"]) < CONTRIBUTE_DB]
            others.sort(key=lambda c: sound[c]["slant"])
            flags = (["others"] if others else []) + got["flags"] + (["not_aircraft"] if e["event_class"] == "other" else [])
            rows.append(_row(e, pass_id, got, flags + clock, others, centre[i], lmax[i]))
        for c in cands[i]:
            candidate_rows.append({
                "source": e["source"], "receptor": e["receptor"], "lmax_utc": e["lmax_utc"], "pass_id": c,
                "matched": "1" if c == pass_id else "", "offset_s": round(lmax[i] - sound[c]["arrival"], 1),
                "slant_m": rounded(sound[c]["slant"]), "track_source": sound[c]["key"][0],
                "below_match_db": None if matched_db is None else round(matched_db - level_db(sound[c]["slant"]), 1)})
    return rows, candidate_rows, clocks


def _row(e, pass_id, got, flags, others, centre, at=None):
    row = {key: e[key] for key in ("source", "receptor", "lmax_utc", "lmax_db", "event_class")}
    row.update({"pass_id": pass_id or "", "track_source": "", "track_id": "", "emitted_utc": "", "arrival_utc": "",
                "offset_s": None, "window_centre_s": centre, "slant_m": None, "ground_m": None, "height_m": None,
                "path_angle_deg": None, "others": ";".join(others), "flags": ";".join(flags)})
    if pass_id:
        row.update({"track_source": got["key"][0], "track_id": got["key"][1], "emitted_utc": iso(got["emitted"]),
                    "arrival_utc": iso(got["arrival"]), "offset_s": round(at - got["arrival"], 1),
                    "slant_m": rounded(got["slant"]), "ground_m": rounded(got["ground"]),
                    "height_m": rounded(got["height"]),
                    "path_angle_deg": None if got["angle"] is None else round(got["angle"], 2)})
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

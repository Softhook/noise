"""Match each noise event at a receptor to the pass that made it (ARCHITECTURE.md, Match).

For each pass near an event in time, the sound's predicted arrival at the receptor: where its track
came closest to the microphone in three dimensions (geometry.closest_slant), plus the time sound
takes to cover that distance. The track is the pass's flight in the highest-ranked source
(link.source_rank) whose closest point isn't at an edge of its data, so the ADS-B sources' before
WebTrak's, and a match never depends on WebTrak's radar when an ADS-B track is there.

An event's candidates are the passes whose predicted arrival is within WINDOW_S of its LAmax. Of
those, it's matched to the one predicted loudest: the closest, since sound falls off with distance
(6 dB each time it doubles). Each pass makes at most one event of a source at a receptor, so when
two events want one pass it goes to the event it came closer to in time, and the other event takes
its next candidate. Every pair is ranked first and then taken best first, as link does, so the
result doesn't depend on the order of the events.

The other candidates predicted within CONTRIBUTE_DB of the matched one are listed in `others`:
close enough that they may have added to the level, such as a helicopter or a high Heathrow
arrival under an LCY departure. A pass 10 dB quieter adds under half a decibel.

`offset_s` is LAmax minus the predicted arrival. Its median over a day's matches is the clock check
between the noise source and the track's source; `checks` will report it.

Flags (`flags`, joined by ";"):
    unmatched     no pass's predicted arrival is within WINDOW_S of LAmax
    taken         there were candidates, but each made another event that fitted it better
    others        another pass may have added to the level (`others` lists them)
    at_track_end  every track of the pass has its closest point at an edge of its data, so the
                  aircraft may have come closer, and sooner or later, than predicted
    no_height     no track of the pass has heights, so the arrival is from its ground distance alone
    not_aircraft  matched, though the noise source classed the event as not an aircraft
"""

from __future__ import annotations

import bisect
import math
import statistics

from . import link
from .common import iso, parse_time, rounded
from .geometry import Frame, closest_approach, closest_slant

# The speed of sound at 15 °C. The core has no weather; at 20 °C either side it's 12 m/s faster or
# slower, which moves an arrival from 1 km by under 0.1 s.
SOUND_SPEED = 340.3
# LAmax this long before or after a pass's predicted arrival can still be its sound. On 5 November
# 2026, NMT6's events were within 3 s of their pass's arrival but one, at 8 s; a garden clock that's
# out, or a long event's LAmax away from the closest point, needs more room
WINDOW_S = 20
# Another pass predicted this much quieter than the matched one or less may have added to the level
CONTRIBUTE_DB = 10
# Sound from a pass arrives this long after its track ends at most: about 20 km at the speed of sound
MAX_DELAY_S = 60

FLAGS = ("unmatched", "taken", "others", "at_track_end", "no_height", "not_aircraft")


def predicted(members, tracks, frame, mic_amsl):
    """A pass's predicted sound at a receptor, from its flights [(source, source_id)]: (arrival_t,
    slant_m, ground_m, height_m, emitted_t, (source, source_id), flags), or None without a track.
    From the highest-ranked flight whose closest point isn't at an edge of its data; else the
    highest-ranked one; else, with no heights at all, from the ground distance."""
    found = []
    for key in sorted(members, key=lambda k: (link.source_rank(k[0]), k[1])):
        got = closest_slant(tracks.get(key) or [], frame, mic_amsl)
        if got:
            found.append((key, got))
    if found:
        key, (t, slant, ground, height, edge) = next(((k, g) for k, g in found if not g[4]), found[0])
        return t + slant / SOUND_SPEED, slant, ground, height, t, key, ["at_track_end"] if edge else []
    for key in sorted(members, key=lambda k: (link.source_rank(k[0]), k[1])):
        got = closest_approach(tracks.get(key) or [], frame)
        if got:
            t, ground, _, _, edge = got
            return t + ground / SOUND_SPEED, ground, ground, None, t, key, ["no_height"] + (["at_track_end"] if edge else [])
    return None


def level_db(slant_m):
    """A pass's predicted level, but for a constant: spherical spreading only."""
    return -20 * math.log10(max(slant_m, 1.0))


def match(events, passes, flights, tracks, receptors):
    """Rows for the event_matches table, one per noise event, in time order.

    events: the noise_events table; passes, flights: those tables; tracks: {(source, source_id):
    track (geometry.py)}; receptors: manifest.load's receptors. An event at a receptor that isn't
    there (a private one left out) is listed unmatched."""
    members, span = {}, {}
    times = {(f["source"], f["source_id"]): (parse_time(f["first_utc"]), parse_time(f["last_utc"])) for f in flights}
    for p in passes:
        key = (p["source"], p["source_id"])
        members.setdefault(p["pass_id"], []).append(key)
        if key in times:
            lo, hi = span.get(p["pass_id"], times[key])
            span[p["pass_id"]] = (min(lo, times[key][0]), max(hi, times[key][1]))

    rows = []
    by_group = {}
    for e in events:
        by_group.setdefault((e["receptor"], e["source"]), []).append(e)
    for (rid, _), group in sorted(by_group.items()):
        group.sort(key=lambda e: parse_time(e["lmax_utc"]))
        r = receptors.get(rid)
        if r is None:
            rows += [_row(e, None, [], ["unmatched"]) for e in group]
            continue
        rows += _match_group(group, members, span, tracks, r)
    return sorted(rows, key=lambda row: (row["lmax_utc"], row["receptor"], row["source"]))


def _match_group(group, members, span, tracks, r):
    """The matches for one noise source's events at one receptor."""
    frame = Frame(r["lat"], r["lon"])
    mic = float(r["ground_elevation_m"] or 0) + float(r["mic_height_m"] or 0)
    lmax = [parse_time(e["lmax_utc"]) for e in group]

    # Each pass that could be heard around an event's LAmax, and its predicted sound
    sound = {}
    for pass_id, (lo, hi) in span.items():
        i = bisect.bisect_left(lmax, lo - WINDOW_S)
        if i < len(lmax) and lmax[i] <= hi + MAX_DELAY_S + WINDOW_S:
            got = predicted(members[pass_id], tracks, frame, mic)
            if got:
                sound[pass_id] = got

    # Every (event, pass) pair within the window, loudest first, then closest in time
    pairs, candidates = [], [[] for _ in group]
    for pass_id, got in sound.items():
        lo = bisect.bisect_left(lmax, got[0] - WINDOW_S)
        hi = bisect.bisect_right(lmax, got[0] + WINDOW_S)
        for i in range(lo, hi):
            candidates[i].append(pass_id)
            pairs.append((-level_db(got[1]), abs(lmax[i] - got[0]), i, pass_id))
    chosen, used = {}, set()
    for _, _, i, pass_id in sorted(pairs):
        if i not in chosen and pass_id not in used:
            chosen[i] = pass_id
            used.add(pass_id)

    rows = []
    for i, e in enumerate(group):
        pass_id = chosen.get(i)
        if pass_id is None:
            rows.append(_row(e, None, [], ["taken" if candidates[i] else "unmatched"],
                             _others(candidates[i], sound, lmax[i], None)))
            continue
        got = sound[pass_id]
        others = _others([c for c in candidates[i] if c != pass_id], sound, lmax[i], level_db(got[1]))
        flags = (["others"] if others else []) + got[6] + (["not_aircraft"] if e["event_class"] == "other" else [])
        rows.append(_row(e, pass_id, got, flags, others, lmax[i]))
    return rows


def _others(pass_ids, sound, at, matched_db):
    """The other candidates loud enough to have added to the level (all of them when nothing was
    matched), loudest first, as 'pass_id 1450 m +3.2 s'."""
    keep = sorted((p for p in pass_ids if matched_db is None or matched_db - level_db(sound[p][1]) < CONTRIBUTE_DB),
                  key=lambda p: sound[p][1])
    return "; ".join(f"{p} {sound[p][1]:.0f} m {at - sound[p][0]:+.1f} s" for p in keep)


def _row(e, pass_id, got, flags, others="", at=None):
    row = {key: e[key] for key in ("source", "receptor", "lmax_utc", "lmax_db", "event_class")}
    row.update({"pass_id": pass_id or "", "track_source": "", "track_id": "", "emitted_utc": "", "arrival_utc": "",
                "offset_s": None, "slant_m": None, "ground_m": None, "height_m": None,
                "others": others, "flags": ";".join(flags)})
    if pass_id:
        arrival, slant, ground, height, emitted, key, _ = got
        row.update({"track_source": key[0], "track_id": key[1], "emitted_utc": iso(emitted), "arrival_utc": iso(arrival),
                    "offset_s": round(at - arrival, 1), "slant_m": rounded(slant), "ground_m": rounded(ground),
                    "height_m": rounded(height)})
    return row


def summary(rows):
    """build.json's matches: per receptor and noise source, how many events were matched, and the
    median offset of LAmax from the predicted arrival."""
    out = {}
    for row in rows:
        s = out.setdefault(f"{row['receptor']} {row['source']}", {"events": 0, "matched": 0, "unmatched": 0,
                                                                   "taken": 0, "with others": 0, "offsets": []})
        s["events"] += 1
        flags = row["flags"].split(";")
        if row["pass_id"]:
            s["matched"] += 1
            s["offsets"].append(row["offset_s"])
        s["unmatched"] += "unmatched" in flags
        s["taken"] += "taken" in flags
        s["with others"] += "others" in flags
    for s in out.values():
        offsets = s.pop("offsets")
        s["median offset s"] = round(statistics.median(offsets), 1) if offsets else None
    return out

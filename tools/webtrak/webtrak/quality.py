"""Check the saved data for one monitor: what is missing, what looks wrong, what to trust less.

  python3 -m webtrak quality [--nmt 106] [--from 'YYYY-MM-DD HH:MM'] [--to ...] [--json report.json]

Reads only what is saved under data/<site>/nmt<id>/ (and the raw cache for the radar status); it
never downloads and never changes a file. Without --from/--to it checks everything saved.

Each check gives a count and a few examples. The thresholds below are rules of thumb, not
WebTrak's: a finding is a reason to look, not proof that the data is wrong.

Coverage   chunks missing between the first and last saved one; saved chunks without their 30
           seconds of levels, or with seconds twice; chunks whose radar WebTrak said was not
           online; events still waiting for radar.
Levels     seconds with no measurement (the 00:00 and 12:00 placeholders are counted apart);
           levels outside LEVEL_RANGE_DB; the same level for STUCK_S seconds or more; steps of
           JUMP_DB or more from one second to the next; local times with the wrong UTC offset.
Events     repeated events; SEL not equal to Leq + 10 log10(duration); LAmax not the highest
           1 s level within the event; flag 1 seconds outside every event, and aircraft events
           with no flag 1 seconds (flag 1 marks only class 1 events); aircraft (class 1) events with no aircraft matched, or matched to one
           more than FAR_SLANT_M away; other (class 5) events with an aircraft within NEAR_SLANT_M;
           LAmax too long before or after the closest approach; events whose radar is incomplete.
Radar      repeated positions; gaps of more than store.MAX_STEP_S within a track; positions
           without a height; implausible heights or speeds.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import math
import os

from . import parse, stats, store

LEVEL_RANGE_DB = (25.0, 110.0)   # outside this a 1 s level outdoors in Thamesmead is unlikely
STUCK_S = 30                     # the same level this many seconds running suggests a stuck output
JUMP_DB = 15.0                   # a step this big in one second is more than a passing aircraft gives
SEL_TOLERANCE_DB = 0.3           # WebTrak rounds to 0.01 dB and durations to 1 s
LMAX_TOLERANCE_DB = 0.5
FAR_SLANT_M = 1500               # an aircraft event matched further away than this is a weak match
NEAR_SLANT_M = 1000              # a non-aircraft event with an aircraft this close may be misclassed
LAG_RANGE_S = (-5, 20)           # LAmax from 5 s before to 20 s after the closest approach is normal
TRACK_GAP_MAX_S = 300            # longer gaps within a track are the aircraft leaving and coming back
HEIGHT_RANGE_M = (-50, 15000)
SPEED_MAX_MS = 350
EXAMPLES = 8


def _utc(text):
    return stats._utc(text)


def _local(t):
    return dt.datetime.fromtimestamp(t, parse.site_zone()).strftime("%Y-%m-%d %H:%M:%S")


def _rows(path):
    try:
        with open(path, newline="") as f:
            yield from csv.DictReader(f)
    except OSError:
        return


def _float(text):
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


class Report:
    """Findings grouped by section: each has a count, a note and some examples."""

    def __init__(self):
        self.sections = collections.OrderedDict()
        self.facts = collections.OrderedDict()

    def fact(self, section, name, value):
        self.facts.setdefault(section, collections.OrderedDict())[name] = value

    def finding(self, section, name, items, note, warn=True):
        items = list(items)
        self.sections.setdefault(section, []).append(
            {"check": name, "count": len(items), "warn": warn and bool(items), "note": note,
             "examples": items[:EXAMPLES]})

    @property
    def warnings(self):
        return sum(1 for checks in self.sections.values() for c in checks if c["warn"])

    def as_dict(self):
        return {"facts": self.facts, "sections": self.sections, "warnings": self.warnings}

    def text(self):
        lines = []
        for section in list(self.facts) + [s for s in self.sections if s not in self.facts]:
            lines.append(f"\n{section}")
            for name, value in self.facts.get(section, {}).items():
                lines.append(f"  {name}: {value}")
            for c in self.sections.get(section, []):
                mark = "WARN" if c["warn"] else ("ok  " if not c["count"] else "info")
                lines.append(f"  {mark} {c['check']}: {c['count']}" + (f"  ({c['note']})" if c["note"] else ""))
                for example in c["examples"]:
                    lines.append(f"         {example}")
                if c["count"] > len(c["examples"]):
                    lines.append(f"         ... and {c['count'] - len(c['examples'])} more")
        lines.append(f"\n{self.warnings} check(s) with warnings")
        return "\n".join(lines).lstrip("\n")


def _runs(times):
    """Consecutive runs in a sorted list of whole seconds, as (first, last)."""
    out = []
    for t in times:
        if out and t == out[-1][1] + 1:
            out[-1][1] = t
        else:
            out.append([t, t])
    return out


def _is_placeholder_time(t):
    """Within the first two minutes after 00:00 or 12:00 local, when WebTrak sends its 20 dB placeholder."""
    local = dt.datetime.fromtimestamp(t, parse.site_zone())
    return local.hour in (0, 12) and local.minute < 2


def check(monitor_dir, start=None, end=None, site_dir=None):
    """Check one monitor folder over [start, end) (UTC seconds; default everything saved). Returns a Report.

    With site_dir, the radar status of each saved chunk is read from the site's raw cache."""
    report = Report()
    state = store.read_state(monitor_dir)
    saved = state.get("saved", [])
    monitor = state.get("monitor", {})
    if start is None or end is None:
        if not saved:
            report.fact("Coverage", "saved chunks", "none")
            return report
        start = parse.utc_for_handle(saved[0][0]) if start is None else start
        end = parse.utc_for_handle(saved[-1][1] + 1) if end is None else end
    first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
    handles = [h for a, b in saved for h in range(max(a, first), min(b, last) + 1)]
    handle_set = set(handles)

    if monitor:
        report.fact("Coverage", "monitor", f"NMT{monitor.get('id')} {monitor.get('name', '')}")
    report.fact("Coverage", "period", f"{_local(start)} to {_local(end)} local")
    report.fact("Coverage", "chunks saved", f"{len(handles)} of {last - first + 1}"
                f" ({100 * len(handles) / (last - first + 1):.1f}%)")

    # --- coverage --------------------------------------------------------------------------
    missing = store.gaps(saved, first, last)
    report.finding("Coverage", "missing chunk ranges",
                   [f"{_local(parse.utc_for_handle(a))} to {_local(parse.utc_for_handle(b + 1))}"
                    f" ({b - a + 1} chunks)" for a, b in missing],
                   "fetch the period again to fill them")

    # Levels: read every row ourselves, to see repeats and the local offsets.
    zone = parse.site_zone()
    by_second = collections.Counter()
    levels = {}
    bad_offset = []
    for day in stats.local_days(start, end):
        for row in _rows(os.path.join(monitor_dir, "levels", f"{day}.csv")):
            try:
                t = round(_utc(row["time_utc"]))
            except (KeyError, ValueError):
                continue
            if not start <= t < end:
                continue
            by_second[t] += 1
            levels[t] = (_float(row.get("level_db")), row.get("flag", ""))
            try:
                offset = dt.datetime.fromisoformat(row["time_local"]).utcoffset()
                expected = dt.datetime.fromtimestamp(t, zone).utcoffset()
                if offset != expected:
                    bad_offset.append(f"{row['time_utc']} written as {row['time_local']}")
            except (KeyError, ValueError):
                bad_offset.append(f"{row.get('time_utc')}: unreadable local time {row.get('time_local')!r}")

    per_chunk = collections.Counter(parse.handle_for_utc(t) for t in by_second)
    short = [f"{_local(parse.utc_for_handle(h))}: {per_chunk.get(h, 0)} s"
             for h in handles if per_chunk.get(h, 0) < parse.WINDOW_S]
    report.finding("Coverage", "saved chunks with fewer than 30 s of levels", short,
                   "WebTrak sent fewer seconds, or the levels file was edited")
    outside = sorted(h for h in per_chunk if h not in handle_set)
    report.finding("Coverage", "levels in chunks not marked saved",
                   [_local(parse.utc_for_handle(h)) for h in outside],
                   "state.json and the levels files disagree")
    report.finding("Coverage", "seconds written more than once",
                   [f"{_local(t)} x{n}" for t, n in sorted(by_second.items()) if n > 1],
                   "a chunk appended twice")

    if site_dir:
        cache = store.RawCache(site_dir)
        statuses = collections.Counter()
        offline, uncached = [], 0
        for h in handles:
            text = cache.get(h)
            if text is None:
                uncached += 1
                continue
            try:
                status = parse.parse_chunk(text, h).radar_status or "?"
            except parse.NotAvailable:
                status = "unreadable"
            statuses[status] += 1
            if status != "online":
                offline.append(f"{_local(parse.utc_for_handle(h))}: radar {status}")
        report.fact("Coverage", "radar status", ", ".join(f"{k} {v}" for k, v in statuses.most_common()) or "-")
        report.finding("Coverage", "chunks whose radar was not online", offline,
                       "events then may have no aircraft matched")
        if uncached:
            report.fact("Coverage", "chunks not in the raw cache", uncached)
    pending = state.get("pending", [])
    report.finding("Coverage", "events waiting for radar",
                   [_local(e.get("lmax_time", 0)) for e in pending],
                   "matched when the chunks around them are saved")

    # --- levels ----------------------------------------------------------------------------
    times = sorted(levels)
    valid = [(t, levels[t][0]) for t in times if levels[t][0] is not None]
    flags = collections.Counter(levels[t][1] for t in times)
    report.fact("Levels", "seconds", f"{len(times)} ({len(valid)} measured)")
    report.fact("Levels", "flags", ", ".join(f"{k or '-'}: {v}" for k, v in sorted(flags.items())))
    if valid:
        values = [v for _, v in valid]
        report.fact("Levels", "range", f"{min(values):.1f} to {max(values):.1f} dB, LAeq {stats.energy_mean(values):.1f},"
                    f" L90 {stats.exceeded(values, 90):.1f}")
    blank_runs = _runs([t for t in times if levels[t][0] is None])
    placeholder = [r for r in blank_runs if _is_placeholder_time(r[0])]
    other = [r for r in blank_runs if not _is_placeholder_time(r[0])]
    report.finding("Levels", "no-measurement runs at 00:00 / 12:00",
                   [f"{_local(a)} for {b - a + 1} s" for a, b in placeholder],
                   "WebTrak's usual placeholder", warn=False)
    report.finding("Levels", "other no-measurement runs", [f"{_local(a)} for {b - a + 1} s" for a, b in other],
                   "the monitor reported nothing")
    low, high = LEVEL_RANGE_DB
    report.finding("Levels", f"levels outside {low:g}-{high:g} dB",
                   [f"{_local(t)}: {v:.1f} dB" for t, v in valid if not low <= v <= high], "")
    stuck, run = [], []
    for t, v in valid + [(None, None)]:
        if run and t == run[-1][0] + 1 and v == run[-1][1]:
            run.append((t, v))
            continue
        if len(run) >= STUCK_S:
            stuck.append(f"{_local(run[0][0])}: {run[0][1]:.1f} dB for {len(run)} s")
        run = [(t, v)] if t is not None else []
    report.finding("Levels", f"same level {STUCK_S} s or more", stuck, "a stuck or held output")
    jumps = [f"{_local(t2)}: {v1:.1f} -> {v2:.1f} dB" for (t1, v1), (t2, v2) in zip(valid, valid[1:])
             if t2 == t1 + 1 and abs(v2 - v1) >= JUMP_DB]
    report.finding("Levels", f"steps of {JUMP_DB:g} dB or more in 1 s", jumps, "spikes or dropouts")
    report.finding("Levels", "local times with the wrong UTC offset", bad_offset, "")

    # --- events ----------------------------------------------------------------------------
    events = []
    starts = collections.Counter()
    for row in _rows(os.path.join(monitor_dir, "events.csv")):
        try:
            e = {"start": _utc(row["start_utc"]), "lmax_t": _utc(row["lmax_time_local"]),
                 "end": _utc(row["end_local"]), "duration": float(row["duration_s"]),
                 "lmax": float(row["lmax_db"]), "sel": float(row["sel_db"]), "leq": float(row["leq_db"]),
                 "class": row["event_class"], "who": row["callsign"] or (f"track {row['track']}" if row["track"] else ""),
                 "type": row["type"], "track": row["track"], "slant": _float(row["closest_slant_m"]),
                 "lag": _float(row["lmax_after_closest_s"]), "candidates": int(row["candidates"] or 0)}
        except (KeyError, ValueError):
            continue
        if start <= e["lmax_t"] < end:
            events.append(e)
            starts[round(e["start"])] += 1
    events.sort(key=lambda e: e["start"])
    classes = collections.Counter(e["class"] for e in events)
    report.fact("Events", "events", f"{len(events)} (" + ", ".join(f"class {k}: {v}" for k, v in sorted(classes.items())) + ")")
    matched = [e for e in events if e["track"]]
    report.fact("Events", "matched to an aircraft", f"{len(matched)} of {len(events)}")

    def name(e):
        return f"{_local(e['lmax_t'])} LAmax {e['lmax']:.1f} class {e['class']}" + (f" {e['who']} {e['type']}" if e["track"] else "")

    report.finding("Events", "events listed more than once",
                   [f"{_local(t)} x{n}" for t, n in sorted(starts.items()) if n > 1], "")
    report.finding("Events", f"SEL differs from Leq + 10 log10(duration) by more than {SEL_TOLERANCE_DB} dB",
                   [f"{name(e)}: SEL {e['sel']:.2f}, expected {e['leq'] + 10 * math.log10(e['duration']):.2f}"
                    for e in events if e["duration"] > 0
                    and abs(e["sel"] - e["leq"] - 10 * math.log10(e["duration"])) > SEL_TOLERANCE_DB], "")
    report.finding("Events", "LAmax time outside the event", [name(e) for e in events
                                                              if not e["start"] <= e["lmax_t"] <= e["end"]], "")
    lmax_off, no_levels = [], []
    for e in events:
        inside = [levels[t][0] for t in range(math.floor(e["start"]), math.ceil(e["end"]) + 1)
                  if t in levels and levels[t][0] is not None]
        if not inside:
            no_levels.append(name(e))
        elif abs(max(inside) - e["lmax"]) > LMAX_TOLERANCE_DB:
            lmax_off.append(f"{name(e)}: highest 1 s level {max(inside):.1f}")
    report.finding("Events", "events without saved levels", no_levels, "")
    report.finding("Events", f"LAmax differs from the highest 1 s level by more than {LMAX_TOLERANCE_DB} dB",
                   lmax_off, "")
    in_event = set()
    for e in events:
        in_event.update(range(math.floor(e["start"]), math.ceil(e["end"]) + 1))
    stray = _runs([t for t in times if levels[t][1] == "1" and t not in in_event])
    report.finding("Events", "flag 1 seconds outside every saved event",
                   [f"{_local(a)} for {b - a + 1} s" for a, b in stray],
                   "an event WebTrak didn't list, or one outside the period")
    # Flag 1 marks only aircraft (class 1) events: class 5 events keep flag 5 (seen on 5 Nov 2026).
    report.finding("Events", "aircraft events with no flag 1 seconds",
                   [name(e) for e in events if e["class"] == "1" and not any(
                       levels.get(t, (None, ""))[1] == "1" for t in range(math.floor(e["start"]), math.ceil(e["end"]) + 1))],
                   "")
    report.finding("Events", "aircraft events with no aircraft matched",
                   [name(e) for e in events if e["class"] == "1" and not e["track"]],
                   "radar missing, or the aircraft was outside the radius")
    report.finding("Events", f"aircraft events matched more than {FAR_SLANT_M} m away",
                   [f"{name(e)} at {e['slant']:.0f} m" for e in events
                    if e["class"] == "1" and e["slant"] is not None and e["slant"] > FAR_SLANT_M], "weak matches")
    report.finding("Events", f"non-aircraft events with an aircraft within {NEAR_SLANT_M} m",
                   [f"{name(e)} at {e['slant']:.0f} m" for e in events
                    if e["class"] != "1" and e["slant"] is not None and e["slant"] <= NEAR_SLANT_M],
                   "maybe an aircraft WebTrak didn't attribute", warn=False)
    lo, hi = LAG_RANGE_S
    report.finding("Events", f"LAmax outside {lo} to +{hi} s of the closest approach",
                   [f"{name(e)}: {e['lag']:+.0f} s" for e in events if e["lag"] is not None and not lo <= e["lag"] <= hi],
                   "maybe the wrong aircraft")
    report.finding("Events", "matched with more than one aircraft in range",
                   [f"{name(e)}: {e['candidates']} aircraft" for e in events if e["candidates"] > 1],
                   "the closest was chosen", warn=False)
    report.finding("Events", "events whose radar window isn't all saved",
                   [name(e) for e in events if not all(any(a <= h <= b for a, b in saved)
                                                       for h in store.match_handles(parse.Event(
                                                           "", e["start"], e["lmax_t"], e["end"], 0, 0, 0, 0, 0, "")))],
                   "the match may have missed an aircraft")

    # --- radar -----------------------------------------------------------------------------
    positions = []
    seen = collections.Counter()
    for day in stats.local_days(start, end):
        for row in _rows(os.path.join(monitor_dir, "aircraft", f"{day}.csv")):
            try:
                t = _utc(row["time_utc"])
            except (KeyError, ValueError):
                continue
            if start <= t < end:
                positions.append((t, row))
                seen[(row["time_utc"], row["track"])] += 1
    tracks = collections.defaultdict(list)
    for t, row in positions:
        tracks[row["track"]].append((t, row))
    report.fact("Radar", "positions", f"{len(positions)} in {len(tracks)} tracks")
    report.finding("Radar", "positions written more than once",
                   [f"{k[0]} track {k[1]} x{n}" for k, n in sorted(seen.items()) if n > 1], "")
    track_gaps = []
    for track, points in tracks.items():
        points.sort(key=lambda p: p[0])
        for (t1, r1), (t2, _) in zip(points, points[1:]):
            if store.MAX_STEP_S < t2 - t1 <= TRACK_GAP_MAX_S:
                track_gaps.append(f"track {track} {r1['callsign'] or ''} at {_local(t1)}: {t2 - t1:.0f} s")
    report.finding("Radar", f"gaps of {store.MAX_STEP_S}-{TRACK_GAP_MAX_S} s within a track", track_gaps,
                   "the closest approach may fall in a gap", warn=False)
    report.finding("Radar", "positions without a height",
                   [f"{r['time_utc']} track {r['track']}" for _, r in positions if _float(r.get("height_m")) is None],
                   "counted as 0 m when matching")
    hlo, hhi = HEIGHT_RANGE_M
    odd = []
    for _, r in positions:
        h, s = _float(r.get("height_m")), _float(r.get("speed_ms"))
        if (h is not None and not hlo <= h <= hhi) or (s is not None and not 0 <= s <= SPEED_MAX_MS):
            odd.append(f"{r['time_utc']} track {r['track']}: height {r.get('height_m')} m, speed {r.get('speed_ms')} m/s")
    report.finding("Radar", "implausible heights or speeds", odd, "")
    return report


def write_json(report, path):
    with open(path, "w") as f:
        json.dump(report.as_dict(), f, indent=1)

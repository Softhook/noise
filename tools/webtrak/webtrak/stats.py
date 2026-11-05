"""Summary statistics for one monitor over a period, read from its saved CSV files.

Levels are 1 s values; percentile levels L10/L50/L90 are the levels exceeded 10/50/90% of the
valid seconds (L90 is the usual measure of background). Seconds WebTrak marked as having no
measurement (blank level_db) are left out. The aircraft share is the energy of the class 1 events
(from their SEL) as a fraction of all the sound energy over the valid seconds.
"""

from __future__ import annotations

import calendar
import collections
import csv
import datetime as dt
import math
import os
import statistics

from . import parse, store

QUARTER_S = 15 * 60


def _utc(text):
    """Seconds for '2026-11-05T12:00:00Z' or '2026-11-05T12:00:00+00:00'."""
    if text.endswith("Z"):
        return calendar.timegm(dt.datetime.fromisoformat(text[:-1]).timetuple())
    return dt.datetime.fromisoformat(text).timestamp()


def energy_mean(levels):
    levels = list(levels)
    if not levels:
        return None
    return 10 * math.log10(sum(10 ** (v / 10) for v in levels) / len(levels))


def exceeded(levels, percent):
    """The level exceeded percent% of the time."""
    ordered = sorted(levels, reverse=True)
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, int(len(ordered) * percent / 100))]


def local_days(start, end):
    zone = parse.site_zone()
    day = dt.datetime.fromtimestamp(start, zone).date()
    last = dt.datetime.fromtimestamp(max(start, end - 1), zone).date()
    while day <= last:
        yield day.isoformat()
        day += dt.timedelta(days=1)


def _rows(path):
    try:
        with open(path, newline="") as f:
            yield from csv.DictReader(f)
    except OSError:
        return


def read_levels(monitor_dir, start, end):
    """[(utc, level or None, flag)] for start <= utc < end, in time order."""
    out = []
    for day in local_days(start, end):
        for row in _rows(os.path.join(monitor_dir, "levels", f"{day}.csv")):
            try:
                t = _utc(row["time_utc"])
                level = float(row["level_db"]) if row["level_db"] else None
            except (KeyError, TypeError, ValueError):
                continue  # a line being written as we read
            if start <= t < end:
                out.append((t, level, row.get("flag", "")))
    out.sort(key=lambda item: item[0])
    return out


def read_events(monitor_dir, start, end):
    """Event rows with their LAmax time from start up to end, in time order."""
    out = []
    for row in _rows(os.path.join(monitor_dir, "events.csv")):
        try:
            t = _utc(row["lmax_time_local"])
            event = {"t": t, "lmax": float(row["lmax_db"]), "sel": float(row["sel_db"]),
                     "leq": float(row["leq_db"]), "duration": float(row["duration_s"]),
                     "event_class": row["event_class"], "callsign": row["callsign"], "type": row["type"],
                     "direction": row["direction"], "airport": row["airport"], "track": row["track"],
                     "slant": int(row["closest_slant_m"]) if row["closest_slant_m"] else None,
                     "height": int(row["closest_height_m"]) if row["closest_height_m"] else None}
        except (KeyError, TypeError, ValueError):
            continue
        if start <= t < end:
            out.append(event)
    out.sort(key=lambda e: e["t"])
    return out


def _round(value, places=1):
    return None if value is None else round(value, places)


def summary(monitor_dir, start, end, bucket_s=60):
    """Everything the statistics view shows, as plain JSON-ready values."""
    levels = read_levels(monitor_dir, start, end)
    valid = [(t, v) for t, v, _ in levels if v is not None]
    values = [v for _, v in valid]
    outside_events = [v for _, v, flag in levels if v is not None and flag != "1"]
    events = read_events(monitor_dir, start, end)
    state = store.read_state(monitor_dir)
    first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)

    buckets = collections.defaultdict(list)
    for t, v in valid:
        buckets[int(t // bucket_s * bucket_s)].append(v)
    series = [{"t": b, "laeq": _round(energy_mean(vs)), "max": max(vs)} for b, vs in sorted(buckets.items())]

    quarters = []
    q = int(start // QUARTER_S * QUARTER_S)
    while q < end:
        qv = [v for t, v in valid if q <= t < q + QUARTER_S]
        qe = [e for e in events if q <= e["t"] < q + QUARTER_S]
        if qv or qe:
            quarters.append({"t": q, "laeq": _round(energy_mean(qv)), "l90": exceeded(qv, 90),
                             "max": max(qv) if qv else None, "events": len(qe),
                             "aircraft": sum(1 for e in qe if e["event_class"] == "1")})
        q += QUARTER_S

    total = energy_mean(values)
    aircraft = [e for e in events if e["event_class"] == "1"]
    share = laeq_aircraft = None
    if values and aircraft:
        laeq_aircraft = 10 * math.log10(sum(10 ** (e["sel"] / 10) for e in aircraft) / len(values))
        share = 100 * 10 ** ((laeq_aircraft - total) / 10)

    types = []
    by_type = collections.defaultdict(list)
    for e in aircraft:
        if e["track"]:
            by_type[e["type"] or "?"].append(e)
    for name, group in sorted(by_type.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        slants = [e["slant"] for e in group if e["slant"] is not None]
        types.append({"type": name, "count": len(group),
                      "lmax": _round(statistics.median(e["lmax"] for e in group)),
                      "sel": _round(statistics.median(e["sel"] for e in group)),
                      "slant": round(statistics.median(slants)) if slants else None})

    return {
        "start": start, "end": end,
        "coverage": {"chunks": last - first + 1,
                     "saved": store.count_saved(state.get("saved", []), first, last),
                     "seconds": len(levels), "valid_seconds": len(values),
                     "no_measurement_seconds": len(levels) - len(values),
                     "pending_events": len(state.get("pending", []))},
        "laeq": _round(total), "l10": exceeded(values, 10), "l50": exceeded(values, 50),
        "l90": exceeded(values, 90), "lmax": max(values) if values else None,
        "laeq_outside_events": _round(energy_mean(outside_events)),
        "events": len(events), "aircraft_events": len(aircraft),
        "matched_events": sum(1 for e in events if e["track"]),
        "laeq_aircraft": _round(laeq_aircraft), "aircraft_share": _round(share, 0),
        "series": series, "bucket_s": bucket_s, "quarters": quarters, "types": types,
        "event_list": events,
    }

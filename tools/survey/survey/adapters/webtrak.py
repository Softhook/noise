"""WebTrak: the airport's radar tracks, and noise monitors' events and 1 s levels, from tools/webtrak's raw chunk cache.

Each saved chunk holds every monitor and all the radar, so this reads the raw cache, through
tools/webtrak's own parser, rather than the per-monitor CSVs (which only keep radar within 3 km).
Only this module imports the webtrak package, as ARCHITECTURE.md requires of adapters.

Manifest entry:
    "webtrak": {"adapter": "webtrak", "tool": "../webtrak", "site_dir": "../webtrak/data/lcy",
                "monitors": {"nmt6": "106"}}

`monitors` maps a receptor to its WebTrak monitor id. Heights are WebTrak's altitude above sea
level, of kind `radar`, since we don't know how WebTrak derives them.
"""

from __future__ import annotations

import gzip
import os
import sys

from ..common import iso, registration
from ..geometry import Frame, distance_m

TRACK_GAP_S = 600  # A track id seen again after this long is a new flight


def _webtrak(tool):
    if tool not in sys.path:
        sys.path.insert(0, tool)
    from webtrak import parse  # noqa: E402  (only here, so the core never loads it)
    return parse


def limits(receptors, max_km):
    """What the source can see (explain.py's limits): radar at any height, within max_km of any
    receptor, as read() keeps it."""
    return {"ceiling_m": None, "areas": [("circle", r["lat"], r["lon"], max_km) for r in receptors.values()], "any": True}


def read(name, spec, start, end, receptors, max_km, warnings):
    """(flights, positions, noise_events, levels, coverage) rows for start to end."""
    parse = _webtrak(spec["tool"])
    raw_dir = os.path.join(spec["site_dir"], "raw")
    monitors = {str(mid): rid for rid, mid in (spec.get("monitors") or {}).items() if rid in receptors}
    frames = [Frame(r["lat"], r["lon"]) for r in receptors.values()]
    limit = max_km * 1000
    first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
    tracks, events, levels, saved, unreadable = {}, {}, {}, [], 0
    for handle in range(first, last + 1):
        t0 = parse.utc_for_handle(handle)
        path = os.path.join(raw_dir, iso(t0)[:10], f"{handle}.txt.gz")
        if not os.path.exists(path):
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                chunk = parse.parse_chunk(f.read(), handle)
        except (OSError, EOFError, parse.NotAvailable):
            unreadable += 1
            continue
        saved.append(handle)
        for p in chunk.positions:
            if not start <= p.utc < end or min(distance_m(fr, p.lat, p.lon) for fr in frames) > limit:
                continue
            tracks.setdefault(p.track, {})[p.utc] = p  # Keyed on time: a chunk can repeat a position
        for e in chunk.events:
            rid = monitors.get(str(e.monitor))
            if rid and start <= e.lmax_time < end:
                events[(rid, round(e.start))] = e
        for lv in chunk.levels:
            rid = monitors.get(str(lv.monitor))
            if rid and lv.valid and start <= lv.utc < end:
                levels[(rid, lv.utc)] = lv
    if unreadable:
        warnings.append(f"{name}: {unreadable} saved chunks couldn't be read")

    flights, positions = [], []
    for track, by_time in tracks.items():
        pts = [by_time[t] for t in sorted(by_time)]
        groups = [[pts[0]]]
        for p in pts[1:]:
            if p.utc - groups[-1][-1].utc <= TRACK_GAP_S:
                groups[-1].append(p)
            else:
                groups.append([p])
        for group in groups:
            head = group[0]
            source_id = f"{track}-{iso(head.utc)[:19].replace('-', '').replace(':', '')}"
            reg = registration(head.registration)
            callsign = head.callsign if head.callsign and registration(head.callsign) != reg else ""
            flights.append({
                "source": name, "source_id": source_id, "first_utc": iso(head.utc), "last_utc": iso(group[-1].utc),
                "registration": reg, "callsign": callsign, "callsign_kind": "iata" if callsign else "",
                "type": head.aircraft_type, "squawk": head.squawk, "direction": head.direction,
                "origin": head.origin, "destination": head.destination, "hex": "",
            })
            positions += [{
                "source": name, "source_id": source_id, "t": round(p.utc, 2), "lat": p.lat, "lon": p.lon,
                "height_m": p.altitude_m, "height_kind": "radar", "speed_ms": p.speed_ms,
            } for p in group]

    noise = [{
        "source": name, "receptor": rid, "start_utc": iso(e.start), "lmax_utc": iso(e.lmax_time),
        "end_utc": iso(e.end), "lmax_db": e.lmax, "sel_db": e.sel, "leq_db": e.leq, "event_class": e.event_class,
    } for (rid, _), e in sorted(events.items(), key=lambda kv: kv[1].lmax_time)]
    level_rows = [{"source": name, "receptor": rid, "t": round(t, 1), "level_db": lv.level, "flag": lv.flag}
                  for (rid, t), lv in sorted(levels.items(), key=lambda kv: kv[0][1])]

    coverage, run = [], None
    for handle in saved + [None]:
        if run and handle == run[1] + 1:
            run[1] = handle
            continue
        if run:
            coverage.append({"source": name, "start_utc": iso(parse.utc_for_handle(run[0])),
                             "end_utc": iso(parse.utc_for_handle(run[1]) + parse.WINDOW_S), "note": "saved chunks"})
        run = [handle, handle] if handle is not None else None
    return flights, positions, noise, level_rows, coverage

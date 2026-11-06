"""Build a deployment: run its adapters, work out closest approaches, link passes, write the tables.

    python3 -m survey build --manifest ../deployments/2026-11-05.json

Writes data/<deployment>/common/ (a CSV per table, and a folder of daily CSVs for positions and
levels) and build.json (counts, coverage and warnings), which the
survey app reads. The sources' own files are only ever read.

The steps, each a function here, in order:
    read_sources   each source's adapter -> the source tables, a time-ordered track per flight,
                   and what each source can see
    approaches     each flight's closest approach to each receptor
    link           flights -> passes (link.py)
    unseen         why a source has no flight in a pass (explain.py)
A step still to be built (match, resolve, checks) goes in build() between these.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import glob
import os
import shutil
import sys

from . import adapters, explain, link, manifest, schema
from .common import day_of, iso, rounded
from .geometry import Frame, closest_approach


class Busy(Exception):
    """Another build of the same deployment is running."""


@contextlib.contextmanager
def build_lock(m, wait=True):
    """Held for the whole of a build, so two builds of one deployment never swap tables at once,
    whether they're started by `make build` or the app's Rebuild. A lock file beside the
    deployment's folder, not in it, so the folder holds only what the build writes. The lock goes
    when the process does, so a build that crashes never leaves it held. wait=False: raise Busy
    instead of waiting for the other build."""
    parent = os.path.dirname(m["out_dir"])
    os.makedirs(parent, exist_ok=True)
    with open(os.path.join(parent, f".{m['deployment']}.build.lock"), "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise Busy(f"{m['deployment']} is being built by another process; try again when it's done") from None
        yield


def clear_leftovers(m):
    """Remove the staging and old tables folders a build that was killed part-way left behind."""
    for path in glob.glob(os.path.join(m["out_dir"], ".common.*")):
        shutil.rmtree(path, ignore_errors=True)


def read_sources(m, warnings, log):
    """Every source in the manifest, through its adapter: (tables, tracks, levels, limits).

    tables: {"flights", "noise_events", "coverage": rows}; tracks: {(source, source_id): track},
    each a time-ordered list of (t, lat, lon, height_m, height_kind, speed_ms); levels: [(source,
    receptor, t, level_db, flag)]; limits: {source: what it can see}. Positions and levels are
    turned into tuples as each adapter gives them, so a long deployment's millions of rows are
    never all held as dicts."""
    context = adapters.context(m)
    tables = {name: [] for name in ("flights", "noise_events", "coverage")}
    tracks, levels, limits = {}, [], {}
    for name, spec in m["sources"].items():
        adapter = adapters.ADAPTERS[spec["adapter"]]
        got = adapter.read(name, spec, context, warnings)
        counts = {}
        for table in tables:
            rows = list(got.get(table, ()))
            tables[table] += rows
            counts[table] = len(rows)
        counts["positions"] = 0
        for p in got.get("positions", ()):
            tracks.setdefault((p["source"], p["source_id"]), []).append(
                (p["t"], p["lat"], p["lon"], p["height_m"], p["height_kind"], p["speed_ms"]))
            counts["positions"] += 1
        before = len(levels)
        levels += ((lv["source"], lv["receptor"], lv["t"], lv["level_db"], lv["flag"]) for lv in got.get("levels", ()))
        counts["levels"] = len(levels) - before
        limits[name] = adapter.limits(spec, context)
        print(f"{name}: " + ", ".join(f"{counts[t]} {t.replace('_', ' ')}"
                                      for t in ("flights", "positions", "noise_events", "levels")), file=log)
    for points in tracks.values():
        points.sort(key=lambda p: p[0])
    levels.sort(key=lambda lv: (lv[2], lv[0], lv[1]))
    return tables, tracks, levels, limits


def position_parts(tracks, flights):
    """The positions table, as {day: rows}: each track whole, in the file for the day of its
    flight's first_utc (schema.PARTITIONED), tracks in key order."""
    first = {(f["source"], f["source_id"]): f["first_utc"][:10] for f in flights}
    by_day = {}
    for key in sorted(tracks):
        by_day.setdefault(first.get(key) or day_of(tracks[key][0][0]), []).append(key)

    def rows(keys):
        for key in keys:
            for t, lat, lon, height, kind, speed in tracks[key]:
                yield {"source": key[0], "source_id": key[1], "t": t, "lat": lat, "lon": lon,
                       "height_m": height, "height_kind": kind, "speed_ms": speed}

    return {day: rows(keys) for day, keys in by_day.items()}


def level_parts(levels):
    """The levels table, as {day: rows}, by each level's own time."""
    by_day = {}
    for source, receptor, t, db, flag in levels:
        by_day.setdefault(day_of(t), []).append(
            {"source": source, "receptor": receptor, "t": t, "level_db": db, "flag": flag})
    return by_day


def approaches(tracks, receptors):
    """{(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)}"""
    found = {}
    for r in receptors.values():
        frame = Frame(r["lat"], r["lon"])
        mic = None
        if r["ground_elevation_m"] is not None:
            mic = float(r["ground_elevation_m"]) + float(r["mic_height_m"] or 0)
        for key, points in tracks.items():
            got = closest_approach(points, frame, mic)
            if got:
                found[(*key, r["id"])] = got
    return found


def approach_rows(found):
    return [{"source": s, "source_id": sid, "receptor": rid, "t": iso(t), "ground_m": rounded(g),
             "height_m": rounded(h), "slant_m": rounded(sl), "at_track_end": "1" if end else ""}
            for (s, sid, rid), (t, g, h, sl, end) in sorted(found.items())]


def receptor_rows(receptors):
    return [{**{key: r[key] for key in schema.TABLES["receptors"]}, "public": "1" if r["public"] else ""}
            for r in receptors.values()]


def summarise(m, tables, tracks, warnings):
    """build.json: when, what went in, and what came out."""
    linked = {}
    for row in tables["passes"]:
        linked.setdefault(row["pass_id"], set()).add(row["source"])

    def count(table, source):
        return sum(1 for row in tables[table] if row["source"] == source)

    return {
        "deployment": m["deployment"],
        "description": m["description"],
        "manifest": m["path"],
        "built_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_utc": [iso(m["start"]), iso(m["end"])],
        "receptors": list(m["receptors"]),
        "sources": {name: {"adapter": spec["adapter"], "flights": count("flights", name),
                           "positions": sum(len(pts) for (s, _), pts in tracks.items() if s == name)}
                    for name, spec in m["sources"].items()},
        "passes": len(linked),
        "passes_in_several_sources": sum(1 for s in linked.values() if len(s) > 1),
        "unseen": {reason: sum(1 for u in tables["unseen"] if u["reason"] == reason) for reason in explain.REASONS},
        "warnings": warnings,
    }


def build(m, log=None, wait=True):
    """Build manifest m (from manifest.load). Returns the build summary. If another build of it is
    running, waits for it to finish, or with wait=False raises Busy."""
    with build_lock(m, wait):
        clear_leftovers(m)
        return _build(m, log or sys.stderr)


def _build(m, log):
    warnings = list(m["warnings"])
    tables, tracks, levels, limits = read_sources(m, warnings, log)

    tables["flights"] = [f for f in tables["flights"] if (f["source"], f["source_id"]) in tracks]
    found = approaches(tracks, m["receptors"])
    passes = link.link(tables["flights"], tracks, found, m["pass_receptor"])
    tables.update({
        "receptors": receptor_rows(m["receptors"]),
        # By day, and in track order within a day, so a reader can take each track's positions as they come
        "positions": position_parts(tracks, tables["flights"]),
        "levels": level_parts(levels),
        "approaches": approach_rows(found),
        "passes": passes,
        "unseen": explain.unseen_rows(passes, tracks, limits, tables["coverage"]),
    })

    out = os.path.join(m["out_dir"], "common")
    schema.write_tables(out, {name: tables[name] for name in schema.TABLES})
    summary = summarise(m, tables, tracks, warnings)
    schema.write_json(os.path.join(m["out_dir"], "build.json"), summary)
    for w in warnings:
        print(f"WARNING: {w}", file=log)
    print(f"{summary['passes']} passes, {summary['passes_in_several_sources']} seen by more than one source, "
          f"{summary['unseen'][explain.UNEXPLAINED]} missed by a source that should have seen them "
          f"-> {os.path.relpath(out)}", file=log)
    return summary


def main(args):
    build(manifest.load(args.manifest))
    return 0

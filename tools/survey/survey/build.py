"""Build a deployment: run its adapters, work out closest approaches, link passes, write the tables.

    python3 -m survey build --manifest ../deployments/2026-11-05.json

Writes data/<deployment>/common/*.csv and build.json (counts, coverage and warnings), which the
survey app reads. The sources' own files are only ever read.

The steps, each a function here, in order:
    read_sources   each source's adapter -> the source tables, and what each source can see
    group_tracks   positions -> one time-ordered track per flight
    approaches     each flight's closest approach to each receptor
    link           flights -> passes (link.py)
    unseen         why a source has no flight in a pass (explain.py)
A step still to be built (match, resolve, checks) goes in build() between these.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

from . import adapters, explain, link, manifest, schema
from .common import iso, rounded
from .geometry import Frame, closest_approach


def read_sources(m, warnings, log):
    """({table: rows} for schema.SOURCE_TABLES, {source: limits}) from every source in the manifest."""
    context = adapters.context(m)
    tables = {name: [] for name in schema.SOURCE_TABLES}
    limits = {}
    for name, spec in m["sources"].items():
        adapter = adapters.ADAPTERS[spec["adapter"]]
        got = adapter.read(name, spec, context, warnings)
        for table, rows in got.items():
            tables[table] += rows
        limits[name] = adapter.limits(spec, context)
        counts = ", ".join(f"{len(got.get(t, []))} {t.replace('_', ' ')}"
                           for t in ("flights", "positions", "noise_events", "levels"))
        print(f"{name}: {counts}", file=log)
    return tables, limits


def group_tracks(positions):
    """{(source, source_id): [position dicts, time-ordered]}"""
    tracks = {}
    for p in positions:
        tracks.setdefault((p["source"], p["source_id"]), []).append(p)
    for points in tracks.values():
        points.sort(key=lambda p: p["t"])
    return tracks


def approaches(tracks, receptors):
    """{(source, source_id, receptor): (t, ground_m, height_m, slant_m, at_track_end)}"""
    found = {}
    for r in receptors.values():
        frame = Frame(r["lat"], r["lon"])
        mic = None
        if r["ground_elevation_m"] is not None:
            mic = float(r["ground_elevation_m"]) + float(r["mic_height_m"] or 0)
        for key, points in tracks.items():
            got = closest_approach([(p["t"], p["lat"], p["lon"], p["height_m"]) for p in points], frame, mic)
            if got:
                found[(*key, r["id"])] = got
    return found


def approach_rows(found):
    return [{"source": s, "source_id": sid, "receptor": rid, "t": iso(t), "ground_m": rounded(g),
             "height_m": rounded(h), "slant_m": rounded(sl), "at_track_end": "1" if end else ""}
            for (s, sid, rid), (t, g, h, sl, end) in sorted(found.items())]


def receptor_rows(receptors):
    return [{key: r[key] for key in schema.TABLES["receptors"]} for r in receptors.values()]


def summarise(m, tables, warnings):
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
                           "positions": count("positions", name)}
                    for name, spec in m["sources"].items()},
        "passes": len(linked),
        "passes_in_several_sources": sum(1 for s in linked.values() if len(s) > 1),
        "unseen": {reason: sum(1 for u in tables["unseen"] if u["reason"] == reason) for reason in explain.REASONS},
        "warnings": warnings,
    }


def build(m, log=None):
    """Build manifest m (from manifest.load). Returns the build summary."""
    log = log or sys.stderr
    warnings = list(m["warnings"])
    tables, limits = read_sources(m, warnings, log)

    tracks = group_tracks(tables["positions"])
    tables["flights"] = [f for f in tables["flights"] if (f["source"], f["source_id"]) in tracks]
    found = approaches(tracks, m["receptors"])
    passes = link.link(tables["flights"], tracks, found, m["pass_receptor"])
    tables.update({
        "receptors": receptor_rows(m["receptors"]),
        # In track order, so a reader can take each track's positions as they come
        "positions": [p for _, points in sorted(tracks.items()) for p in points],
        "approaches": approach_rows(found),
        "passes": passes,
        "unseen": explain.unseen_rows(passes, tracks, limits, tables["coverage"]),
    })

    out = os.path.join(m["out_dir"], "common")
    schema.write_tables(out, {name: tables[name] for name in schema.TABLES})
    summary = summarise(m, tables, warnings)
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

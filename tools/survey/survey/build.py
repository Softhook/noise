"""Build a deployment: run its adapters, work out closest approaches, link passes, write the tables.

    python3 -m survey build --manifest ../deployments/2026-11-05.json

Writes data/<deployment>/common/*.csv and build.json (counts, coverage and warnings), which the
survey app reads. The sources' own files are only ever read.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

from . import explain, link, manifest, schema
from .adapters import adsb, webtrak
from .common import iso, parse_time, rounded
from .geometry import Frame, closest_approach


def receptor_rows(receptors):
    return [{key: r[key] for key in schema.TABLES["receptors"]} for r in receptors.values()]


def approaches_for(tracks, receptors):
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


def build(m, log=None):
    """Build manifest m (from manifest.load). Returns the build summary."""
    log = log or sys.stderr
    warnings = list(m["warnings"])
    flights, positions, noise, levels, coverage, limits = [], [], [], [], [], {}
    for name, spec in m["sources"].items():
        if spec["adapter"] == "adsb":
            f, p, c = adsb.read(name, spec, m["start"], m["end"], warnings)
            n, lv = [], []
            limits[name] = adsb.limits(spec)
        else:
            f, p, n, lv, c = webtrak.read(name, spec, m["start"], m["end"], m["receptors"], m["max_km"], warnings)
            limits[name] = webtrak.limits(m["receptors"], m["max_km"])
        print(f"{name}: {len(f)} flights, {len(p)} positions, {len(n)} noise events, {len(lv)} levels", file=log)
        flights += f
        positions += p
        noise += n
        levels += lv
        coverage += c

    tracks = {}
    for p in positions:
        tracks.setdefault((p["source"], p["source_id"]), []).append(p)
    for points in tracks.values():
        points.sort(key=lambda p: p["t"])
    flights = [f for f in flights if (f["source"], f["source_id"]) in tracks]
    approaches = approaches_for(tracks, m["receptors"])
    first = next(iter(m["receptors"]))
    passes = link.link(flights, tracks, approaches, first)
    unseen = explain.unseen_rows(passes, tracks, limits, coverage)

    out = os.path.join(m["out_dir"], "common")
    schema.write_table(out, "receptors", receptor_rows(m["receptors"]))
    schema.write_table(out, "flights", flights)
    schema.write_table(out, "positions", positions)
    schema.write_table(out, "noise_events", noise)
    schema.write_table(out, "levels", levels)
    schema.write_table(out, "coverage", coverage)
    schema.write_table(out, "approaches", [
        {"source": s, "source_id": sid, "receptor": rid, "t": iso(t), "ground_m": rounded(g),
         "height_m": rounded(h), "slant_m": rounded(sl), "at_track_end": "1" if end else ""}
        for (s, sid, rid), (t, g, h, sl, end) in sorted(approaches.items())])
    schema.write_table(out, "passes", passes)
    schema.write_table(out, "unseen", unseen)

    linked = {}
    for row in passes:
        linked.setdefault(row["pass_id"], set()).add(row["source"])
    summary = {
        "deployment": m["deployment"],
        "description": m["description"],
        "manifest": m["path"],
        "built_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_utc": [iso(m["start"]), iso(m["end"])],
        "receptors": list(m["receptors"]),
        "sources": {name: {"adapter": spec["adapter"],
                           "flights": sum(1 for f in flights if f["source"] == name),
                           "positions": sum(1 for p in positions if p["source"] == name)}
                    for name, spec in m["sources"].items()},
        "passes": len(linked),
        "passes_in_several_sources": sum(1 for s in linked.values() if len(s) > 1),
        "unseen": {reason: sum(1 for u in unseen if u["reason"] == reason) for reason in explain.REASONS},
        "warnings": warnings,
    }
    with open(os.path.join(m["out_dir"], "build.json"), "w") as f:
        json.dump(summary, f, indent=2)
    for w in warnings:
        print(f"WARNING: {w}", file=log)
    print(f"{summary['passes']} passes, {summary['passes_in_several_sources']} seen by more than one source, "
          f"{summary['unseen'][explain.UNEXPLAINED]} missed by a source that should have seen them "
          f"-> {os.path.relpath(out)}", file=log)
    return summary


def main(args):
    m = manifest.load(args.manifest)
    build(m)
    return 0

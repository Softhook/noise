"""Tests for the survey package, on made-up data in temporary folders. Nothing touches the network."""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import html
import http.client
import http.server
import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from unittest import mock

from survey import adapters, build, explain, fleet, link, manifest, registers, resolve, schema, server
from survey.app import TRACK_SPACING_S, App, BadRequest, minutes_covered
from survey.adapters import adsb, webtrak
from survey.common import iso, parse_time, registration
from survey.geometry import Frame, closest_approach, path_angle

TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NMT6 = (51.50535, 0.11075)
T0 = parse_time("2026-11-05T09:00:00Z")  # GMT, so WebTrak's local times are UTC
M_PER_DEG_LAT = 111250.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(NMT6[0]))


def at(east_m, north_m):
    return NMT6[0] + north_m / M_PER_DEG_LAT, NMT6[1] + east_m / M_PER_DEG_LON


def westbound(t_abeam, north_m=-210.0, span_s=60, speed=70.0, height_at_abeam=330.0):
    """(t, lat, lon, height) once a second, flying west and descending, passing north_m from NMT6 at t_abeam."""
    pts = []
    for s in range(-span_s, span_s + 1):
        lat, lon = at(-s * speed, north_m)
        pts.append((t_abeam + s, lat, lon, height_at_abeam - s * speed * math.tan(math.radians(5.5))))
    return pts


def window(start, end, receptors=None, max_km=15):
    """An adapter's Context, for start to end."""
    return adapters.Context(start, end, receptors or {}, max_km)


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def adsb_results(folder, flights):
    """An adsb analyse results folder. flights: [(hex, registration, callsign, type, points)]."""
    frows, prows = [], []
    for i, (hexcode, reg, call, kind, pts) in enumerate(flights, 1):
        frows.append({"flight_id": i, "hex": hexcode, "callsign": call, "type": kind, "registration": reg,
                      "label": "rwy27_arrival", "first_seen_utc": iso(pts[0][0]), "last_seen_utc": iso(pts[-1][0]),
                      "height_source": "geometric"})
        prows += [{"flight_id": i, "hex": hexcode, "emission_time_utc": iso(t), "lat": lat, "lon": lon,
                   "height_used_amsl_m": round(h, 1), "ground_speed_kt": 136} for t, lat, lon, h in pts]
    write_csv(os.path.join(folder, "flights.csv"), list(frows[0]), frows)
    write_csv(os.path.join(folder, "positions.csv"), list(prows[0]), prows)
    with open(os.path.join(folder, "summary.txt"), "w") as f:
        f.write(f"Time covered: {iso(T0 - 3600)} to {iso(T0 + 3600)}\n")


def local(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def webtrak_chunks(site_dir, tracks, levels=(), events=()):
    """Raw WebTrak chunks. tracks: [(track id, registration, type, points)]; levels: [(t, dB)];
    events: [(lmax time, LAmax)]. Monitor 106."""
    by_handle = {}
    for track, reg, kind, pts in tracks:
        for t, lat, lon, h in pts[::4]:  # Radar every 4 s
            by_handle.setdefault(int(t // 30), []).append(
                f"radar,{local(t)},{track},A,LCY,{kind},,0,{lon:.5f},{lat:.5f},{h - 6:.0f},70,{reg},7000,DUB,LCY,,,{h:.0f}")
    for t, db in levels:
        by_handle.setdefault(int(t // 30), []).append(f"noise,{local(t)},106,106,1,{db}")
    for t, lmax in events:
        by_handle.setdefault(int(t // 30), []).append(
            f"event,{local(t - 10)},106,106,1,{lmax},{local(t)},{lmax + 8},{lmax - 5},0,20,{local(t + 10)}")
    for handle, lines in by_handle.items():
        start = handle * 30
        path = os.path.join(site_dir, "raw", iso(start)[:10], f"{handle}.txt.gz")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with gzip.open(path, "wt") as f:
            f.write(f'<data endTime="x" handle="{handle}" radarStatus="online" startTime="'
                    f'{dt.datetime.fromtimestamp(start, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}" type="data">'
                    + "\n".join(lines) + "\n</data>")


class Common(unittest.TestCase):
    def test_registration_is_normalised(self):
        self.assertEqual(registration("G-LCYN"), "GLCYN")
        self.assertEqual(registration("glcyn "), "GLCYN")
        self.assertEqual(registration(None), "")

    def test_times_need_a_zone(self):
        self.assertEqual(parse_time("2026-11-05T09:00:00Z"), T0)
        with self.assertRaises(ValueError):
            parse_time("2026-11-05T09:00:00")


class Geometry(unittest.TestCase):
    def test_closest_approach_between_positions(self):
        frame = Frame(*NMT6)
        pts = westbound(T0)[::10]  # Positions 700 m apart, none abeam exactly
        t, ground, height, slant, end = closest_approach(pts, frame, 6.0)
        self.assertAlmostEqual(t, T0, delta=0.5)
        self.assertAlmostEqual(ground, 210, delta=2)
        self.assertAlmostEqual(height, 330, delta=2)
        self.assertAlmostEqual(slant, math.hypot(ground, height - 6), delta=0.1)
        self.assertFalse(end)

    def test_closest_point_at_the_end_of_a_track_is_flagged(self):
        frame = Frame(*NMT6)
        after = [p for p in westbound(T0) if p[0] > T0 + 20]  # The track starts after passing NMT6
        self.assertTrue(closest_approach(after, frame)[4])

    def test_a_hole_in_a_track_isnt_interpolated_across(self):
        # The source lost the aircraft for 60 s around NMT6: a line across the hole would put the
        # closest approach abeam, 210 m away, though no position was ever there
        frame = Frame(*NMT6)
        holed = [p for p in westbound(T0) if abs(p[0] - T0) > 30]
        t, ground, _, _, edge = closest_approach(holed, frame)
        self.assertGreater(ground, 2000)
        self.assertTrue(edge)  # At the hole's edge, so it may have come closer
        # A short gap is still interpolated
        t, ground, _, _, edge = closest_approach([p for p in westbound(T0) if abs(p[0] - T0) > 10], frame)
        self.assertAlmostEqual(ground, 210, delta=2)
        self.assertFalse(edge)

    def test_path_angle_is_fitted_near_the_closest_approach(self):
        frame = Frame(*NMT6)
        self.assertAlmostEqual(path_angle(westbound(T0), frame, T0), -5.5, delta=0.05)  # Descending
        climbing = [(2 * T0 - t, lat, lon, h) for t, lat, lon, h in reversed(westbound(T0))]
        self.assertAlmostEqual(path_angle(climbing, frame, T0), 5.5, delta=0.05)
        # Only the 3 km either side counts: a steeper stretch further out doesn't change it
        bent = [(t, lat, lon, h + (max(0, T0 - 50 - t) * 70 * 0.1)) for t, lat, lon, h in westbound(T0)]
        self.assertAlmostEqual(path_angle(bent, frame, T0), -5.5, delta=0.05)

    def test_path_angle_needs_enough_heights_and_no_hole(self):
        frame = Frame(*NMT6)
        self.assertIsNone(path_angle([(t, lat, lon, None) for t, lat, lon, _ in westbound(T0)], frame, T0))
        self.assertIsNone(path_angle([p for p in westbound(T0) if abs(p[0] - T0) <= 5], frame, T0))  # Under 1 km
        # Across a hole, only the side of it the closest approach is on is fitted, so a jump in
        # height across the hole doesn't tilt the line
        holed = [(t, lat, lon, h + (300 if t > T0 + 20 else 0)) for t, lat, lon, h in westbound(T0) if not T0 + 10 < t <= T0 + 50]
        self.assertAlmostEqual(path_angle(holed, frame, T0), -5.5, delta=0.05)
        self.assertIsNone(path_angle([], frame, T0))


class Manifests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def write(self, **extra):
        spec = {"window_utc": ["2026-11-05T00:00:00Z", "2026-11-06T00:00:00Z"],
                "receptors": {"nmt6": {"lat": NMT6[0], "lon": NMT6[1], "label": "NMT6", "public": True},
                              "garden": {"config": "private/site.json"}},
                "sources": {"opensky": {"adapter": "adsb", "results": "results"}, "adsb": None}}
        spec.update(extra)
        path = os.path.join(self.dir, "d1.json")
        with open(path, "w") as f:
            json.dump(spec, f)
        return path

    def test_paths_are_relative_to_the_manifest_and_null_sources_are_off(self):
        m = manifest.load(self.write())
        self.assertEqual(list(m["sources"]), ["opensky"])
        self.assertEqual(m["sources"]["opensky"]["results"], os.path.join(self.dir, "results"))
        self.assertEqual(m["deployment"], "d1")

    def test_a_private_receptor_comes_from_its_config_or_is_left_out(self):
        m = manifest.load(self.write())
        self.assertEqual(list(m["receptors"]), ["nmt6"])
        self.assertIn("garden", m["warnings"][0])
        os.makedirs(os.path.join(self.dir, "private"))
        with open(os.path.join(self.dir, "private", "site.json"), "w") as f:
            json.dump({"site": {"name": "Garden", "lat": 51.5, "lon": 0.1, "ground_elevation_m": 2, "mic_height_m": 3}}, f)
        m = manifest.load(self.write())
        self.assertEqual(m["receptors"]["garden"]["name"], "Garden")
        self.assertFalse(m["receptors"]["garden"]["public"])

    def test_pass_ids_are_dated_by_a_public_receptor_unless_the_manifest_names_one(self):
        os.makedirs(os.path.join(self.dir, "private"))
        with open(os.path.join(self.dir, "private", "site.json"), "w") as f:
            json.dump({"site": {"name": "Garden", "lat": 51.5, "lon": 0.1}}, f)
        receptors = {"garden": {"config": "private/site.json"},
                     "nmt6": {"lat": NMT6[0], "lon": NMT6[1], "public": True}}
        # The garden is listed first, but it's private, so it may be missing elsewhere
        self.assertEqual(manifest.load(self.write(receptors=receptors))["pass_receptor"], "nmt6")
        self.assertEqual(manifest.load(self.write(receptors=receptors, pass_receptor="garden"))["pass_receptor"], "garden")
        os.remove(os.path.join(self.dir, "private", "site.json"))
        m = manifest.load(self.write(receptors=receptors, pass_receptor="garden"))  # Named, but its site.json isn't there
        self.assertEqual(m["pass_receptor"], "nmt6")
        self.assertTrue(any("pass_receptor" in w for w in m["warnings"]))

    def test_bad_manifests_are_refused(self):
        with self.assertRaises(manifest.ManifestError):
            manifest.load(self.write(window_utc=["2026-11-05T00:00:00", "2026-11-06T00:00:00Z"]))
        with self.assertRaises(manifest.ManifestError):
            manifest.load(self.write(sources={"x": {"adapter": "fax"}}))


class Adapters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_adsb_results_become_flights_and_positions(self):
        folder = os.path.join(self.dir, "results")
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0))])
        warnings = []
        got = adsb.read("opensky", {"results": folder}, window(T0 - 3600, T0 + 3600), warnings)
        flights, positions, coverage = got["flights"], list(got["positions"]), got["coverage"]
        self.assertEqual(len(flights), 1)
        f = flights[0]
        self.assertEqual((f["registration"], f["direction"], f["hex"], f["callsign_kind"]), ("GLCYN", "A", "4006a1", "icao"))
        self.assertEqual(f["source_id"], "4006a1-20261105T085900")
        self.assertEqual(len(positions), 121)
        self.assertEqual(positions[0]["height_kind"], "geometric")
        self.assertEqual(warnings, [])
        self.assertEqual(coverage[0]["note"], "data")

    def test_a_flight_keeps_its_whole_track_when_the_window_ends_mid_flight(self):
        folder = os.path.join(self.dir, "results")
        # A slow 40-minute flight, for one that starts well before the window ends and passes NMT6 well after
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0, span_s=1200, speed=5))])
        positions = list(adsb.read("opensky", {"results": folder}, window(T0 - 3600, T0 - 900), [])["positions"])
        self.assertEqual(len(positions), 2401)
        pts = [(p["t"], p["lat"], p["lon"], p["height_m"]) for p in positions]
        self.assertFalse(closest_approach(pts, Frame(*NMT6))[4])  # Not cut short at the window's end

    def test_the_loggers_coverage_comes_from_its_health_log(self):
        folder, logs = os.path.join(self.dir, "results"), os.path.join(self.dir, "logs")
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0))])
        records = []
        for t in range(int(T0 - 3600), int(T0 + 3601), 300):
            if T0 + 600 < t < T0 + 1800:
                continue  # The logger stopped writing for 20 minutes: under summary.txt's 30-minute gaps
            record = {"time": t, "event": None, "connected": True, "lines": 5000, "clock": {"synchronised": True}}
            if t == T0 - 1800:
                record["clock"] = {"synchronised": False}
            records.append(record)
        records.append({"time": T0 + 2400 + 5, "event": "disconnected", "connected": False, "lines": 10})
        records.sort(key=lambda r: r["time"])
        os.makedirs(os.path.join(logs, "health"))
        with open(os.path.join(logs, "health", "2026-11-05.jsonl"), "w") as f:
            f.write("not json\n")
            for r in records:
                f.write(json.dumps(r) + "\n")
        coverage = adsb.read("adsb", {"results": folder, "logs": logs}, window(T0 - 3600, T0 + 3600), [])["coverage"]
        spans = [(parse_time(c["start_utc"]) - T0, parse_time(c["end_utc"]) - T0) for c in coverage]
        self.assertEqual({c["note"] for c in coverage}, {"health log"})
        # Not while the clock was unsynchronised (-1800), in the 20 minutes without records, or from
        # the disconnection (2405) to the next record that shows it connected again (2700)
        self.assertEqual(spans, [(-3600, -2100), (-1500, 600), (1800, 2400), (2700, 3600)])
        # A pass in the outage is then "no data", not a miss the logger should explain
        lim = explain.prepare({"ceiling_m": 3048.0, "areas": [("circle", *NMT6, 15.0)], "any": False})
        when = [(parse_time(c["start_utc"]), parse_time(c["end_utc"])) for c in coverage]
        self.assertEqual(explain.why_unseen(westbound(T0 + 1200), lim, when), explain.NO_DATA)
        self.assertEqual(explain.why_unseen(westbound(T0), lim, when), explain.UNEXPLAINED)

    def test_adsb_warns_when_positions_are_missing(self):
        folder = os.path.join(self.dir, "results")
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0))])
        with open(os.path.join(folder, "flights.csv"), "a") as f:
            f.write(f"2,4006a2,,,,other,{iso(T0)},{iso(T0 + 60)},geometric\n")
        warnings = []
        got = adsb.read("opensky", {"results": folder}, window(T0 - 3600, T0 + 3600), warnings)
        list(got["positions"])  # The warning comes once the positions have been read
        self.assertIn("--all-positions", warnings[0])

    def test_a_converted_sources_period_is_its_coverage(self):
        folder, logs = os.path.join(self.dir, "results"), os.path.join(self.dir, "adsb")
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0))])
        os.makedirs(logs)
        with open(os.path.join(logs, "SOURCE.txt"), "w") as f:
            f.write("Source: OpenSky\nPeriod: 2026-11-05T00:00:00Z to 2026-11-06T00:00:00Z\n")
        coverage = adsb.read("opensky", {"results": folder, "logs": logs}, window(T0 - 3600, T0 + 3600), [])["coverage"]
        self.assertEqual([(c["start_utc"], c["end_utc"], c["note"]) for c in coverage],
                         [(iso(T0 - 3600), iso(T0 + 3600), "queried")])

    def test_webtrak_chunks_become_flights_events_and_levels(self):
        site = os.path.join(self.dir, "lcy")
        webtrak_chunks(site, [("101", "GLCYN", "E190", westbound(T0)), ("102", "GFAR", "C172", westbound(T0, north_m=40000))],
                       levels=[(T0 + s, 60 + s / 10) for s in range(0, 30)], events=[(T0 + 3, 72.5)])
        receptors = {"nmt6": {"id": "nmt6", "lat": NMT6[0], "lon": NMT6[1]}}
        spec = {"tool": os.path.join(TOOLS, "webtrak"), "site_dir": site, "monitors": {"nmt6": "106"}}
        got = webtrak.read("webtrak", spec, window(T0 - 600, T0 + 600, receptors), [])
        flights, positions, noise, levels, coverage = (got[t] for t in schema.SOURCE_TABLES)
        self.assertEqual([f["registration"] for f in flights], ["GLCYN"])  # The one 40 km away is left out
        self.assertEqual(flights[0]["callsign"], "")  # WebTrak gave only the registration
        self.assertTrue(all(p["height_kind"] == "radar" for p in positions))
        self.assertEqual(len(positions), 31)
        self.assertEqual([(e["lmax_db"], e["lmax_utc"]) for e in noise], [(72.5, iso(T0 + 3))])
        self.assertEqual(noise[0]["event_class"], "aircraft")  # WebTrak's class 1, in the common table's terms
        self.assertEqual(len(levels), 30)
        self.assertEqual(coverage[0]["note"], "saved chunks")


def flight(source, sid, reg, first, last):
    return {"source": source, "source_id": sid, "registration": reg, "first_utc": iso(first), "last_utc": iso(last)}


class Linking(unittest.TestCase):
    def tracks_and_approaches(self, flights, points):
        tracks = {(f["source"], f["source_id"]): list(pts) for f, pts in zip(flights, points)}
        frame = Frame(*NMT6)
        approaches = {(*k, "nmt6"): closest_approach(v, frame) for k, v in tracks.items()}
        return tracks, approaches

    def passes(self, flights, points):
        rows = link.link(flights, *self.tracks_and_approaches(flights, points), "nmt6")
        groups = {}
        for r in rows:
            groups.setdefault(r["pass_id"], []).append((r["source"], r["evidence"]))
        return groups

    def test_same_registration_and_overlapping_times_link(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "GLCYN", T0 - 50, T0 + 70)]
        groups = self.passes(fs, [westbound(T0), westbound(T0 + 1)])
        self.assertEqual(list(groups.values()), [[("opensky", "registration"), ("webtrak", "registration")]])
        self.assertEqual(list(groups), ["20261105T0900-GLCYN"])

    def test_the_same_airframe_hours_apart_is_two_passes(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "GLCYN", T0 + 7200, T0 + 7300)]
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0 + 7250)])), 2)

    def test_different_registrations_never_link_even_on_the_same_track(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "GLCYO", T0 - 60, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0)])), 2)

    def test_without_a_registration_close_tracks_link(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "", T0 - 60, T0 + 60)]
        groups = self.passes(fs, [westbound(T0), westbound(T0 + 3, north_m=-260)])
        self.assertEqual(list(groups.values()), [[("opensky", "track"), ("webtrak", "track")]])
        # Too far apart in space, or in time, they don't
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0, north_m=1500)])), 2)
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0 + 50)])), 2)

    def test_tracks_link_without_a_registration_far_from_the_receptor(self):
        # 12 km north of NMT6, so their closest approaches to it say little; the tracks still agree
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "", T0 - 60, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [westbound(T0, north_m=12000), westbound(T0 + 2, north_m=12100)])), 1)
        # But not one far below the other
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0, height_at_abeam=900)])), 2)

    def test_a_registration_with_too_few_positions_together_isnt_checked(self):
        # The tracks overlap by only two seconds: too little to say they agree
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0), flight("webtrak", "b", "GLCYN", T0 - 1, T0 + 60)]
        track = westbound(T0)
        groups = self.passes(fs, [[p for p in track if p[0] <= T0], [p for p in track if p[0] >= T0 - 1]])
        self.assertEqual(list(groups.values()), [[("opensky", link.UNCHECKED), ("webtrak", link.UNCHECKED)]])

    def test_the_same_registration_on_two_different_tracks_doesnt_link(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "GLCYN", T0 - 60, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0, north_m=5000)])), 2)

    def test_the_same_registration_links_when_the_tracks_dont_overlap_in_time(self):
        # WebTrak's saved data starts just after OpenSky's track ends: nothing to compare, so the registration decides
        before, after = [p for p in westbound(T0) if p[0] <= T0], [p for p in westbound(T0) if p[0] >= T0 + 30]
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0), flight("webtrak", "b", "GLCYN", T0 + 30, T0 + 60)]
        groups = self.passes(fs, [before, after])
        self.assertEqual(list(groups.values()), [[("opensky", link.UNCHECKED), ("webtrak", link.UNCHECKED)]])

    def test_a_registration_whose_tracks_agree_beats_one_never_compared(self):
        # OpenSky has two flights with WebTrak's registration: one ends before WebTrak's starts, so
        # it can't be compared, and one whose track agrees with WebTrak's. WebTrak joins the second.
        track = westbound(T0, span_s=120)
        early = [p for p in track if p[0] <= T0 - 30]
        late = [p for p in track if p[0] >= T0]
        radar = [p for p in track if p[0] >= T0 - 10]
        fs = [flight("opensky", "early", "GLCYN", T0 - 120, T0 - 30), flight("opensky", "late", "GLCYN", T0, T0 + 120),
              flight("webtrak", "w", "GLCYN", T0 - 10, T0 + 120)]
        rows = link.link(fs, *self.tracks_and_approaches(fs, [early, late, radar]), "nmt6")
        pass_of = {r["source_id"]: r["pass_id"] for r in rows}
        self.assertEqual(pass_of["w"], pass_of["late"])
        self.assertNotEqual(pass_of["w"], pass_of["early"])

    def test_a_hole_in_one_track_isnt_compared_as_a_straight_line(self):
        # OpenSky loses the aircraft while it's out of its box, 9 km north, and finds it again;
        # WebTrak follows it all the way. A line across OpenSky's hole would be 9 km from WebTrak.
        # OpenSky's positions come once a second, so its track is the one interpolated at WebTrak's times.
        def where(t):
            return (t, *at(-(t - T0) * 70, 9000 if abs(t - T0) < 150 else -210), 330)
        radar = [where(t) for t in range(int(T0 - 200), int(T0 + 201), 4)]
        adsb_track = [where(t) for t in range(int(T0 - 200), int(T0 + 201)) if abs(t - T0) >= 150]
        fs = [flight("opensky", "a", "GLCYN", T0 - 200, T0 + 200), flight("webtrak", "b", "GLCYN", T0 - 200, T0 + 200)]
        self.assertEqual(len(self.passes(fs, [adsb_track, radar])), 1)

    def test_a_flight_joins_its_best_match_not_the_first_found(self):
        fs = [flight("opensky", "a", "GAAAA", T0 - 70, T0 + 60), flight("opensky", "b", "GBBBB", T0 - 60, T0 + 60),
              flight("webtrak", "c", "", T0 - 60, T0 + 60)]
        groups = self.passes(fs, [westbound(T0, north_m=-560), westbound(T0, north_m=-230), westbound(T0)])
        joined = [g for g in groups.values() if len(g) > 1]
        self.assertEqual(len(joined), 1)
        self.assertIn("20261105T0900-GBBBB", groups)
        self.assertEqual(len(groups["20261105T0900-GBBBB"]), 2)  # 20 m away, not GAAAA's 350 m

    def test_adding_webtrak_doesnt_change_a_pass_id(self):
        # WebTrak's closest approach is in the minute before OpenSky's
        opensky = flight("opensky", "a", "GLCYN", T0 - 55, T0 + 65)
        alone = self.passes([opensky], [westbound(T0 + 5)])
        both = self.passes([opensky, flight("webtrak", "b", "GLCYN", T0 - 65, T0 + 55)], [westbound(T0 + 5), westbound(T0 - 5)])
        self.assertEqual(list(alone), ["20261105T0900-GLCYN"])
        self.assertEqual(list(both), ["20261105T0900-GLCYN"])
        # Without a registration (so linked by track, which needs them closer), it's named by the ADS-B source's id
        unnamed = self.passes([flight("opensky", "a", "", T0 - 58, T0 + 62), flight("webtrak", "b", "", T0 - 62, T0 + 58)],
                              [westbound(T0 + 2), westbound(T0 - 2)])
        self.assertEqual(list(unnamed), ["20261105T0900-a"])

    def test_sources_are_ranked_ads_b_first_and_webtrak_last(self):
        self.assertEqual(link.ranked(["webtrak", "fusion", "opensky", "adsb", "adsblol"]), ["adsb", "adsblol", "opensky", "fusion", "webtrak"])

    def test_two_flights_from_one_source_are_never_one_pass(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("opensky", "b", "GLCYN", T0 - 60, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0)])), 2)


class Explain(unittest.TestCase):
    """Why a source has no flight in a pass."""

    def limits(self, ceiling_m=3048.0, areas=(("circle", *NMT6, 15.0), ("box", *NMT6, 5.0)), any_=False):
        return explain.prepare({"ceiling_m": ceiling_m, "areas": list(areas), "any": any_})

    def test_a_pass_the_source_could_see_is_unexplained(self):
        pts = westbound(T0)
        self.assertEqual(explain.why_unseen(pts, self.limits(), [(T0 - 600, T0 + 600)]), explain.UNEXPLAINED)

    def test_no_data_then(self):
        pts = westbound(T0)
        self.assertEqual(explain.why_unseen(pts, self.limits(), []), explain.NO_DATA)
        # Data for only the last 10 s of the pass isn't enough to have seen it
        self.assertEqual(explain.why_unseen(pts, self.limits(), [(T0 + 50, T0 + 600)]), explain.NO_DATA)

    def test_coverage_runs_are_merged(self):
        cov = explain.Coverage([(T0 + 100, T0 + 200), (T0, T0 + 50), (T0 + 40, T0 + 60)])
        self.assertEqual((cov.starts, cov.ends), ([T0, T0 + 100], [T0 + 60, T0 + 200]))
        self.assertIn(T0 + 55, cov)
        self.assertNotIn(T0 + 80, cov)
        self.assertNotIn(T0 - 1, cov)
        self.assertIn(T0 + 200, cov)

    def test_outside_its_area(self):
        far = [(t, lat + 0.2, lon, h) for t, lat, lon, h in westbound(T0)]  # About 22 km north
        self.assertEqual(explain.why_unseen(far, self.limits(), [(T0 - 600, T0 + 600)]), explain.OUTSIDE)
        # With "any", one area is enough
        areas = [("circle", *NMT6, 1.0), ("circle", far[60][1], far[60][2], 1.0)]
        self.assertEqual(explain.why_unseen(far, self.limits(areas=areas, any_=True), [(T0 - 600, T0 + 600)]), explain.UNEXPLAINED)

    def test_above_its_ceiling(self):
        high = westbound(T0, height_at_abeam=9000)
        self.assertEqual(explain.why_unseen(high, self.limits(), [(T0 - 600, T0 + 600)]), explain.ABOVE)
        self.assertEqual(explain.why_unseen(high, self.limits(ceiling_m=None), [(T0 - 600, T0 + 600)]), explain.UNEXPLAINED)

    def test_just_below_the_ceiling_counts_as_above_it(self):
        # 2,800 m QNH is above a 10,000 ft (3,048 m) pressure-altitude ceiling when QNH is under about 983 hPa
        level = [(t, lat, lon, 2800.0) for t, lat, lon, _ in westbound(T0)]
        self.assertEqual(explain.why_unseen(level, self.limits(), [(T0 - 600, T0 + 600)]), explain.ABOVE)
        lower = [(t, lat, lon, 2700.0) for t, lat, lon, _ in westbound(T0)]
        self.assertEqual(explain.why_unseen(lower, self.limits(), [(T0 - 600, T0 + 600)]), explain.UNEXPLAINED)

    def test_adsb_limits_come_from_the_results_and_logs(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "results"))
            os.makedirs(os.path.join(d, "logs"))
            with open(os.path.join(d, "results", "summary.txt"), "w") as f:
                f.write("Site: NMT6, St Pauls Church, Thamesmead (51.50535, 0.11075)\n")
            with open(os.path.join(d, "logs", "SOURCE.txt"), "w") as f:
                f.write("Kept: airborne positions within 5 km either side of NMT6 (a box)\n")
            got = adsb.limits({"results": os.path.join(d, "results"), "logs": os.path.join(d, "logs")}, window(T0, T0 + 1))
            self.assertAlmostEqual(got["ceiling_m"], 3048.0)
            self.assertEqual(got["areas"], [("circle", *NMT6, 15.0), ("box", *NMT6, 5.0)])
            self.assertEqual(adsb.limits({"results": os.path.join(d, "results"), "ceiling_ft": 5000}, window(T0, T0 + 1))["areas"], [("circle", *NMT6, 15.0)])


class BuildAndServe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        adsb_results(os.path.join(self.dir, "results"), [
            ("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0)),
            ("4006a2", "G-LCYO", "CFE2", "E190", westbound(T0 + 600))])
        webtrak_chunks(os.path.join(self.dir, "lcy"), [("101", "GLCYN", "E190", westbound(T0 + 1))],
                       levels=[(T0 + s, 65.0) for s in range(30)], events=[(T0 + 4, 74.0)])
        self.deployments = os.path.join(self.dir, "deployments")
        os.makedirs(self.deployments)
        with open(os.path.join(self.deployments, "2026-11-05.json"), "w") as f:
            json.dump({
                "window_utc": ["2026-11-05T00:00:00Z", "2026-11-06T00:00:00Z"],
                "receptors": {"nmt6": {"lat": NMT6[0], "lon": NMT6[1], "label": "NMT6", "public": True,
                                       "ground_elevation_m": 3, "mic_height_m": 3}},
                "sources": {"opensky": {"adapter": "adsb", "results": "../results"},
                            "webtrak": {"adapter": "webtrak", "tool": os.path.join(TOOLS, "webtrak"),
                                        "site_dir": "../lcy", "monitors": {"nmt6": "106"}}}}, f)
        patcher = mock.patch.object(manifest, "OUT_DIR", os.path.join(self.dir, "out"))
        patcher.start()
        self.addCleanup(patcher.stop)
        # A fleet table of the test's own, never the real one in registry/
        self.fleet_path = os.path.join(self.dir, "fleet.csv")
        fleet.write({"GLCYN": {"registration": "GLCYN", "mark": "G-LCYN", "status": "registered", "icao_type": "E190",
                               "model": "ERJ 190-100 LR", "icao24": "4006A1", "register": "uk"}}, self.fleet_path)
        patcher = mock.patch.object(fleet, "FLEET_PATH", self.fleet_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_build_resolves_types_from_the_fleet_table(self):
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        summary = build.build(m, log=io.StringIO())
        common = os.path.join(self.dir, "out", "2026-11-05", "common")
        got = {i["registration"]: i for i in schema.read_table(common, "identity")}
        self.assertEqual((got["GLCYN"]["type"], got["GLCYN"]["type_source"], got["GLCYN"]["disagree"]),
                         ("E190", "register:uk", ""))
        self.assertEqual((got["GLCYO"]["type"], got["GLCYO"]["type_source"]), ("E190", "opensky"))
        self.assertEqual(summary["types"], {"from a register": 1, "set by hand": 0, "from a source only": 1,
                                            "unknown": 0, "sources disagree": 0})
        # The page is given each pass's identity
        day = App(self.deployments).day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual(day["identity"]["20261105T0900-GLCYN"]["type_source"], "register:uk")

    def test_build_writes_the_common_tables(self):
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        summary = build.build(m, log=io.StringIO())
        self.assertEqual(summary["passes"], 2)
        self.assertEqual(summary["passes_in_several_sources"], 1)
        common = os.path.join(self.dir, "out", "2026-11-05", "common")
        approaches = schema.read_table(common, "approaches")
        self.assertEqual(len(approaches), 3)
        self.assertTrue(all(abs(float(a["ground_m"]) - 210) < 5 for a in approaches))
        self.assertTrue(all(abs(float(a["path_angle_deg"]) + 5.5) < 0.2 for a in approaches))
        self.assertEqual(len(schema.read_table(common, "levels")), 30)
        # WebTrak has no data when G-LCYO passed; OpenSky saw everything WebTrak did
        [unseen] = schema.read_table(common, "unseen")
        self.assertEqual((unseen["pass_id"], unseen["source"], unseen["reason"]), ("20261105T0910-GLCYO", "webtrak", explain.NO_DATA))
        self.assertEqual(summary["unseen"][explain.UNEXPLAINED], 0)

    def test_a_build_replaces_the_tables_folder_whole(self):
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        build.build(m, log=io.StringIO())
        out = os.path.join(self.dir, "out", "2026-11-05")
        with open(os.path.join(out, "common", "stale.csv"), "w") as f:
            f.write("left over\n")
        build.build(m, log=io.StringIO())
        self.assertFalse(os.path.exists(os.path.join(out, "common", "stale.csv")))
        self.assertEqual(sorted(os.listdir(out)), ["build.json", "common"])  # Nothing temporary left
        self.assertEqual(sorted(os.listdir(os.path.join(out, "common"))),
                         sorted(n if n in schema.PARTITIONED else f"{n}.csv" for n in schema.TABLES))
        # The daily tables have a file per day
        self.assertEqual(schema.table_days(os.path.join(out, "common"), "positions"), ["2026-11-05"])
        positions = schema.read_table(os.path.join(out, "common"), "positions")
        keys = [(p["source"], p["source_id"], float(p["t"])) for p in positions]
        self.assertEqual(keys, sorted(keys))

    def test_the_app_sees_a_build_made_outside_it(self):
        app = App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        d = app.deployment("2026-11-05")
        self.assertEqual(len(d.load()["flights"]), 3)
        build_json = os.path.join(self.dir, "out", "2026-11-05", "build.json")
        stamp = os.path.getmtime(build_json)
        webtrak_chunks(os.path.join(self.dir, "lcy"), [("102", "GLCYO", "E190", westbound(T0 + 601))])
        build.build(manifest.load(d.manifest_path), log=io.StringIO())  # As make build would
        os.utime(build_json, (stamp, stamp))  # Even if build.json's time looks unchanged
        self.assertEqual(len(d.load()["flights"]), 4)

    def test_a_rebuild_is_refused_even_after_the_manifest_is_read_again(self):
        app = App(self.deployments)
        d = app.deployment("2026-11-05")
        path = os.path.join(self.deployments, "2026-11-05.json")
        with d.building:  # As if a rebuild were running
            os.utime(path, (os.path.getmtime(path) + 5,) * 2)
            self.assertIsNot(app.deployment("2026-11-05"), d)
            with self.assertRaises(BadRequest):
                app.rebuild({"deployment": "2026-11-05"})

    def test_the_day_says_which_tracks_are_radar_and_classes_events(self):
        app = App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual({(f["source"], f["height_kind"]) for f in day["flights"]}, {("opensky", "geometric"), ("webtrak", "radar")})
        self.assertEqual([e["event_class"] for e in day["events"]], ["aircraft"])
        self.assertFalse(any(k.startswith("_") for f in day["flights"] for k in f))
        self.assertEqual(day["sources"], ["opensky", "webtrak"])

    def test_the_server_answers_only_this_computer_and_json_posts(self):
        server.Handler.app = App(self.deployments)
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]

        def ask(method, path, host=f"127.0.0.1:{port}", body=None, kind=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            headers = {"Host": host, **({"Content-Type": kind} if kind else {})}
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            r.read()
            c.close()
            return r.status

        self.assertEqual(ask("GET", "/"), 200)
        self.assertEqual(ask("GET", "/common.js"), 200)
        self.assertEqual(ask("GET", "/style.css"), 200)
        self.assertEqual(ask("GET", "/../app.py"), 404)  # Only the page's own files
        self.assertEqual(ask("GET", "/nope.js"), 404)
        self.assertEqual(ask("GET", "/api/deployments", host=f"localhost:{port}"), 200)
        self.assertEqual(ask("GET", "/api/deployments", host=f"evil.example:{port}"), 403)  # DNS rebinding
        self.assertEqual(ask("GET", "/api/deployments", host=f"localhost.evil.example:{port}"), 403)
        body = json.dumps({"deployment": "2026-11-05"})
        self.assertEqual(ask("POST", "/api/build", body=body, kind="text/plain"), 403)  # A form another site could send
        self.assertEqual(ask("POST", "/api/build", body="{", kind="application/json"), 400)
        self.assertEqual(ask("POST", "/api/build", body="[1]", kind="application/json"), 400)
        self.assertEqual(ask("POST", "/api/build", body=body, kind="application/json"), 200)
        self.assertEqual(ask("GET", "/api/day?deployment=2026-11-05&day=nope"), 400)

    def test_a_pass_one_source_should_have_seen_is_unexplained(self):
        # The same track, but WebTrak gives another registration, so the two can't be linked
        webtrak_chunks(os.path.join(self.dir, "lcy"), [("101", "GLCYX", "E190", westbound(T0 + 1))])
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        summary = build.build(m, log=io.StringIO())
        common = os.path.join(self.dir, "out", "2026-11-05", "common")
        reasons = {(u["pass_id"], u["source"]): u["reason"] for u in schema.read_table(common, "unseen")}
        self.assertEqual(reasons[("20261105T0900-GLCYN", "webtrak")], explain.UNEXPLAINED)
        self.assertEqual(reasons[("20261105T0900-GLCYX", "opensky")], explain.UNEXPLAINED)
        self.assertEqual(summary["unseen"][explain.UNEXPLAINED], 2)
        app = App(self.deployments)
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual(day["unseen"]["20261105T0900-GLCYN"], {"webtrak": explain.UNEXPLAINED})

    def test_the_app_lists_deployments_and_serves_a_day(self):
        app = App(self.deployments)
        [d] = app.deployments()
        self.assertFalse(d["built"])
        with self.assertRaises(BadRequest):
            app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        app.rebuild({"deployment": "2026-11-05"})
        [d] = app.deployments()
        self.assertTrue(d["built"])
        self.assertEqual(d["days"][0]["minutes"]["webtrak"], 2)
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual(len(day["flights"]), 3)
        linked = [f for f in day["flights"] if f["registration"] == "GLCYN"]
        self.assertEqual({f["pass_id"] for f in linked}, {"20261105T0900-GLCYN"})
        self.assertEqual({f["evidence"] for f in linked}, {"registration"})
        self.assertIn("nmt6", linked[0]["approaches"])
        self.assertTrue(all(len(p) == 4 for pts in day["tracks"].values() for p in pts))
        self.assertTrue(all(b[0] - a[0] >= TRACK_SPACING_S for pts in day["tracks"].values() for a, b in zip(pts, pts[1:])))
        self.assertEqual(day["levels"][0][:2], [T0 - day["start"], "nmt6"])
        with self.assertRaises(BadRequest):
            app.day({"deployment": "2026-11-05", "day": "2026-11-06"})  # Outside its window
        with self.assertRaises(BadRequest):
            app.day({"deployment": "2026-11-05", "day": "yesterday"})
        with self.assertRaises(BadRequest):
            app.deployment("nope")

    def test_a_flight_across_midnight_has_its_whole_track_on_the_next_day(self):
        midnight = parse_time("2026-11-06T00:00:00Z")
        adsb_results(os.path.join(self.dir, "results"), [("4006a3", "G-LCYP", "CFE3", "E190", westbound(midnight + 30))])
        path = os.path.join(self.deployments, "2026-11-05.json")
        with open(path) as f:
            spec = json.load(f)
        spec["window_utc"] = ["2026-11-05T00:00:00Z", "2026-11-07T00:00:00Z"]
        with open(path, "w") as f:
            json.dump(spec, f)
        app = App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        common = os.path.join(self.dir, "out", "2026-11-05", "common")
        self.assertEqual(schema.table_days(common, "positions"), ["2026-11-05"])  # Filed by the day it started
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-06"})
        [track] = day["tracks"].values()
        self.assertEqual(len(track), 61)  # Every 2 s, from 23:59:30 to 00:01:30
        self.assertLess(track[0][0], midnight)
        self.assertEqual(day["flights"][0]["height_kind"], "geometric")

    def test_the_app_reads_a_changed_manifest_again(self):
        app = App(self.deployments)
        path = os.path.join(self.deployments, "2026-11-05.json")
        self.assertEqual(app.deployments()[0]["description"], "")
        with open(path) as f:
            spec = json.load(f)
        spec["description"] = "Changed"
        with open(path, "w") as f:
            json.dump(spec, f)
        os.utime(path, (os.path.getmtime(path) + 5,) * 2)
        self.assertEqual(app.deployments()[0]["description"], "Changed")

    def test_listing_deployments_reads_only_their_coverage(self):
        app = App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        d = app.deployment("2026-11-05")
        d.tables = d.stamp = None
        [listed] = app.deployments()
        self.assertEqual(listed["days"][0]["minutes"]["webtrak"], 2)
        self.assertIsNone(d.tables)  # Positions and levels weren't read just to list the days

    def test_a_rebuild_blocks_only_its_own_deployment(self):
        app = App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        d = app.deployment("2026-11-05")
        with d.building:  # As if a rebuild were running
            self.assertTrue(app.deployments()[0]["built"])  # The list doesn't wait for it
            with self.assertRaises(BadRequest):
                app.rebuild({"deployment": "2026-11-05"})  # A second rebuild is refused

    def test_a_day_being_read_doesnt_refuse_a_rebuild(self):
        app = App(self.deployments)
        d = app.deployment("2026-11-05")
        with d.lock:  # As if a day's tables were being read
            app.rebuild({"deployment": "2026-11-05"})
        self.assertEqual(len(d.load()["flights"]), 3)

    def test_a_build_outside_the_app_refuses_a_rebuild_from_it(self):
        app = App(self.deployments)
        d = app.deployment("2026-11-05")
        with build.build_lock(d.m):  # As if make build were running
            with self.assertRaises(build.Busy):
                build.build(d.m, log=io.StringIO(), wait=False)
            with self.assertRaises(BadRequest):
                app.rebuild({"deployment": "2026-11-05"})
        app.rebuild({"deployment": "2026-11-05"})  # And once it's done, a rebuild goes ahead

    def test_a_build_clears_what_a_killed_build_left_behind(self):
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        build.build(m, log=io.StringIO())
        out = os.path.join(self.dir, "out", "2026-11-05")
        os.makedirs(os.path.join(out, ".common.new.abc123"))
        build.build(m, log=io.StringIO())
        self.assertEqual(sorted(os.listdir(out)), ["build.json", "common"])

    def test_overlapping_coverage_counts_each_minute_once(self):
        rows = [{"source": "opensky", "start_utc": iso(T0), "end_utc": iso(T0 + 3600)},
                {"source": "opensky", "start_utc": iso(T0 + 1800), "end_utc": iso(T0 + 5400)},
                {"source": "opensky", "start_utc": iso(T0 + 600), "end_utc": iso(T0 + 1200)}]
        self.assertEqual(minutes_covered(rows, T0 - 3600, T0 + 86400), {"opensky": 90})


@unittest.skipUnless(shutil.which("node"), "needs node to run the page's script")
class Page(unittest.TestCase):
    """The survey app's own scripts (survey/ui/), run by tests/ui_check.js without a browser."""

    def run_page(self, data, receptor="nmt6", sources=(), measure=None):
        here = os.path.dirname(os.path.abspath(__file__))
        done = subprocess.run(["node", os.path.join(here, "ui_check.js"), os.path.join(server.UI_DIR, "index.html")],
                              input=json.dumps({"data": data, "receptor": receptor, "sources": list(sources), "measure": measure}),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_each_noise_event_goes_to_one_pass_the_closest(self):
        def f(pass_id, t, ground):
            return {"pass_id": pass_id, "source": "opensky", "first_utc": iso(t - 60),
                    "approaches": {"nmt6": {"t": iso(t), "ground_m": ground, "height_m": 300}}}

        def e(t, db, receptor="nmt6", source="webtrak"):
            return {"source": source, "receptor": receptor, "lmax_utc": iso(t), "lmax_db": str(db)}

        data = {"flights": [f("far", T0, 2000), f("near", T0 + 10, 150), f("alone", T0 + 600, 900), f("quiet", T0 + 1200, 500)],
                "events": [e(T0 + 15, 75), e(T0 + 30, 70), e(T0 + 610, 68), e(T0 + 650, 80), e(T0 + 1200, 90, "garden"),
                           e(T0 + 1201, 85, source="fusion")]}
        got = self.run_page(data, sources=["webtrak", "opensky"])["events"]
        # Both events near T0 go to "near", which came 150 m from NMT6, not to "far" as well; "alone"
        # gets the one 10 s after it but not the one 50 s after; nothing at another receptor counts,
        # nor an event from a source that's switched off
        self.assertEqual(got, {"near": "75", "alone": "68"})

    def test_sources_are_listed_in_the_servers_order(self):
        data = {"flights": [], "events": [], "sources": link.ranked(["webtrak", "fusion", "opensky", "adsb", "adsblol"])}
        got = self.run_page(data, sources=["webtrak", "zzz", "fusion", "opensky", "adsb", "adsblol"])
        self.assertEqual(got["order"], ["adsb", "adsblol", "opensky", "fusion", "webtrak", "zzz"])

    def test_by_aircraft_type_has_a_lane_per_source_and_a_row_per_pass_type(self):
        def f(pass_id, source, kind, angle, edge=False, height=300):
            return {"pass_id": pass_id, "source": source, "type": kind, "first_utc": iso(T0 - 60),
                    "approaches": {"nmt6": {"t": iso(T0), "ground_m": 200, "height_m": height,
                                            "path_angle_deg": angle, "at_track_end": edge}}}

        data = {"sources": ["opensky", "webtrak"], "events": [], "flights": [
            # WebTrak calls a's aircraft an E195, but it's in the E190 row, as OpenSky, ranked first, says
            f("a", "opensky", "E190", -5.4), f("a", "webtrak", "E195", -5.6),
            f("b", "opensky", "E190", -5.6), f("b", "webtrak", "", -5.2),
            f("c", "webtrak", "", None), f("d", "webtrak", "", 3.0),
            f("e", "opensky", "A320", -4.5, edge=True, height=900)]}
        got = self.run_page(data, sources=["opensky", "webtrak"], measure="path_angle_deg")["types"]
        self.assertEqual(got, [
            ["A320", 1, [["opensky", [-4.5], -4.5]]],  # The path angle isn't doubtful at an edge, so it counts
            ["E190", 2, [["opensky", [-5.4, -5.6], -5.5], ["webtrak", [-5.6, -5.2], -5.4]]],
            ["unknown", 1, [["webtrak", [3.0], 3.0]]]])  # c has no path angle, so isn't shown
        # A height at an edge of its source's data is shown, but left out of the median
        got = self.run_page(data, sources=["opensky", "webtrak"], measure="height_m")["types"]
        self.assertEqual(got[0], ["A320", 1, [["opensky", [900], None]]])

    def test_a_resolved_type_decides_a_pass_row(self):
        def f(pass_id, kind):
            return {"pass_id": pass_id, "source": "opensky", "type": kind, "first_utc": iso(T0 - 60),
                    "approaches": {"nmt6": {"t": iso(T0), "ground_m": 200, "height_m": 300, "path_angle_deg": -4.5}}}

        # The register says a is an E290, whatever OpenSky says; b isn't in the fleet table
        data = {"sources": ["opensky"], "events": [], "flights": [f("a", "E190"), f("b", "E190")],
                "identity": {"a": {"type": "E290", "type_source": "register:ch", "disagree": "opensky E190"}}}
        got = self.run_page(data, sources=["opensky"], measure="path_angle_deg")["types"]
        self.assertEqual([row[:2] for row in got], [["E190", 1], ["E290", 1]])


class FakeRegister:
    """registers.Http's stand-in: answers by URL ending, and records what was asked."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def json(self, url, body=None):
        self.asked.append((url, body))
        for ending, answer in sorted(self.answers.items(), key=lambda a: -len(a[0])):  # The most specific first
            if url.endswith(ending):
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected request {url}")

    text = bytes = lambda self, url: self.json(url)


GINFO = {
    "search": [{"AircraftID": 64481, "Mark": "LCYN", "AircraftType": "ERJ 190-100 LR", "RegistrationStatus": "R"},
               {"AircraftID": 1, "Mark": "LCYNX"}],
    "details/64481": {
        "RegistrationDetails": {"Mark": "LCYN", "Status": "Registered"},
        "AircraftDetails": {"Manufacturer": "EMPRESA BRASILEIRA DE AERONAUTICA SA", "Type": "ERJ 190-100 LR",
                            "SerialNumber": "19000392", "ICAO24BitAircraftAddress": {"Hex": "4063c3"},
                            "PopularName": "EMBRAER 190", "ICAOAircraftTypeDesignator": "E190",
                            "Engines": [{"NumberOfEngines": 2, "Name": "GENERAL ELECTRIC CO CF34-10E5A1 G07 "}],
                            "Mtow": "45990 kg", "YearBuild": 2010},
        "NoiseSummaryDetails": {"NoiseCertificateNumber": "030406", "NoiseChapter": "03"},
        "RegisteredAircraftOwners": [{"RegisteredOwners": "SOMEONE"}]},
    "noisecertificationdetails/64481": {"NoiseLevel": {
        "FlyoverLevel": "Flyover: 81.4 EPNdB", "LateralLevel": "Lateral: 93.0 EPNdB", "ApproachLevel": "Approach: 92.5 EPNdB"}},
}
BAZL = {
    "/lfr": [{"lfrId": "1334634", "registration": "HB-AZH", "status": "Registered"}],
    "/lfr/1334634": {"lfrId": "1334634", "status": "Registered", "registration": "HB-AZH",
                     "aircraftModelType": "ERJ 190-300", "icaoCode": "E290", "manufacturer": "YABORA",
                     "ownerOperators": [{"ownerOperator": "Someone AG"}],
                     "details": {"marketing": "E190-E2", "serialNumber": "19020046", "yearOfManufacture": 2021,
                                 "mtom": 54000, "engines": [{"name": "PW1919G", "count": 2}],
                                 "noiseStandard": "ICAO Annex 16, Vol. 1, Chapter 14",
                                 "noiseLevel": "Sideline: 85.4 EPNdB; Take Off: 77.7 EPNdB; Approach: 91.4 EPNdB"}},
}


class Fleet(unittest.TestCase):
    def test_each_registration_goes_to_its_countrys_register(self):
        self.assertEqual(registers.nationality("HBAZH"), "HB")
        self.assertEqual(registers.nationality("GLCYN"), "G")
        self.assertIsNone(registers.nationality("DAKJC"))
        with self.assertRaises(KeyError):
            registers.look_up("DAKJC", FakeRegister({}))

    def test_the_uk_register_gives_type_engines_mass_and_noise_but_no_owner(self):
        http = FakeRegister(GINFO)
        got = registers.look_up("GLCYN", http)
        self.assertEqual(http.asked[0][1]["Registration"], "LCYN")
        self.assertEqual((got["mark"], got["icao_type"], got["model"], got["icao24"], got["mtow_kg"]),
                         ("G-LCYN", "E190", "ERJ 190-100 LR", "4063C3", 45990))
        self.assertEqual((got["approach_epndb"], got["lateral_epndb"], got["flyover_epndb"]), (92.5, 93.0, 81.4))
        self.assertEqual(got["noise_standard"], "ICAO Annex 16, Chapter 3")
        self.assertEqual(got["engines"], "2 x GENERAL ELECTRIC CO CF34-10E5A1 G07")
        self.assertEqual(set(got), set(fleet.FIELDS))  # Nothing about the owner
        self.assertNotIn("SOMEONE", json.dumps(got))

    def test_the_swiss_register_names_its_noise_points_its_own_way(self):
        got = registers.look_up("HBAZH", FakeRegister(BAZL))
        self.assertEqual((got["mark"], got["icao_type"], got["model"], got["marketing_name"], got["mtow_kg"]),
                         ("HB-AZH", "E290", "ERJ 190-300", "E190-E2", 54000))
        # Sideline is the lateral point, take-off the flyover one
        self.assertEqual((got["approach_epndb"], got["lateral_epndb"], got["flyover_epndb"]), (91.4, 85.4, 77.7))
        self.assertEqual(set(got), set(fleet.FIELDS))
        self.assertNotIn("Someone", json.dumps(got))

    def test_an_aircraft_the_register_doesnt_have_is_none(self):
        self.assertIsNone(registers.look_up("GLCYQ", FakeRegister({"search": [{"AircraftID": 1, "Mark": "LCYQX"}]})))
        self.assertIsNone(registers.look_up("HBAZZ", FakeRegister({"/lfr": []})))

    def test_an_unexpected_answer_is_a_failed_lookup_not_a_missing_aircraft(self):
        with self.assertRaises(registers.LookupFailed):
            registers.look_up("HBAZH", FakeRegister({"/lfr": [{"registration": "HB-AZH"}]}))  # No lfrId

    def test_only_new_registrations_are_asked_about_and_manual_ones_never(self):
        entries = {"GLCYN": {"registration": "GLCYN", "register": "uk"},
                   "PHEZE": {"registration": "PHEZE", "register": fleet.MANUAL}}
        regs = ["GLCYN", "GLCYO", "PHEZE", "PHEZF", "HBAZH"]
        self.assertEqual(fleet.to_check(regs, entries), (["GLCYO", "HBAZH"], ["PHEZF"]))
        self.assertEqual(fleet.to_check(regs, entries, recheck=True), (["GLCYN", "GLCYO", "HBAZH"], ["PHEZF"]))

    def test_a_miss_is_asked_about_again_once_its_old(self):
        entries = {"GLCYQ": {"registration": "GLCYQ", "register": "uk", "status": fleet.NOT_FOUND, "checked_utc": "2026-10-01"},
                   "GLCYR": {"registration": "GLCYR", "register": "uk", "status": fleet.NOT_FOUND, "checked_utc": "2026-11-01"},
                   "GLCYN": {"registration": "GLCYN", "register": "uk", "status": "registered", "checked_utc": "2020-01-01"}}
        self.assertEqual(fleet.to_check(list(entries), entries, now="2026-11-06"), (["GLCYQ"], []))

    def test_a_recheck_keeps_an_aircraft_that_has_left_the_register(self):
        entries = {"GLCYN": registers.look_up("GLCYN", FakeRegister(GINFO))}
        fleet.check(["GLCYN"], entries, FakeRegister({"search": []}), log=io.StringIO())
        e = entries["GLCYN"]
        self.assertEqual((e["status"], e["icao_type"], e["register"]), (fleet.LEFT, "E190", "uk"))
        self.assertIn("rechecked", e["note"])
        self.assertEqual(fleet.known_type(e), "E190")  # Its passes keep the register's type

    def test_a_mark_now_on_another_airframe_keeps_the_earlier_entry(self):
        old = registers.look_up("HBAZH", FakeRegister(BAZL))
        entries, log = {"HBAZH": dict(old)}, io.StringIO()
        newer = json.loads(json.dumps(BAZL))
        for answer in newer.values():
            if isinstance(answer, dict) and "details" in answer:
                answer["icaoCode"], answer["details"]["serialNumber"] = "E295", "19020999"
        fleet.check(["HBAZH"], entries, FakeRegister(newer), log=log)
        e = entries["HBAZH"]
        self.assertEqual((e["icao_type"], e["serial_number"]), ("E290", old["serial_number"]))
        self.assertIn("19020999", e["note"])
        self.assertIn("another airframe", log.getvalue())
        # The same airframe again is simply updated
        fleet.check(["HBAZH"], entries, FakeRegister(BAZL), log=io.StringIO())
        self.assertEqual(entries["HBAZH"]["note"], "")

    def test_entries_with_no_type_are_listed(self):
        entries = {"EIABS": {"status": "registered", "register": "ie", "icao_type": ""},
                   "EIHLA": {"status": "registered", "register": "ie", "icao_type": "BCS1"},
                   "GLCYQ": {"status": fleet.NOT_FOUND, "register": "uk", "icao_type": ""},
                   "PHEZE": {"status": "", "register": fleet.MANUAL, "icao_type": ""}}
        self.assertEqual(fleet.untyped(entries), ["EIABS"])

    def test_checking_keeps_answers_misses_and_what_it_had_when_a_register_fails(self):
        old = {"registration": "HBAZH", "icao_type": "E290", "register": "ch"}
        entries = {"HBAZH": dict(old)}
        answers = {**GINFO, "search": [{"AircraftID": 64481, "Mark": "LCYN"}],
                   "/lfr": registers.LookupFailed("down")}
        http = FakeRegister(answers)
        failed = fleet.check(["GLCYN", "HBAZH"], entries, http, log=io.StringIO())
        self.assertEqual(failed, ["HBAZH"])
        self.assertEqual(entries["GLCYN"]["icao_type"], "E190")
        self.assertEqual(entries["HBAZH"], old)
        http = FakeRegister({"search": []})
        fleet.check(["GLCYQ"], entries, http, log=io.StringIO())
        self.assertEqual((entries["GLCYQ"]["status"], entries["GLCYQ"]["register"]), (fleet.NOT_FOUND, "uk"))
        self.assertEqual(fleet.known_type(entries["GLCYQ"]), "")

    def test_the_table_reads_back_as_written(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "registry", "fleet.csv")
            self.assertEqual(fleet.read(path), {})
            entry = registers.look_up("GLCYN", FakeRegister(GINFO))
            fleet.write({"GLCYN": entry}, path)
            got = fleet.read(path)["GLCYN"]
            self.assertEqual(got["icao_type"], "E190")
            self.assertEqual(got["approach_epndb"], "92.5")
            self.assertEqual(list(got), fleet.FIELDS)


def xlsx(rows):
    """A minimal Excel file: rows of text in the first sheet, through shared strings, with a
    gap in the columns, as Excel leaves for an empty cell."""
    strings, cells = [], []
    for r, row in enumerate(rows, 1):
        refs = []
        for c, text in enumerate(row):
            if text == "":
                continue
            strings.append(text)
            refs.append(f'<c r="{chr(65 + c)}{r}" t="s"><v>{len(strings) - 1}</v></c>')
        cells.append(f'<row r="{r}">{"".join(refs)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>" + "".join(f"<si><t>{html.escape(s)}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{''.join(cells)}</sheetData></worksheet>")
    return out.getvalue()


IAA_HEADER = ["Registration Mark", "Aircraft producer", "Aircraft Model", "Category", "Registration date", "MTOW (KGs)",
              "Year of Manufacture", "Aircraft Serial Number", "Engine Manufacturer", "Engine Model", "No. of Engines",
              "Registered Owner", "Address"]
IAA_LISTING_PAGE = """<table><tr><td>31 August 2025</td><td>01/09/2025</td>
<td><a href="https://www.iaa.ie/docs/aircraft-registration/all-registered-aircraft---august-2025.xlsx?v=1">Download</a></td></tr>
<tr><td>30 September 2025</td><td>01/10/2025</td>
<td><a href="https://www.iaa.ie/docs/aircraft-registration/all-registered---september---2025.xlsx?v=3">Download</a></td></tr>
<tr><td>Changes in September 2025</td><td>02/10/2025</td>
<td><a href="https://www.iaa.ie/docs/aircraft-registration-montly-changes/register-changes-september-2025.xlsx">Download</a></td></tr></table>"""
# Two pages of the relevé, as pdftotext -layout lays them out, with the columns in other places
LU_TEXT = (
    "Relevé luxembourgeois des immatriculations\n"
    "Immat        Constructeur                  Type d'aéronef       SN aéronef   Propriétaire                Exploitant\n"
    "LX-ABC       BOMBARDIER INC.               BD-700-1A10 GLOBAL   9213         SOMEONE LTD.                SOMEONE ELSE S.A.\n"
    "                                           EXPRESS XRS\n\n"
    "\fImmat        Constructeur            Type d'aéronef   SN aéronef   Propriétaire               Exploitant\n"
    "LX-LEC       EMBRAER S.A.            ERJ 190-400      19020218     LX-LEC S.A.                LUXAIR, SOCIÉTÉ LUXEMBOURGEOISE DE\n"
    "                                                                                              NAVIGATION AÉRIENNE S.A.\n\n"
    "LX-LQA       BOMBARDIER INC.         DHC-8-402        4468         ROI SOLEIL S.A.            LUXAIR\n")


class DownloadedRegisters(unittest.TestCase):
    def test_models_map_to_icao_types(self):
        for model, code in [("BD-500-1A10", "BCS1"), ("BD-500-1A11", "BCS3"), ("ERJ 190-100 LR", "E190"),
                            ("ERJ 190-300", "E290"), ("ERJ 190-400", "E295"), ("DHC-8-402", "DH8D"),
                            ("A320-251N", "A20N"), ("A320-214", "A320"), ("A321-271NX", "A21N"), ("A321-231", "A321"),
                            ("A319-151N", "A19N"), ("A319-111", "A319"), ("DHC-8-311", "DH8C"), ("DHC-8-102", "DH8A"),
                            ("ATR 72-212 A (600)", "AT76"), ("ATR 72-212A 500", "AT75"),
                            ("BD-700-1A10 GLOBAL EXPRESS XRS", "")]:
            self.assertEqual(registers.icao_type(model), code, model)

    def test_a_model_shared_by_two_types_gives_none_and_says_why(self):
        # The ATR 72-500 and 72-600 are both model 72-212A
        self.assertEqual(registers.icao_type("ATR 72-212 A"), "")
        e = registers.file_entry("EIFAV", "EI-FAV", "ATR 72-212A", "ie", "", "IAA register as at 30 September 2025")
        self.assertEqual(e["icao_type"], "")
        self.assertIn("AT75", e["note"])
        self.assertNotIn("not in registers.MODEL_TYPES", e["note"])

    def test_a_mass_is_read_from_a_number_or_text(self):
        self.assertEqual([registers.kg(v) for v in (45990, 45990.0, "45,990 kg", "", None)], [45990, 45990, 45990, None, None])

    def test_the_first_sheet_is_the_workbooks_first_not_sheet1(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("xl/workbook.xml", f'<workbook {ns} {rel}><sheets><sheet name="Register" sheetId="2" r:id="rId7"/>'
                                          f'<sheet name="Cover" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr("xl/_rels/workbook.xml.rels",
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                       '<Relationship Id="rId7" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="inlineStr">'
                                                   f'<is><t>Cover</t></is></c></row></sheetData></worksheet>')
            z.writestr("xl/worksheets/sheet2.xml", f'<worksheet {ns}><sheetData><row r="1"><c r="B1" t="inlineStr">'
                                                   f'<is><t>Registration Mark</t></is></c></row></sheetData></worksheet>')
        self.assertEqual(registers.xlsx_rows(out.getvalue()), [["", "Registration Mark"]])
        self.assertEqual(registers.xlsx_rows(xlsx([["A"]])), [["A"]])  # No workbook.xml: sheet1.xml

    def test_the_irish_file_is_read_without_owners(self):
        rows = registers.xlsx_rows(xlsx([
            ["All Registered Aircraft as at 30 September 2025 - Total 3"], IAA_HEADER,
            ["EI-HLA", "AIRBUS CANADA LIMITED PARTNERSHIP", "BD-500-1A10", "LAND AEROPLANE", "31/10/2023", "54885",
             "2023", "50068", "PRATT & WHITNEY", "PW1521G", "2", "A LESSOR LIMITED", "DUBLIN 2"],
            ["EJ-ADMI", "GULFSTREAM", "GULFSTREAM GVI", "LAND AEROPLANE", "", "", "", "", "", "", "", "PRIVATE INDIVIDUAL", "CORK"],
            ["EI-ABS", "BOEING", "B75N1", "", "", "1338", "", "75-2634", "", "", "1", "PRIVATE INDIVIDUAL", "DUBLIN"],
            ["Total", "3"]]))
        got = registers.iaa_entries(rows, "30 September 2025", "https://www.iaa.ie/x.xlsx")
        self.assertEqual(sorted(got), ["EIABS", "EIHLA", "EJADMI"])
        self.assertEqual(got["EIHLA"]["register_ref"], "https://www.iaa.ie/x.xlsx")  # The file, not its date
        e = got["EIHLA"]
        self.assertEqual((e["mark"], e["icao_type"], e["model"], e["mtow_kg"], e["engines"], e["register"]),
                         ("EI-HLA", "BCS1", "BD-500-1A10", 54885, "2 x PRATT & WHITNEY PW1521G", "ie"))
        self.assertEqual(set(e), set(fleet.FIELDS))
        self.assertNotIn("LESSOR", json.dumps(got))
        self.assertNotIn("DUBLIN", json.dumps(got))
        # A model MODEL_TYPES doesn't have keeps its model, with no type, so it settles nothing
        self.assertEqual((got["EIABS"]["icao_type"], got["EIABS"]["model"]), ("", "B75N1"))
        self.assertEqual(fleet.known_type(got["EIABS"]), "")
        self.assertIn("MODEL_TYPES", got["EIABS"]["note"])

    def test_the_newest_irish_register_file_is_used(self):
        page = {registers.IAA_LISTING: IAA_LISTING_PAGE, registers.IAA_LISTING + "/1": IAA_LISTING_PAGE}
        issued, title, url = registers.iaa_newest(FakeRegister(page))
        self.assertEqual(issued, "2025-10-01")
        self.assertTrue(url.endswith("all-registered---september---2025.xlsx?v=3"))  # Not the monthly changes

    def test_the_luxembourg_releve_is_read_by_each_pages_columns(self):
        got = registers.lu_entries(LU_TEXT, "2026-10-15")
        self.assertEqual(sorted(got), ["LXABC", "LXLEC", "LXLQA"])
        self.assertEqual((got["LXLEC"]["model"], got["LXLEC"]["icao_type"], got["LXLEC"]["serial_number"]),
                         ("ERJ 190-400", "E295", "19020218"))
        self.assertEqual(got["LXLQA"]["icao_type"], "DH8D")
        self.assertEqual(got["LXABC"]["model"], "BD-700-1A10 GLOBAL EXPRESS XRS")  # Carried on below
        self.assertNotIn("SOLEIL", json.dumps(got))
        self.assertNotIn("LUXAIR", json.dumps(got))

    def test_a_luxembourg_pages_date_line_isnt_part_of_a_model(self):
        text = ("Immat        Constructeur            Type d'aéronef   SN aéronef   Propriétaire\n"
                "LX-LQA       BOMBARDIER INC.         DHC-8-402        4468         ROI SOLEIL S.A.\n"
                "Thursday, October 15, 2026                  Page 1 sur 21\n")
        self.assertEqual(registers.lu_entries(text, "2026-10-15")["LXLQA"]["model"], "DHC-8-402")

    def test_a_downloaded_register_is_read_once_a_run_even_when_it_fails(self):
        http, calls = registers.Http(pause_s=0), []

        def read(h):
            calls.append(1)
            return "2026-10-15", {"LXLEC": {"icao_type": "E295"}}

        self.assertEqual(registers.downloaded("LXLEC", http, "lu", read, now="2026-11-06"), {"icao_type": "E295"})
        self.assertIsNone(registers.downloaded("LXLQA", http, "lu", read, now="2026-11-06"))
        self.assertEqual(len(calls), 1)
        self.assertEqual((registers.file_date(http, "lu"), http.notes), ("2026-10-15", []))  # Recent: no note

        def fails(h):
            calls.append(1)
            raise registers.LookupFailed("cut short")

        for reg in ("EIHLA", "EIHLB"):
            with self.assertRaises(registers.LookupFailed):
                registers.downloaded(reg, http, "ie", fails)
        self.assertEqual(len(calls), 2)

    def test_an_old_register_file_is_reported_once(self):
        http = registers.Http(pause_s=0)
        for reg in ("EIHLA", "EIHLB"):
            registers.downloaded(reg, http, "ie", lambda h: ("2025-10-01", {}), now="2026-11-06")
        self.assertEqual(len(http.notes), 1)
        self.assertIn("2025-10-01, 401 days ago", http.notes[0])

    def test_a_miss_in_an_old_file_says_the_files_date(self):
        http = registers.Http(pause_s=0)
        http.files["ie"] = ("2025-10-01", {})
        entries, log = {}, io.StringIO()
        fleet.check(["EIHLZ"], entries, http, log=log)
        self.assertEqual(entries["EIHLZ"]["status"], fleet.NOT_FOUND)
        self.assertIn("file of 2025-10-01", entries["EIHLZ"]["note"])

    def test_irish_and_luxembourg_marks_go_to_their_registers(self):
        self.assertEqual([registers.REGISTERS[registers.nationality(r)][0] for r in ("EIHLA", "EJADMI", "LXLEC")],
                         ["ie", "ie", "lu"])


class Resolve(unittest.TestCase):
    def flights_and_passes(self, *members):
        flights, passes = [], []
        for pass_id, source, reg, kind, hex_ in members:
            sid = f"{source}-{pass_id}"
            flights.append({"source": source, "source_id": sid, "registration": reg, "type": kind, "hex": hex_})
            passes.append({"pass_id": pass_id, "source": source, "source_id": sid, "evidence": ""})
        return passes, flights

    def test_the_register_decides_and_sources_that_differ_are_listed(self):
        passes, flights = self.flights_and_passes(
            ("p1", "webtrak", "HBAZH", "E295", ""), ("p1", "opensky", "HBAZH", "E290", "4b4a01"))
        entries = {"HBAZH": {"registration": "HBAZH", "icao_type": "E290", "model": "ERJ 190-300", "register": "ch",
                             "status": "registered", "icao24": ""}}
        [got] = resolve.resolve(passes, flights, entries)
        self.assertEqual((got["registration"], got["type"], got["model"], got["type_source"], got["disagree"]),
                         ("HBAZH", "E290", "ERJ 190-300", "register:ch", "webtrak E295"))

    def test_a_transponder_address_other_than_the_registers_is_flagged(self):
        passes, flights = self.flights_and_passes(("p1", "opensky", "GLCYN", "E190", "4063C4"))
        entries = {"GLCYN": {"icao_type": "E190", "register": "uk", "status": "registered", "icao24": "4063C3"}}
        [got] = resolve.resolve(passes, flights, entries)
        self.assertEqual(got["disagree"], "opensky hex 4063C4, register 4063C3")

    def test_without_an_entry_the_highest_ranked_source_decides(self):
        passes, flights = self.flights_and_passes(
            ("p1", "webtrak", "PHEZE", "E195", ""), ("p1", "opensky", "PHEZE", "E190", ""),
            ("p2", "webtrak", "", "", ""),
            ("p3", "opensky", "GLCYQ", "E190", ""))
        entries = {"GLCYQ": {"status": fleet.NOT_FOUND, "register": "uk"},
                   "PHEZE": {"status": "", "icao_type": "", "register": fleet.MANUAL}}
        got = {r["pass_id"]: r for r in resolve.resolve(passes, flights, entries)}
        self.assertEqual((got["p1"]["type"], got["p1"]["type_source"], got["p1"]["disagree"]), ("E190", "opensky", "webtrak E195"))
        self.assertEqual((got["p2"]["type"], got["p2"]["type_source"]), ("", ""))
        self.assertEqual(got["p3"]["type_source"], "opensky")  # A "not found" entry settles nothing

    def test_a_pass_says_why_the_fleet_table_didnt_settle_its_type(self):
        passes, flights = self.flights_and_passes(
            ("p1", "opensky", "GLCYN", "E190", ""), ("p2", "opensky", "", "E190", ""),
            ("p3", "opensky", "PHEZE", "E190", ""), ("p4", "opensky", "GLCYQ", "E190", ""),
            ("p5", "opensky", "EIFAV", "AT76", ""), ("p6", "opensky", "GLCYT", "E190", ""))
        entries = {"GLCYN": {"icao_type": "E190", "register": "uk", "status": "registered"},
                   "GLCYQ": {"status": fleet.NOT_FOUND, "register": "uk"},
                   "EIFAV": {"icao_type": "", "register": "ie", "status": "registered"},
                   "GLCYT": {"icao_type": "E190", "register": "uk", "status": fleet.LEFT}}
        got = {r["pass_id"]: r["fleet"] for r in resolve.resolve(passes, flights, entries)}
        self.assertEqual(got, {"p1": "", "p2": "no registration", "p3": "not in the table", "p4": "not found",
                               "p5": "no type", "p6": ""})

    def test_a_manual_entry_says_so(self):
        passes, flights = self.flights_and_passes(("p1", "opensky", "PHEZE", "E190", ""))
        entries = {"PHEZE": {"icao_type": "E190", "register": fleet.MANUAL, "status": "registered"}}
        [got] = resolve.resolve(passes, flights, entries)
        self.assertEqual(got["type_source"], fleet.MANUAL)


if __name__ == "__main__":
    unittest.main()

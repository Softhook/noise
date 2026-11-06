"""Tests for the survey package, on made-up data in temporary folders. Nothing touches the network."""

from __future__ import annotations

import csv
import datetime as dt
import gzip
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
from unittest import mock

from survey import build, explain, link, manifest, schema, server
from survey.adapters import adsb, webtrak
from survey.common import iso, parse_time, registration
from survey.geometry import Frame, closest_approach

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
        flights, positions, coverage = adsb.read("opensky", {"results": folder}, T0 - 3600, T0 + 3600, warnings)
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
        flights, positions, _ = adsb.read("opensky", {"results": folder}, T0 - 3600, T0 - 900, [])
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
        _, _, coverage = adsb.read("adsb", {"results": folder, "logs": logs}, T0 - 3600, T0 + 3600, [])
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
        adsb.read("opensky", {"results": folder}, T0 - 3600, T0 + 3600, warnings)
        self.assertIn("--all-positions", warnings[0])

    def test_a_converted_sources_period_is_its_coverage(self):
        folder, logs = os.path.join(self.dir, "results"), os.path.join(self.dir, "adsb")
        adsb_results(folder, [("4006a1", "G-LCYN", "CFE1", "E190", westbound(T0))])
        os.makedirs(logs)
        with open(os.path.join(logs, "SOURCE.txt"), "w") as f:
            f.write("Source: OpenSky\nPeriod: 2026-11-05T00:00:00Z to 2026-11-06T00:00:00Z\n")
        _, _, coverage = adsb.read("opensky", {"results": folder, "logs": logs}, T0 - 3600, T0 + 3600, [])
        self.assertEqual([(c["start_utc"], c["end_utc"], c["note"]) for c in coverage],
                         [(iso(T0 - 3600), iso(T0 + 3600), "queried")])

    def test_webtrak_chunks_become_flights_events_and_levels(self):
        site = os.path.join(self.dir, "lcy")
        webtrak_chunks(site, [("101", "GLCYN", "E190", westbound(T0)), ("102", "GFAR", "C172", westbound(T0, north_m=40000))],
                       levels=[(T0 + s, 60 + s / 10) for s in range(0, 30)], events=[(T0 + 3, 72.5)])
        receptors = {"nmt6": {"id": "nmt6", "lat": NMT6[0], "lon": NMT6[1]}}
        spec = {"tool": os.path.join(TOOLS, "webtrak"), "site_dir": site, "monitors": {"nmt6": "106"}}
        flights, positions, noise, levels, coverage = webtrak.read("webtrak", spec, T0 - 600, T0 + 600, receptors, 15, [])
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
        tracks = {(f["source"], f["source_id"]): [{"t": t, "lat": la, "lon": lo, "height_m": h} for t, la, lo, h in pts]
                  for f, pts in zip(flights, points)}
        frame = Frame(*NMT6)
        approaches = {(*k, "nmt6"): closest_approach([(p["t"], p["lat"], p["lon"], p["height_m"]) for p in v], frame)
                      for k, v in tracks.items()}
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

    def test_the_same_registration_on_two_different_tracks_doesnt_link(self):
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0 + 60), flight("webtrak", "b", "GLCYN", T0 - 60, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [westbound(T0), westbound(T0, north_m=5000)])), 2)

    def test_the_same_registration_links_when_the_tracks_dont_overlap_in_time(self):
        # WebTrak's saved data starts just after OpenSky's track ends: nothing to compare, so the registration decides
        before, after = [p for p in westbound(T0) if p[0] <= T0], [p for p in westbound(T0) if p[0] >= T0 + 30]
        fs = [flight("opensky", "a", "GLCYN", T0 - 60, T0), flight("webtrak", "b", "GLCYN", T0 + 30, T0 + 60)]
        self.assertEqual(len(self.passes(fs, [before, after])), 1)

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
        ranked = sorted(["webtrak", "fusion", "opensky", "adsb", "adsblol"], key=link.source_rank)
        self.assertEqual(ranked, ["adsb", "adsblol", "opensky", "fusion", "webtrak"])

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
            got = adsb.limits({"results": os.path.join(d, "results"), "logs": os.path.join(d, "logs")})
            self.assertAlmostEqual(got["ceiling_m"], 3048.0)
            self.assertEqual(got["areas"], [("circle", *NMT6, 15.0), ("box", *NMT6, 5.0)])
            self.assertEqual(adsb.limits({"results": os.path.join(d, "results"), "ceiling_ft": 5000})["areas"], [("circle", *NMT6, 15.0)])


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

    def test_build_writes_the_common_tables(self):
        m = manifest.load(os.path.join(self.deployments, "2026-11-05.json"))
        summary = build.build(m, log=io.StringIO())
        self.assertEqual(summary["passes"], 2)
        self.assertEqual(summary["passes_in_several_sources"], 1)
        common = os.path.join(self.dir, "out", "2026-11-05", "common")
        approaches = schema.read_table(common, "approaches")
        self.assertEqual(len(approaches), 3)
        self.assertTrue(all(abs(float(a["ground_m"]) - 210) < 5 for a in approaches))
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
        self.assertEqual(sorted(os.listdir(os.path.join(out, "common"))), sorted(f"{n}.csv" for n in schema.TABLES))
        positions = schema.read_table(os.path.join(out, "common"), "positions")
        keys = [(p["source"], p["source_id"], float(p["t"])) for p in positions]
        self.assertEqual(keys, sorted(keys))

    def test_the_app_sees_a_build_made_outside_it(self):
        app = server.App(self.deployments)
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
        app = server.App(self.deployments)
        d = app.deployment("2026-11-05")
        path = os.path.join(self.deployments, "2026-11-05.json")
        with d.lock:  # As if a rebuild were running
            os.utime(path, (os.path.getmtime(path) + 5,) * 2)
            self.assertIsNot(app.deployment("2026-11-05"), d)
            with self.assertRaises(server.BadRequest):
                app.rebuild({"deployment": "2026-11-05"})

    def test_the_day_says_which_tracks_are_radar_and_classes_events(self):
        app = server.App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual({(f["source"], f["height_kind"]) for f in day["flights"]}, {("opensky", "geometric"), ("webtrak", "radar")})
        self.assertEqual([e["event_class"] for e in day["events"]], ["aircraft"])
        self.assertFalse(any(k.startswith("_") for f in day["flights"] for k in f))

    def test_the_server_answers_only_this_computer_and_json_posts(self):
        server.Handler.app = server.App(self.deployments)
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
        self.assertEqual(ask("GET", "/api/deployments", host=f"localhost:{port}"), 200)
        self.assertEqual(ask("GET", "/api/deployments", host=f"evil.example:{port}"), 403)  # DNS rebinding
        self.assertEqual(ask("GET", "/api/deployments", host=f"localhost.evil.example:{port}"), 403)
        body = json.dumps({"deployment": "2026-11-05"})
        self.assertEqual(ask("POST", "/api/build", body=body, kind="text/plain"), 403)  # A form another site could send
        self.assertEqual(ask("POST", "/api/build", body="{", kind="application/json"), 400)
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
        app = server.App(self.deployments)
        day = app.day({"deployment": "2026-11-05", "day": "2026-11-05"})
        self.assertEqual(day["unseen"]["20261105T0900-GLCYN"], {"webtrak": explain.UNEXPLAINED})

    def test_the_app_lists_deployments_and_serves_a_day(self):
        app = server.App(self.deployments)
        [d] = app.deployments()
        self.assertFalse(d["built"])
        with self.assertRaises(server.BadRequest):
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
        self.assertTrue(all(b[0] - a[0] >= server.TRACK_SPACING_S for pts in day["tracks"].values() for a, b in zip(pts, pts[1:])))
        self.assertEqual(day["levels"][0][:2], [T0 - day["start"], "nmt6"])
        self.assertEqual(app.day({"deployment": "2026-11-05", "day": "2026-11-06"})["flights"], [])
        with self.assertRaises(server.BadRequest):
            app.day({"deployment": "2026-11-05", "day": "yesterday"})
        with self.assertRaises(server.BadRequest):
            app.deployment("nope")

    def test_the_app_reads_a_changed_manifest_again(self):
        app = server.App(self.deployments)
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
        app = server.App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        d = app.deployment("2026-11-05")
        d.tables = d.stamp = None
        [listed] = app.deployments()
        self.assertEqual(listed["days"][0]["minutes"]["webtrak"], 2)
        self.assertIsNone(d.tables)  # Positions and levels weren't read just to list the days

    def test_a_rebuild_blocks_only_its_own_deployment(self):
        app = server.App(self.deployments)
        app.rebuild({"deployment": "2026-11-05"})
        d = app.deployment("2026-11-05")
        with d.lock:  # As if a rebuild were running
            self.assertTrue(app.deployments()[0]["built"])  # The list doesn't wait for it
            with self.assertRaises(server.BadRequest):
                app.rebuild({"deployment": "2026-11-05"})  # A second rebuild is refused


@unittest.skipUnless(shutil.which("node"), "needs node to run the page's script")
class Page(unittest.TestCase):
    """The survey app's own script (ui.html), run by tests/ui_check.js without a browser."""

    def run_page(self, data, receptor="nmt6", sources=()):
        here = os.path.dirname(os.path.abspath(__file__))
        done = subprocess.run(["node", os.path.join(here, "ui_check.js"), os.path.join(server.PACKAGE_DIR, "ui.html")],
                              input=json.dumps({"data": data, "receptor": receptor, "sources": list(sources)}),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_each_noise_event_goes_to_one_pass_the_closest(self):
        def f(pass_id, t, ground):
            return {"pass_id": pass_id, "source": "opensky", "first_utc": iso(t - 60),
                    "approaches": {"nmt6": {"t": iso(t), "ground_m": ground, "height_m": 300}}}

        def e(t, db, receptor="nmt6"):
            return {"receptor": receptor, "lmax_utc": iso(t), "lmax_db": str(db)}

        data = {"flights": [f("far", T0, 2000), f("near", T0 + 10, 150), f("alone", T0 + 600, 900), f("quiet", T0 + 1200, 500)],
                "events": [e(T0 + 15, 75), e(T0 + 30, 70), e(T0 + 610, 68), e(T0 + 650, 80), e(T0 + 1200, 90, "garden")]}
        got = self.run_page(data)["events"]
        # Both events near T0 go to "near", which came 150 m from NMT6, not to "far" as well; "alone"
        # gets the one 10 s after it but not the one 50 s after; nothing at another receptor counts
        self.assertEqual(got, {"near": "75", "alone": "68"})

    def test_sources_are_listed_ads_b_first_and_webtrak_last(self):
        got = self.run_page({"flights": [], "events": []}, sources=["webtrak", "fusion", "opensky", "adsb", "adsblol"])
        self.assertEqual(got["order"], ["adsb", "adsblol", "opensky", "fusion", "webtrak"])


if __name__ == "__main__":
    unittest.main()

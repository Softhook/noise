"""Tests that run a simulated morning through the analysis and compare the results with the true values.

This tests the analysis against a simple model of reality, not reality: the simulated aircraft fly
straight, perfect paths. Real data will be messier.

Run from the project folder with: python3 -m unittest discover tools/adsb
"""

import csv
import json
import math
import os
import re
import shutil
import tempfile
import unittest

import adsb_analyse as aa
import adsb_simulate as sim

HOUR = 3600
SHORT = {
    "start": sim.DAY + 6.5 * HOUR,
    "runway_change": sim.DAY + 8 * HOUR,
    "end": sim.DAY + 9 * HOUR,
    "power_cut": sim.DAY + 8.5 * HOUR,
    "clock_sync_seconds": 600.0,  # Long enough that flights are in the air while it's wrong
}


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class SimulatedMorning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        sim.simulate(cls.dir, seed=3, times=SHORT)
        cls.truth = read_csv(os.path.join(cls.dir, "truth.csv"))
        with open(os.path.join(cls.dir, "site.json")) as f:
            cls.config = json.load(f)
        cls.out = os.path.join(cls.dir, "results")
        cls.flights, cls.summary = aa.run(
            cls.config, os.path.join(cls.dir, "logs"), cls.out, os.path.join(cls.dir, "eglc_metars.csv")
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def match(self, truth):
        """The analysed flight for a true flight: same aircraft, abeam the garden within 2 minutes."""
        when = float(truth["true_closest_ground_time"])
        found = [
            f for f in self.flights
            if f["hex"] == truth["hex"] and f["closest_ground_time_utc"]
            and abs(aa.parse_utc(f["closest_ground_time_utc"][:19]) - when) < 120
        ]
        self.assertEqual(len(found), 1, f"{truth['callsign']} matched {len(found)} flights")
        return found[0]

    def clean(self, kind):
        """Flights of one kind with no deliberate problems."""
        rows = [t for t in self.truth if t["kind"] == kind and not t["quirk"] and t["during_power_cut"] == "0"]
        self.assertGreater(len(rows), 4)
        return rows

    def test_every_arrival_and_departure_is_found_and_labelled(self):
        for truth in self.truth:
            if truth["kind"] in ("rwy27_arrival", "rwy09_departure") and truth["during_power_cut"] == "0":
                with self.subTest(truth["callsign"]):
                    self.assertEqual(self.match(truth)["label"], truth["kind"])

    def test_nothing_else_is_labelled_as_an_arrival_or_departure(self):
        labelled = [f for f in self.flights if f["label"] != "other"]
        self.assertGreater(len(labelled), 10)
        for flight in labelled:
            when = aa.parse_utc(flight["closest_ground_time_utc"][:19])
            kinds = [
                t["kind"] for t in self.truth
                if t["hex"] == flight["hex"] and abs(float(t["true_closest_ground_time"]) - when) < 120
            ]
            with self.subTest(flight["callsign"]):
                self.assertEqual(kinds, [flight["label"]])

    def test_arrival_offsets_heights_and_angles_are_recovered(self):
        for truth in self.clean("rwy27_arrival"):
            flight = self.match(truth)
            with self.subTest(truth["callsign"]):
                self.assertAlmostEqual(flight["lateral_offset_m"], float(truth["true_lateral_m"]), delta=15)
                self.assertEqual(flight["garden_side"], truth["true_garden_side"])
                # 25 ft altitude steps allow about 4 m.
                self.assertAlmostEqual(
                    flight["height_at_closest_ground_amsl_m"], float(truth["true_height_at_closest_ground_amsl_m"]), delta=8
                )
                self.assertAlmostEqual(flight["path_angle_deg"], float(truth["true_path_angle_deg"]), delta=0.08)
                self.assertAlmostEqual(flight["closest_slant_m"], float(truth["true_closest_slant_m"]), delta=15)
                self.assertEqual(flight["height_source"], "geometric")
                self.assertEqual(flight["flags"], "")

    def test_a320neo_and_e190_approaches_separate(self):
        angles = {"A20N": [], "E190": []}
        for truth in self.clean("rwy27_arrival"):
            if truth["type"] in angles:
                angles[truth["type"]].append(self.match(truth)["path_angle_deg"])
        self.assertTrue(angles["A20N"] and angles["E190"])
        self.assertLess(max(angles["A20N"]), 4.7)
        self.assertGreater(min(angles["E190"]), 5.3)

    def test_departures_are_recovered(self):
        for truth in self.clean("rwy09_departure"):
            flight = self.match(truth)
            with self.subTest(truth["callsign"]):
                self.assertAlmostEqual(flight["lateral_offset_m"], float(truth["true_lateral_m"]), delta=15)
                self.assertAlmostEqual(
                    flight["height_at_closest_ground_amsl_m"], float(truth["true_height_at_closest_ground_amsl_m"]), delta=8
                )
                # The fit includes the start of the turn, so it reads slightly low.
                self.assertAlmostEqual(flight["path_angle_deg"], float(truth["true_path_angle_deg"]), delta=0.3)

    def test_deliberate_problems_are_handled(self):
        by_quirk = {t["quirk"]: self.match(t) for t in self.truth if t["quirk"]}
        truth = {t["quirk"]: t for t in self.truth if t["quirk"]}

        no_geom = by_quirk["no_geometric"]
        self.assertEqual(no_geom["height_source"], "qnh")
        # QNH heights on this cold day depend on the temperature correction and on allowing for
        # METAR QNH being rounded down. Without them the error would be about 20 m.
        self.assertAlmostEqual(
            no_geom["height_at_closest_ground_amsl_m"],
            float(truth["no_geometric"]["true_height_at_closest_ground_amsl_m"]), delta=8,
        )
        sea_level = by_quirk["geometric_is_sea_level"]
        self.assertIn("heights_disagree", sea_level["flags"])
        self.assertIn("geometric_rejected", sea_level["flags"])
        self.assertEqual(sea_level["height_source"], "qnh")
        self.assertAlmostEqual(sea_level["median_qnh_minus_geometric_m"], sim.GEOID_M, delta=12)
        self.assertAlmostEqual(
            sea_level["height_at_closest_ground_amsl_m"],
            float(truth["geometric_is_sea_level"]["true_height_at_closest_ground_amsl_m"]), delta=8,
        )
        gap = by_quirk["gap_near_garden"]
        self.assertIn("gap_at_closest_point", gap["flags"])
        self.assertAlmostEqual(gap["lateral_offset_m"], float(truth["gap_near_garden"]["true_lateral_m"]), delta=20)

    def test_power_cut_and_clock_are_reported(self):
        self.assertIn("DAMAGED:", self.summary)
        self.assertIn("clock not synchronised from", self.summary)
        self.assertIn("unreadable: 1", self.summary)
        # Flagged exactly when the flight overlaps the unsynchronised period.
        start = SHORT["power_cut"] + sim.DEFAULT_TIMES["power_cut_seconds"]
        end = start + SHORT["clock_sync_seconds"]
        flagged = 0
        for flight in self.flights:
            first = aa.parse_utc(flight["first_seen_utc"][:19])
            last = aa.parse_utc(flight["last_seen_utc"][:19]) + 1
            overlapping = first <= end and last >= start
            with self.subTest(flight["callsign"]):
                self.assertEqual("clock_not_synchronised" in flight["flags"], overlapping)
            flagged += overlapping
        self.assertGreater(flagged, 0)

    def test_sound_speed_comes_from_the_metar_temperature(self):
        for flight in self.flights:
            self.assertNotIn("assumed_sound_speed", flight["flags"])
            self.assertNotIn("no_qnh", flight["flags"])

    def test_viewer_has_the_data_and_no_coordinates(self):
        with open(os.path.join(self.out, "viewer.html")) as f:
            html = f.read()
        self.assertNotIn("__ADSB_DATA__", html)
        payload = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)
        data = json.loads(payload)
        self.assertEqual(len(data["flights"]), len(self.flights))
        self.assertTrue(data["simulated"])
        self.assertEqual(set(data["tracks"]), {str(f["flight_id"]) for f in self.flights})
        for track in data["tracks"].values():
            for point in track:
                self.assertEqual(len(point), 4)
        text = json.dumps(data)
        self.assertNotIn('"lat"', text)
        self.assertNotIn('"lon"', text)

    def test_same_seed_gives_the_same_data(self):
        again = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, again)
        sim.simulate(again, seed=3, times=SHORT)
        self.assertEqual(read_csv(os.path.join(again, "truth.csv")), self.truth)


class Folders(unittest.TestCase):
    def test_refuses_a_folder_it_did_not_make(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        with open(os.path.join(folder, "precious.txt"), "w") as f:
            f.write("keep")
        with self.assertRaises(SystemExit):
            sim.prepare_folder(folder)
        self.assertTrue(os.path.exists(os.path.join(folder, "precious.txt")))

    def test_rerunning_replaces_old_logs(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        times = {**SHORT, "end": SHORT["start"] + 1200, "runway_change": SHORT["start"] + 600}
        sim.simulate(folder, times=times)
        first = sorted(os.listdir(os.path.join(folder, "logs", "adsb")))
        sim.simulate(folder, times=times)
        self.assertEqual(sorted(os.listdir(os.path.join(folder, "logs", "adsb"))), first)


class Weather(unittest.TestCase):
    def test_metars_parse_back(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "w.csv")
        sim.write_weather(path, SHORT)
        weather = aa.Weather.load(path)
        report_time = max(t for t in weather.times if t <= SHORT["start"])
        qnh, temp = weather.at(SHORT["start"])
        # Reported rounded down, then half a hPa added back by the analysis.
        self.assertEqual(qnh, math.floor(sim.qnh_at(report_time)) + 0.5)
        self.assertEqual(temp, round(sim.temp_at(report_time)))


if __name__ == "__main__":
    unittest.main()

"""Tests for adsb.analyse, using made-up flights with known geometry. They aren't real ADS-B data.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import csv
import datetime as dt
import gzip
import json
import math
import os
import shutil
import tempfile
import unittest

from adsb.analyse import DEFAULTS, run
from adsb.atmosphere import geometric_altitude_m, qnh_altitude_m, sound_speed
from adsb.common import FEET, format_utc, parse_utc
from adsb.flight import analyse_flight
from adsb.geometry import Site, closest_approach, garden_side
from adsb.logs import log_paths
from adsb.tracks import FlightBuilder, parse_point
from adsb.weather import Weather

SITE_LAT, SITE_LON = 51.5, 0.1
GROUND_M, MIC_M = 3.0, 3.0
GEOID_M = 45.0
START = 1_793_000_000.0
CONFIG = {
    "site": {"lat": SITE_LAT, "lon": SITE_LON, "ground_elevation_m": GROUND_M, "mic_height_m": MIC_M},
    "geoid_height_m": GEOID_M,
}
SITE = Site(CONFIG)
SETTINGS = dict(DEFAULTS)


def pressure_altitude_ft(height_m, qnh):
    return height_m / FEET + 145366.45 * (1 - (qnh / 1013.25) ** 0.190284)


def make_records(angle=5.5, offset_north=-500.0, heading_west=True, qnh=1031.0, geoid=GEOID_M,
                 start=START, code="abc123", kind="E190", callsign="CFE101  ", rate=2.0,
                 round_altitudes=False, height_at_site=None, speed=70.0, span=9000.0):
    """A straight flight at constant speed, passing the garden at a known offset and height."""
    if height_at_site is None:
        height_at_site = 4000 * math.tan(math.radians(angle))
    direction = -1 if heading_west else 1
    records = []
    steps = int(2 * span / speed * rate)
    for n in range(steps + 1):
        east = -direction * span + direction * n * speed / rate
        travelled = direction * east
        slope = math.tan(math.radians(angle))
        height = height_at_site + (-travelled * slope if heading_west else travelled * slope)
        baro = pressure_altitude_ft(height, qnh)
        geom = (height + geoid) / FEET
        if round_altitudes:
            baro, geom = 25 * round(baro / 25), 25 * round(geom / 25)
        lat = SITE_LAT + math.degrees(offset_north / SITE.metres_per_rad_north)
        lon = SITE_LON + math.degrees(east / SITE.metres_per_rad_east)
        records.append({
            "now": start + n / rate, "hex": code, "type": "adsb_icao", "flight": callsign, "r": "G-TEST",
            "t": kind, "alt_baro": baro, "alt_geom": geom, "gs": speed * 1.94384,
            "track": 270 if heading_west else 90, "lat": lat, "lon": lon, "nic": 8, "rc": 186,
            "seen_pos": 0.0, "rssi": -10.0,
        })
    return records


def weather(qnh=1031.0, temp=15.0, t=START - 600):
    return Weather([(t, qnh, temp)])


def flight_from(records, wx=None, unsynced=()):
    parsed = [parse_point(r, SITE, SETTINGS) for r in records]
    points = [p[1] for p in parsed if p]
    return analyse_flight(1, records[0]["hex"], points, SITE, wx or weather(), SETTINGS, unsynced)


class Heights(unittest.TestCase):
    def test_no_correction_at_standard_pressure(self):
        self.assertAlmostEqual(qnh_altitude_m(1000, 1013.25), 304.8, places=3)

    def test_about_27_feet_per_hpa(self):
        change_ft = (qnh_altitude_m(1000, 1023.25) - qnh_altitude_m(1000, 1013.25)) / FEET
        self.assertAlmostEqual(change_ft / 10, 27.3, delta=0.5)

    def test_low_pressure_lowers_true_height(self):
        self.assertLess(qnh_altitude_m(1000, 990), 304.8)

    def test_geometric_removes_the_geoid(self):
        self.assertAlmostEqual(geometric_altitude_m(1000, 45), 304.8 - 45, places=6)


class Corrections(unittest.TestCase):
    def test_temperature_correction_lowers_heights_on_a_cold_day(self):
        standard = qnh_altitude_m(1300, 1013.25)
        cold = qnh_altitude_m(1300, 1013.25, temp_c=0)
        self.assertAlmostEqual(qnh_altitude_m(1300, 1013.25, temp_c=15), standard, places=6)
        # About 4% lower for 15 °C below standard.
        self.assertAlmostEqual(cold / standard, 1 - 15 / 288, delta=0.005)

    def test_geometric_height_is_rejected_when_it_disagrees(self):
        records = make_records(geoid=0.0)  # Aircraft sending height above sea level as geometric
        flight, _ = flight_from(records)
        self.assertEqual(flight["height_source"], "qnh")
        self.assertIn("geometric_rejected", flight["flags"])
        self.assertAlmostEqual(
            flight["height_at_closest_ground_amsl_m"], 4000 * math.tan(math.radians(5.5)), delta=1
        )

    def test_geometric_kept_when_there_is_no_qnh_to_compare(self):
        flight, _ = flight_from(make_records(geoid=0.0), wx=Weather())
        self.assertEqual(flight["height_source"], "geometric")

    def test_garden_side_suits_the_track_direction(self):
        self.assertEqual(garden_side(270, 0, -500), "north")
        self.assertEqual(garden_side(5, 400, 0), "west")
        self.assertEqual(garden_side(185, -400, 0), "east")


class Streaming(unittest.TestCase):
    def test_restart_files_are_read_after_the_file_they_follow(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        for name in ("2026-11-05T12.1.jsonl.gz", "2026-11-05T12.jsonl.gz", "2026-11-05T11.jsonl.gz", "2026-11-05T12.10.jsonl.gz", "2026-11-05T12.2.jsonl.gz"):
            open(os.path.join(folder, name), "wb").close()
        names = [os.path.basename(p) for p in log_paths(folder)]
        self.assertEqual(names, [
            "2026-11-05T11.jsonl.gz", "2026-11-05T12.jsonl.gz", "2026-11-05T12.1.jsonl.gz",
            "2026-11-05T12.2.jsonl.gz", "2026-11-05T12.10.jsonl.gz",
        ])
        start = parse_utc("2026-11-05 15:00")  # More than an hour after the last file ends
        self.assertEqual(log_paths(folder, start=start), [])

    def test_builder_finishes_flights_after_a_gap_either_way(self):
        points = [parse_point(r, SITE, SETTINGS)[1] for r in make_records(span=500)]
        builder = FlightBuilder(600)
        for p in points:
            self.assertIsNone(builder.add("abc", p))
        self.assertEqual(builder.finish_quiet(points[-1].t + 599), [])
        finished = builder.add("abc", points[0]._replace(t=points[0].t - 3600))  # Clock stepped back
        self.assertEqual(len(finished[2]), len(points))
        self.assertEqual(len(builder.finish_quiet(points[-1].t + 10000)), 1)


class Geometry(unittest.TestCase):
    def test_local_scale_at_this_latitude(self):
        east, north = SITE.local_xy(SITE_LAT + 0.01, SITE_LON + 0.01)
        self.assertAlmostEqual(north, 1112.6, delta=1.5)
        self.assertAlmostEqual(east, 693.5, delta=1.5)

    def test_sound_speed(self):
        self.assertAlmostEqual(sound_speed(15), 340.3, places=1)
        self.assertAlmostEqual(sound_speed(0), 331.3, places=1)

    def test_closest_point_between_samples(self):
        i, u, distance = closest_approach([(-100.0, 50.0), (100.0, 50.0)])
        self.assertEqual(i, 0)
        self.assertAlmostEqual(u, 0.5)
        self.assertAlmostEqual(distance, 50.0)


class Arrival(unittest.TestCase):
    def setUp(self):
        self.flight, self.rows = flight_from(make_records())

    def test_identity_is_cleaned(self):
        self.assertEqual(self.flight["callsign"], "CFE101")
        self.assertEqual(self.flight["type"], "E190")
        self.assertEqual(self.flight["registration"], "G-TEST")

    def test_recovers_the_known_offset_side_and_height(self):
        self.assertAlmostEqual(self.flight["lateral_offset_m"], 500.0, delta=0.5)
        self.assertEqual(self.flight["garden_side"], "north")
        expected = 4000 * math.tan(math.radians(5.5))
        self.assertAlmostEqual(self.flight["height_at_closest_ground_amsl_m"], expected, delta=0.5)

    def test_path_is_labelled_with_its_angle(self):
        self.assertEqual(self.flight["label"], "rwy27_arrival")
        self.assertEqual(self.flight["path_trend"], "descending")
        self.assertAlmostEqual(self.flight["path_angle_deg"], 5.5, delta=0.02)

    def test_closest_slant_and_sound_delay(self):
        # The closest point comes after the overhead point as the aircraft descends.
        above_mic = 4000 * math.tan(math.radians(5.5)) - (GROUND_M + MIC_M)
        at_side = math.hypot(500, above_mic)
        self.assertLess(self.flight["closest_slant_m"], at_side)
        self.assertGreater(self.flight["closest_slant_m"], at_side - 15)
        self.assertAlmostEqual(self.flight["sound_speed_m_s"], sound_speed(15))
        self.assertAlmostEqual(
            self.flight["sound_delay_s"], self.flight["closest_slant_m"] / sound_speed(15), places=6
        )
        self.assertAlmostEqual(self.flight["angle_from_vertical_deg"], 52.5, delta=2.0)

    def test_arrival_time_is_emission_plus_delay(self):
        row = self.rows[len(self.rows) // 2]
        emitted, arrived = parse_utc(row["emission_time_utc"][:19]), parse_utc(row["arrival_time_utc"][:19])
        self.assertAlmostEqual(arrived - emitted, row["sound_delay_s"], delta=1.01)
        self.assertAlmostEqual(row["slant_m"] / row["sound_delay_s"], sound_speed(15))

    def test_both_heights_agree_when_weather_is_right(self):
        self.assertEqual(self.flight["height_source"], "geometric")
        self.assertAlmostEqual(self.flight["median_qnh_minus_geometric_m"], 0.0, delta=0.01)
        self.assertEqual(self.flight["flags"], "")


class OtherFlights(unittest.TestCase):
    def test_a_4_49_degree_approach_is_distinguishable(self):
        flight, _ = flight_from(make_records(angle=4.49))
        self.assertAlmostEqual(flight["path_angle_deg"], 4.49, delta=0.02)

    def test_25_foot_steps_still_give_a_usable_angle_and_height(self):
        flight, _ = flight_from(make_records(angle=4.49, round_altitudes=True))
        self.assertAlmostEqual(flight["path_angle_deg"], 4.49, delta=0.1)
        expected = 4000 * math.tan(math.radians(4.49))
        self.assertAlmostEqual(flight["height_at_closest_ground_amsl_m"], expected, delta=8)

    def test_departure(self):
        flight, _ = flight_from(make_records(angle=7, heading_west=False, offset_north=100.0))
        self.assertEqual(flight["label"], "rwy09_departure")
        self.assertEqual(flight["path_trend"], "climbing")
        self.assertEqual(flight["garden_side"], "south")

    def test_high_overflight_is_other(self):
        flight, _ = flight_from(make_records(angle=0, height_at_site=2500.0))
        self.assertEqual(flight["label"], "other")
        self.assertEqual(flight["path_trend"], "level")

    def test_track_ending_before_the_garden_is_flagged(self):
        records = make_records()
        flight, _ = flight_from(records[: len(records) // 3])
        self.assertIn("closest_point_at_track_end", flight["flags"])

    def test_gap_at_the_closest_point_is_flagged(self):
        records = make_records()
        middle = len(records) // 2
        flight, _ = flight_from(records[: middle - 30] + records[middle + 30 :])
        self.assertIn("gap_at_closest_point", flight["flags"])
        self.assertAlmostEqual(flight["lateral_offset_m"], 500.0, delta=1)

    def test_single_position_does_not_fail(self):
        flight, rows = flight_from(make_records()[:1])
        self.assertEqual(len(rows), 1)
        self.assertIn("closest_point_at_track_end", flight["flags"])
        self.assertEqual(flight["label"], "other")


class HeightSources(unittest.TestCase):
    def test_uses_qnh_when_aircraft_has_no_geometric_altitude(self):
        records = make_records()
        for r in records:
            del r["alt_geom"]
        flight, _ = flight_from(records)
        self.assertEqual(flight["height_source"], "qnh")
        self.assertAlmostEqual(
            flight["height_at_closest_ground_amsl_m"], 4000 * math.tan(math.radians(5.5)), delta=0.5
        )

    def test_uses_qnh_when_geoid_is_unknown(self):
        site = Site({"site": CONFIG["site"]})
        points = [parse_point(r, site, SETTINGS)[1] for r in make_records()]
        flight, _ = analyse_flight(1, "abc123", points, site, weather(), SETTINGS)
        self.assertEqual(flight["height_source"], "qnh")

    def test_wrong_pressure_makes_heights_disagree(self):
        flight, _ = flight_from(make_records(qnh=1031.0), wx=weather(qnh=1013.0))
        self.assertIn("heights_disagree", flight["flags"])
        self.assertAlmostEqual(flight["median_qnh_minus_geometric_m"], -18 * 8.3, delta=6)
        # The weather is at fault here, not the aircraft, so geometric height is kept.
        self.assertEqual(flight["height_source"], "geometric")
        self.assertNotIn("geometric_rejected", flight["flags"])

    def test_no_weather_or_altitude_is_flagged_not_fatal(self):
        records = make_records()
        for r in records:
            del r["alt_geom"]
        flight, rows = flight_from(records, wx=Weather())
        self.assertEqual(flight["height_source"], "none")
        for flag in ("no_qnh", "no_height", "assumed_sound_speed"):
            self.assertIn(flag, flight["flags"])
        self.assertAlmostEqual(flight["lateral_offset_m"], 500.0, delta=0.5)
        self.assertIsNone(flight["closest_slant_m"])
        self.assertIsNone(rows[0]["slant_m"])

    def test_unsynchronised_clock_is_flagged(self):
        flight, _ = flight_from(make_records(), unsynced=[(START + 5, START + 20)])
        self.assertIn("clock_not_synchronised", flight["flags"])


class Records(unittest.TestCase):
    def good(self):
        return make_records()[0]

    def test_rejects_what_it_cant_use(self):
        far = dict(self.good(), lat=SITE_LAT + 1)
        cases = {
            "ground": dict(self.good(), alt_baro="ground"),
            "too high": dict(self.good(), alt_baro=35000),
            "old position": dict(self.good(), seen_pos=5.0),
            "poor position": dict(self.good(), nic=2),
            "far": far,
        }
        for name, record in cases.items():
            with self.subTest(name):
                self.assertIsNone(parse_point(record, SITE, SETTINGS))

    def test_missing_fields_are_tolerated(self):
        record = {"now": START, "hex": "abc123", "lat": SITE_LAT, "lon": SITE_LON}
        _, point = parse_point(record, SITE, SETTINGS)
        self.assertIsNone(point.baro_ft)
        self.assertIsNone(point.callsign)

    def test_position_time_allows_for_its_age(self):
        _, point = parse_point(dict(self.good(), seen_pos=1.5), SITE, SETTINGS)
        self.assertAlmostEqual(point.t, START - 1.5)

    def test_flights_split_on_a_long_gap_and_drop_duplicates(self):
        points = [parse_point(r, SITE, SETTINGS)[1] for r in make_records(span=500)]
        later = [p._replace(t=p.t + 7200) for p in points]
        builder = FlightBuilder(600)
        flights = [f for p in sorted(later + points + points[:3]) if (f := builder.add("x", p))]
        flights += builder.finish_all()
        self.assertEqual([len(f[2]) for f in flights], [len(points), len(points)])


class WeatherFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def load(self, text):
        path = os.path.join(self.dir, "w.csv")
        with open(path, "w") as f:
            f.write(text)
        return Weather.load(path)

    def test_reads_metar_archive_format(self):
        wx = self.load(
            "#comment\nstation,valid,metar\n"
            "EGLC,2026-11-04 00:20,EGLC 040020Z AUTO 06007KT 9999 OVC037 10/05 Q1031\n"
            "EGLC,2026-11-04 00:50,EGLC 040050Z AUTO 06007KT 9999 M02/M05 Q0998\n"
            "EGLC,2026-11-04 01:20,EGLC 040120Z NIL\n"
        )
        first = parse_utc("2026-11-04 00:20")
        # METAR QNH is rounded down, so half a hPa is added back.
        self.assertEqual(wx.at(first + 60), (1031.5, 10.0))
        self.assertEqual(wx.at(first + 1860), (998.5, -2.0))

    def test_too_early_or_too_old_gives_nothing(self):
        wx = self.load("time,qnh_hpa,temp_c\n2026-11-04T00:00:00Z,1020,8\n")
        start = parse_utc("2026-11-04 00:00")
        self.assertEqual(wx.at(start - 1), (None, None))
        self.assertEqual(wx.at(start + 3 * 3600), (1020.0, 8.0))
        self.assertEqual(wx.at(start + 3 * 3600 + 1), (None, None))


class WholeRun(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.logs = os.path.join(self.dir, "logs")
        os.makedirs(os.path.join(self.logs, "adsb"))
        os.makedirs(os.path.join(self.logs, "health"))
        self.out = os.path.join(self.dir, "out")
        self.weather = os.path.join(self.dir, "w.csv")
        with open(self.weather, "w") as f:
            f.write(f"time,qnh_hpa,temp_c\n{format_utc(START - 600)[:19]},1031,15\n")

    def write_log(self, name, records, extra=b""):
        with gzip.open(os.path.join(self.logs, "adsb", name), "wb") as f:
            for record in records:
                f.write(json.dumps(record).encode() + b"\n")
            f.write(extra)

    def test_end_to_end_with_a_damaged_file_and_a_bad_line(self):
        arrival = make_records()
        departure = make_records(angle=7, heading_west=False, offset_north=200.0, code="def456",
                                 kind="A20N", start=START + 3600, callsign="BAW1")
        overflight = make_records(angle=0, height_at_site=2500.0, code="fed789", start=START + 60)
        self.write_log("a.jsonl.gz", arrival + overflight, extra=b'{"partial\n')
        self.write_log("b.jsonl.gz", departure[: len(departure) // 2])
        full = os.path.join(self.logs, "adsb", "c.jsonl.gz")
        self.write_log("c.jsonl.gz", departure[len(departure) // 2 :])
        with open(full, "rb") as f:
            data = f.read()
        with open(full, "wb") as f:
            f.write(data[: len(data) // 2])

        flights, summary = run(CONFIG, self.logs, self.out, self.weather)
        with open(os.path.join(self.out, "positions.csv"), newline="") as f:
            positions = list(csv.DictReader(f))

        labels = {f["hex"]: f["label"] for f in flights}
        self.assertEqual(labels["abc123"], "rwy27_arrival")
        self.assertEqual(labels["fed789"], "other")
        self.assertEqual({p["hex"] for p in positions} & {"fed789"}, set())
        self.assertIn("DAMAGED: c.jsonl.gz", summary)
        self.assertIn("unreadable: 1", summary)
        with open(os.path.join(self.out, "flights.csv"), newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["hex"], "abc123")
        self.assertAlmostEqual(float(rows[0]["lateral_offset_m"]), 500, delta=1)
        self.assertTrue(os.path.exists(os.path.join(self.out, "positions.csv")))

    def test_warns_about_missing_inputs_and_unsynchronised_clock(self):
        self.write_log("a.jsonl.gz", make_records())
        with open(os.path.join(self.logs, "health", "d.jsonl"), "w") as f:
            f.write(json.dumps({"time": START, "clock": {"synchronised": False}}) + "\nnot json\n")
        config = {"site": CONFIG["site"]}
        flights, summary = run(config, self.logs, self.out)
        self.assertIn("no weather file", summary)
        self.assertIn("geoid_height_m not set", summary)
        self.assertIn("Health records: 1", summary)
        self.assertIn("clock not synchronised from", summary)
        self.assertIn("clock_not_synchronised", flights[0]["flags"])

    def test_reports_long_gaps_and_handles_no_data(self):
        self.write_log("a.jsonl.gz", make_records() + make_records(start=START + 7200))
        _, summary = run(CONFIG, self.logs, self.out, self.weather)
        self.assertIn("GAP over 30 minutes", summary)
        flights, summary = run(CONFIG, os.path.join(self.dir, "empty"), self.out)
        self.assertEqual(flights, [])
        self.assertIn("Flights: 0", summary)

    def write_health(self, entries):
        with open(os.path.join(self.logs, "health", "d.jsonl"), "w") as f:
            f.write("".join(json.dumps(e) + "\n" for e in entries))

    def test_a_gap_with_the_logger_listening_is_quiet_not_lost(self):
        self.write_log("a.jsonl.gz", make_records() + make_records(start=START + 7200))
        healthy = [{"time": START + t, "connected": True, "lines": 50} for t in range(0, 7500, 300)]
        self.write_health(healthy)
        _, summary = run(CONFIG, self.logs, self.out, self.weather)
        self.assertIn("QUIET over 30 minutes", summary)
        self.assertNotIn("GAP", summary)
        # A disconnection, or a stretch with no health records, means data may have been lost.
        for broken in (
            healthy[:10] + [dict(healthy[10], event="disconnected", connected=False)] + healthy[11:],
            healthy[:10] + healthy[15:],
        ):
            with self.subTest(len(broken)):
                self.write_health(broken)
                _, summary = run(CONFIG, self.logs, self.out, self.weather)
                self.assertIn("GAP over 30 minutes", summary)

    def test_lines_stamped_by_an_unsynchronised_clock_are_counted(self):
        records = make_records()
        self.write_log("a.jsonl.gz", records)
        middle = records[len(records) // 2]["now"]
        self.write_health([
            {"time": middle, "clock": {"synchronised": False}},
            {"time": middle + 10, "clock": {"synchronised": True}},
        ])
        _, summary = run(CONFIG, self.logs, self.out, self.weather)
        expected = sum(middle <= r["now"] <= middle + 10 for r in records)
        self.assertIn(f"WARNING: {expected} lines were stamped while the clock wasn't synchronised", summary)

    def test_a_line_far_outside_its_files_hour_is_skipped(self):
        name = dt.datetime.fromtimestamp(START, dt.timezone.utc).strftime("%Y-%m-%dT%H.jsonl.gz")
        records = make_records()
        bogus = dict(records[5], now=4_102_444_800.0)  # 2100-01-01
        self.write_log(name, records[:10] + [bogus] + records[10:])
        flights, summary = run(CONFIG, self.logs, self.out, self.weather)
        self.assertEqual(len(flights), 1)
        self.assertIn("WARNING: 1 lines skipped because their time was far outside their file's hour", summary)
        self.assertNotIn("2100", summary)

    def test_one_bad_time_does_not_split_the_flights_after_it(self):
        # Enough positions for the periodic check for quiet flights to run, in a file whose name
        # has no hour, so the bad time isn't skipped.
        records = make_records(rate=40.0, speed=30.0)
        self.assertGreater(len(records), 20000)
        bogus = dict(records[5], hex="zzz999", now=4_102_444_800.0)
        self.write_log("a.jsonl.gz", records[:10] + [bogus] + records[10:])
        flights, _ = run(CONFIG, self.logs, self.out, self.weather)
        self.assertEqual(sorted(f["hex"] for f in flights), ["abc123", "zzz999"])

    def test_date_range_keeps_only_that_period(self):
        self.write_log("a.jsonl.gz", make_records() + make_records(start=START + 86400, code="def456"))
        flights, _ = run(CONFIG, self.logs, self.out, self.weather, start=START + 43200)
        self.assertEqual([f["hex"] for f in flights], ["def456"])
        flights, _ = run(CONFIG, self.logs, self.out, self.weather, end=START + 43200)
        self.assertEqual([f["hex"] for f in flights], ["abc123"])

    def test_viewer_data_cannot_end_its_script_block(self):
        records = make_records(callsign="<b>X</b>")
        self.write_log("a.jsonl.gz", records)
        run(CONFIG, self.logs, self.out, self.weather)
        with open(os.path.join(self.out, "viewer.html")) as f:
            html = f.read()
        self.assertNotIn("<b>X</b>", html.split('<script id="data"')[1].split("</script>")[0])

    def test_logs_are_not_changed(self):
        self.write_log("a.jsonl.gz", make_records())
        path = os.path.join(self.logs, "adsb", "a.jsonl.gz")
        with open(path, "rb") as f:
            before = f.read()
        run(CONFIG, self.logs, self.out, self.weather)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_site_config_is_checked(self):
        with self.assertRaisesRegex(ValueError, "ground_elevation_m"):
            Site({"site": {"lat": 51.5, "lon": 0.1}})


if __name__ == "__main__":
    unittest.main()

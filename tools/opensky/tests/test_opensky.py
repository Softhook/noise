"""Tests for the OpenSky tool, using made-up states and a fake Trino client. Nothing touches the network."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import math
import os
import tempfile
import unittest
from unittest import mock

import gzip
import json

from opensky import aircraft, compare, geometry, logs, passes, trino, webtrak
from opensky.common import NMT6, number, parse_time

T0 = parse_time("2026-11-05T09:00:00Z")  # The start of an hour partition
EAST_M = 1 / (math.radians(1) * 6371000 * math.cos(math.radians(NMT6[0])))  # Degrees of longitude per metre


def state(t, x_m, y_m=0.0, icao24="abc123", **extra):
    """A state vector x_m east and y_m north of NMT6, its position received at t."""
    lat = NMT6[0] + math.degrees(y_m / 6371000)
    lon = NMT6[1] + x_m * EAST_M
    return {"time": int(t), "icao24": icao24, "callsign": "TEST1   ", "lat": lat, "lon": lon,
            "baroaltitude": 600.0, "geoaltitude": 700.0, "onground": False, "lastposupdate": float(t),
            "lastcontact": float(t), "receivers": 40, **extra}


def flyover(t_closest, y_m=100.0, icao24="abc123", speed_ms=100.0, span_s=60):
    """States once a second for an aircraft flying east, passing y_m north of NMT6 at t_closest."""
    return [state(t_closest + dt, dt * speed_ms, y_m, icao24) for dt in range(-span_s, span_s + 1)]


DB = {"abc123": aircraft.Aircraft("G-TEST", "E190", 0, "EMBRAER ERJ-190-100")}


def write_db(path, lines):
    with gzip.open(path, "wt") as f:
        f.write("".join(line + "\n" for line in lines))


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self.rows)


class FakeTrino:
    """Records each query and answers with the states in its hour partition."""

    def __init__(self, states):
        self.states, self.calls = states, []

    def query(self, sql, cached=True):
        self.calls.append((sql, cached))
        hour = int(sql.split("WHERE hour = ")[1].split("\n")[0])
        return FakeFrame(s for s in self.states if hour <= s["time"] < hour + 3600)


class TestCommon(unittest.TestCase):
    def test_parse_time_defaults_to_utc(self):
        self.assertEqual(parse_time("2026-11-05T09:00"), T0)
        self.assertEqual(parse_time("2026-11-05T09:00Z"), T0)

    def test_number_treats_missing_values_as_none(self):
        self.assertIsNone(number(None))
        self.assertIsNone(number(float("nan")))
        self.assertIsNone(number(""))
        self.assertEqual(number("12.5"), 12.5)


class TestGeometry(unittest.TestCase):
    def test_closest_approach_interpolates_between_points(self):
        # Points 1 km either side of NMT6, 200 m north: the closest approach is halfway between
        points = [(0, *self.latlon(-1000, 200)), (20, *self.latlon(1000, 200))]
        t, d = geometry.closest_approach(points)
        self.assertAlmostEqual(t, 10, places=3)
        self.assertAlmostEqual(d, 200, delta=0.5)

    def test_closest_approach_of_one_point(self):
        t, d = geometry.closest_approach([(5, *self.latlon(300, 400))])
        self.assertEqual(t, 5)
        self.assertAlmostEqual(d, 500, delta=0.5)

    def test_box_around_is_square_on_the_ground(self):
        lat0, lat1, lon0, lon1 = geometry.box_around(NMT6, 5000)
        north = geometry.local_xy(lat1, NMT6[1])[1]
        east = geometry.local_xy(NMT6[0], lon1)[0]
        self.assertAlmostEqual(north, 5000, delta=1)
        self.assertAlmostEqual(east, 5000, delta=1)

    @staticmethod
    def latlon(x_m, y_m):
        return NMT6[0] + math.degrees(y_m / 6371000), NMT6[1] + x_m * EAST_M


class TestTrino(unittest.TestCase):
    BOX = geometry.box_around(NMT6, 5000)

    def test_hour_partitions(self):
        self.assertEqual(trino.hour_partitions(T0 + 60, T0 + 3600 + 60), [T0, T0 + 3600])
        self.assertEqual(trino.hour_partitions(T0, T0 + 3599), [T0])
        self.assertEqual(trino.hour_partitions(T0 - 300, T0 + 3600), [T0 - 3600, T0])  # Not the next hour
        self.assertEqual(trino.hour_partitions(T0 + 5, T0 + 5), [T0])

    def test_every_query_filters_on_its_hour_partition(self):
        client = FakeTrino([])
        trino.fetch_states(T0 - 300, T0 + 2 * 3600 + 300, self.BOX, client, log=io.StringIO())
        hours = [T0 - 3600, T0, T0 + 3600, T0 + 7200]
        self.assertEqual(len(client.calls), len(hours))
        for (sql, _), hour in zip(client.calls, hours):
            self.assertIn(f"WHERE hour = {int(hour)}\n", sql)
            self.assertIn(f"time - lastcontact <= {trino.STALE_S}", sql)
            self.assertIn("lat BETWEEN", sql)
            self.assertIn("lon BETWEEN", sql)

    def test_drops_ground_states_and_repeated_positions_in_the_query(self):
        sql = trino.states_sql(int(T0), self.BOX)
        self.assertIn("AND NOT onground\n", sql)
        self.assertIn("GROUP BY icao24, lastposupdate", sql)
        self.assertNotIn("ORDER BY", sql)

    def test_overlapping_periods_send_the_same_queries(self):
        # So pyopensky's cache, keyed on the SQL, serves every hour a previous run fetched
        a, b = FakeTrino([]), FakeTrino([])
        trino.fetch_states(T0 + 60, T0 + 3600 + 60, self.BOX, a, log=io.StringIO())
        trino.fetch_states(T0 + 1800, T0 + 3600 + 1200, self.BOX, b, log=io.StringIO())
        self.assertEqual(a.calls, b.calls)

    def test_rows_are_cut_to_the_period(self):
        states = [state(T0 + 10, 0), state(T0 + 100, 0), state(T0 + 3000, 0)]
        rows = trino.fetch_states(T0 + 50, T0 + 2000, self.BOX, FakeTrino(states), log=io.StringIO())
        self.assertEqual([r["time"] for r in rows], [T0 + 100])

    def test_hours_not_yet_started_are_not_queried(self):
        with mock.patch("opensky.trino.time.time", return_value=T0 + 1800):
            client = FakeTrino([])
            trino.fetch_states(T0 - 300, T0 + 3 * 3600, self.BOX, client, log=io.StringIO())
        self.assertEqual(len(client.calls), 2)
        self.assertEqual([cached for _, cached in client.calls], [False, False])

    def test_only_settled_hours_are_cached(self):
        with mock.patch("opensky.trino.time.time", return_value=T0 + 3600 + trino.SETTLED_S + 1):
            client = FakeTrino([])
            trino.fetch_states(T0, T0 + 2 * 3600 - 1, self.BOX, client, log=io.StringIO())
        self.assertEqual([cached for _, cached in client.calls], [True, False])

    def test_returns_states_from_every_hour(self):
        states = [state(T0 - 10, 0), state(T0 + 10, 0)]
        rows = trino.fetch_states(T0 - 60, T0 + 60, self.BOX, FakeTrino(states), log=io.StringIO())
        self.assertEqual([r["time"] for r in rows], [T0 - 10, T0 + 10])


class TestPasses(unittest.TestCase):
    def test_repeated_positions_and_ground_states_are_dropped(self):
        states = [state(T0, 0), state(T0 + 1, 0, lastposupdate=float(T0)), state(T0 + 2, 50, onground=True),
                  state(T0 + 3, 100, lat=float("nan"))]
        self.assertEqual([p["t"] for p in passes.positions(states)], [T0])

    def test_positions_without_an_onground_column_are_airborne(self):
        # Trino's query drops ground states and leaves the column out
        rows = [{k: v for k, v in state(T0, 0).items() if k != "onground"}]
        self.assertEqual([p["t"] for p in passes.positions(rows)], [T0])

    def test_positions_are_timed_by_when_they_were_received(self):
        points = passes.positions([state(T0 + 5, 0, lastposupdate=float(T0 + 3))])
        self.assertEqual(points[0]["t"], T0 + 3)

    def test_split_passes_on_long_gaps(self):
        points = [{"t": t} for t in (0, 10, 10 + passes.PASS_GAP_S, 20 + 2 * passes.PASS_GAP_S)]
        self.assertEqual([len(g) for g in passes.split_passes(points)], [3, 1])

    def test_a_flyover_gives_one_pass(self):
        (p,) = passes.passes_near(flyover(T0 + 600), T0, T0 + 3600, radius_m=3000, geoid_m=45)
        self.assertAlmostEqual(p.t, T0 + 600, delta=0.01)
        self.assertEqual(p.distance_m, 100)
        self.assertEqual(p.geo_msl_m, 655)
        self.assertEqual(p.baro_alt_m, 600)
        self.assertEqual(p.callsign, "TEST1")
        self.assertEqual(p.point_gap_s, 1.0)
        self.assertEqual(p.receivers, 40)
        self.assertEqual(p.positions, 121)

    def test_passes_outside_the_radius_or_period_are_dropped(self):
        states = flyover(T0 + 600, y_m=3500, icao24="far") + flyover(T0 - 30, icao24="early")
        self.assertEqual(passes.passes_near(states, T0, T0 + 3600, 3000, 45), [])

    def test_two_visits_by_one_aircraft_are_two_passes(self):
        states = flyover(T0 + 600) + flyover(T0 + 1800)
        found = passes.passes_near(states, T0, T0 + 3600, 3000, 45)
        self.assertEqual([round(p.t) for p in found], [T0 + 600, T0 + 1800])

    def test_missing_heights_are_blank_in_the_csv(self):
        states = [{**s, "geoaltitude": None} for s in flyover(T0 + 600)]
        (p,) = passes.passes_near(states, T0, T0 + 3600, 3000, 45)
        self.assertIsNone(p.geo_msl_m)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out", "passes.csv")
            compare.write_csv([p], path)
            with open(path, newline="") as f:
                (row,) = csv.DictReader(f)
        self.assertEqual(row["geo_msl_m"], "")
        self.assertEqual(row["closest_utc"], "2026-11-05T09:10:00Z")


class TestWebTrak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        os.makedirs(os.path.join(self.dir, "aircraft"))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, fields, rows):
        with open(os.path.join(self.dir, name), "w", newline="") as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(rows)

    def test_radar_pass_found_from_points_either_side_of_the_period(self):
        # Track 1's closest point is just after the end, track 2's just before it
        fields = ["time_utc", "track", "callsign", "type", "distance_m", "altitude_m"]
        self.write("aircraft/2026-11-05.csv", fields, [
            {"time_utc": "2026-11-05T09:59:50Z", "track": "1", "callsign": "A", "type": "E190", "distance_m": "500",
             "altitude_m": "700"},
            {"time_utc": "2026-11-05T10:00:10Z", "track": "1", "callsign": "A", "type": "E190", "distance_m": "100",
             "altitude_m": "690"},
            {"time_utc": "2026-11-05T09:59:00Z", "track": "2", "callsign": "B", "type": "DH8D", "distance_m": "80",
             "altitude_m": ""},
            {"time_utc": "2026-11-05T10:00:30Z", "track": "2", "callsign": "B", "type": "DH8D", "distance_m": "900",
             "altitude_m": ""},
        ])
        end = parse_time("2026-11-05T10:00:00Z")
        found = webtrak.radar_passes(T0, end, 3000, pad_s=300, webtrak_dir=self.dir)
        self.assertEqual([(p.callsign, p.distance_m, p.altitude_m) for p in found], [("B", 80.0, None)])

    def test_events(self):
        self.write("events.csv", ["lmax_time_local", "lmax_db"], [
            {"lmax_time_local": "2026-11-05T09:02:53+00:00", "lmax_db": "71.04"},
            {"lmax_time_local": "2026-11-05T11:02:53+00:00", "lmax_db": "65"},
        ])
        found = webtrak.events(T0, T0 + 3600, webtrak_dir=self.dir)
        self.assertEqual([(e.t, e.lmax_db) for e in found], [(T0 + 173, 71.04)])


class TestCompare(unittest.TestCase):
    def test_pair_is_one_to_one_closest_first(self):
        a = [webtrak.Event(100, 70), webtrak.Event(200, 70)]
        b = [webtrak.Event(105, 70), webtrak.Event(300, 70)]
        pairs = compare.pair(a, b, 90)
        self.assertEqual([(x and x.t, y and y.t) for x, y in pairs], [(100, 105), (200, None), (None, 300)])

    def test_run_end_to_end_with_a_fake_client(self):
        args = argparse.Namespace(begin="2026-11-05T09:00Z", end="2026-11-05T10:00Z", radius=3000, geoid=45)
        client = FakeTrino(flyover(T0 + 600))
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(compare, "OUT_DIR", tmp), \
                mock.patch.object(webtrak, "WEBTRAK_DIR", tmp), \
                mock.patch("opensky.webtrak.radar_passes", return_value=[]), \
                mock.patch("opensky.webtrak.events", return_value=[]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            compare.run(args, client, DB)
            written = os.listdir(tmp)
        self.assertEqual(written, ["nmt6-trino-2026-11-05T0900.csv"])
        self.assertIn(" E190 ", out.getvalue())
        self.assertIn("In both: 0. WebTrak only: 0. OpenSky only: 1.", out.getvalue())
        self.assertTrue(all("hour = " in sql for sql, _ in client.calls))

    def test_radii_up_to_3000_m_share_a_query_box(self):
        def sqls(radius):
            args = argparse.Namespace(begin="2026-11-05T09:00Z", end="2026-11-05T10:00Z", radius=radius, geoid=45)
            client = FakeTrino([])
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(compare, "OUT_DIR", tmp), \
                    mock.patch("opensky.webtrak.radar_passes", return_value=[]), \
                    mock.patch("opensky.webtrak.events", return_value=[]), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                compare.run(args, client, DB)
            return [sql for sql, _ in client.calls]

        self.assertEqual(sqls(1500), sqls(3000))
        self.assertNotEqual(sqls(3000), sqls(4000))  # A larger radius widens the box


class TestLogs(unittest.TestCase):
    def test_records_are_in_the_loggers_fields_and_units(self):
        states = flyover(T0 + 120, span_s=2)
        states.append(dict(states[-1], time=states[-1]["time"] + 1))  # A repeat of the last position
        recs = logs.records(states)
        self.assertEqual(len(recs), 5)
        r = recs[0]
        self.assertEqual((r["hex"], r["flight"], r["seen_pos"]), ("abc123", "TEST1", 0.0))
        self.assertEqual((r["alt_baro"], r["alt_geom"]), (1969, 2297))  # 600 m and 700 m in feet
        self.assertEqual([r["now"] for r in recs], sorted(r["now"] for r in recs))

    def test_missing_heights_and_callsigns_are_left_out(self):
        r = logs.records([state(T0, 0, baroaltitude=float("nan"), geoaltitude=None, callsign=None)])[0]
        self.assertNotIn("alt_baro", r)
        self.assertNotIn("alt_geom", r)
        self.assertNotIn("flight", r)

    def test_run_writes_hourly_files_and_source(self):
        client = FakeTrino(flyover(T0 + 3600 - 30, span_s=60))  # Crosses an hour boundary
        with tempfile.TemporaryDirectory() as out:
            args = argparse.Namespace(begin="2026-11-05T09:00Z", end="2026-11-05T11:00Z", out=out)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                logs.run(args, client, DB)
            self.assertEqual(sorted(os.listdir(out)),
                             ["2026-11-05T09.jsonl.gz", "2026-11-05T10.jsonl.gz", "SOURCE.txt"])
            with gzip.open(os.path.join(out, "2026-11-05T10.jsonl.gz"), "rt") as f:
                rows = [json.loads(line) for line in f]
            self.assertTrue(all(T0 + 3600 <= r["now"] < T0 + 7200 for r in rows))
            with open(os.path.join(out, "SOURCE.txt")) as f:
                self.assertIn("NOT the logger's own record", f.read())
            with self.assertRaises(SystemExit):  # Won't write over existing files
                with contextlib.redirect_stderr(io.StringIO()):
                    logs.run(args, client, DB)


class TestAircraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def test_flags_become_readsbs_db_flags(self):
        self.assertEqual([aircraft.db_flags(f) for f in ("00", "10", "01", "0011", "")], [0, 1, 2, 12, 0])

    def test_load_reads_tar1090_db(self):
        path = os.path.join(self.dir, "aircraft-2026-11-06.csv.gz")
        write_db(path, ["3009B7;I-JENI;E190;00;EMBRAER ERJ-190-100;;;", "AE1234;;K35R;10;BOEING KC-135R;;;",
                        "000001;;;10;;;Miscode - VARIOUS;", "4CA123;EI-ABC"])
        db = aircraft.load(path)
        self.assertEqual(db["3009b7"], aircraft.Aircraft("I-JENI", "E190", 0, "EMBRAER ERJ-190-100"))
        self.assertEqual(db["ae1234"].db_flags, 1)
        self.assertEqual(db["4ca123"].type, "")  # Short lines are padded

    def test_database_uses_the_newest_saved_copy(self):
        write_db(os.path.join(self.dir, "aircraft-2026-10-01.csv.gz"), ["ABC123;OLD;A320;00;;;;"])
        write_db(os.path.join(self.dir, "aircraft-2026-11-01.csv.gz"), ["ABC123;NEW;A20N;00;;;;"])
        with mock.patch.object(aircraft, "DB_DIR", self.dir), mock.patch.object(aircraft, "download") as fetch:
            path, db = aircraft.database(log=io.StringIO())
        fetch.assert_not_called()
        self.assertTrue(path.endswith("aircraft-2026-11-01.csv.gz"))
        self.assertEqual(db["abc123"].registration, "NEW")

    def test_database_downloads_a_copy_when_none_is_saved(self):
        saved = os.path.join(self.dir, "aircraft-2026-11-06.csv.gz")
        write_db(saved, ["ABC123;G-TEST;E190;00;;;;"])
        with mock.patch.object(aircraft, "DB_DIR", os.path.join(self.dir, "empty")), \
                mock.patch.object(aircraft, "download", return_value=saved) as fetch:
            _, db = aircraft.database(log=io.StringIO())
        fetch.assert_called_once()
        self.assertEqual(db["abc123"].type, "E190")

    def test_a_broken_download_is_not_kept(self):
        source = os.path.join(self.dir, "source.csv.gz")
        write_db(source, ["ABC123;G-TEST;E190;00;;;;"])
        out = os.path.join(self.dir, "db")
        with self.assertRaises(SystemExit):
            aircraft.download(out, "file://" + source, log=io.StringIO())
        self.assertEqual(os.listdir(out), [])

    def test_unknown_types_are_reported_by_name(self):
        log = io.StringIO()
        db = {**DB, "def456": aircraft.Aircraft("N1", "", 0, "")}
        count = aircraft.report_unknown(db, [("abc123", "A"), ("def456", "B"), ("fff000", "")], log)
        self.assertEqual(count, 2)
        self.assertIn("def456 (B)", log.getvalue())
        self.assertIn("fff000 (no callsign)", log.getvalue())

    def test_passes_get_their_type_and_registration(self):
        found = passes.passes_near(flyover(T0 + 600), T0, T0 + 3600, 3000, 45)
        compare.add_types(found, DB)
        self.assertEqual((found[0].type, found[0].registration), ("E190", "G-TEST"))
        self.assertEqual(found[0].row()["type"], "E190")

    def test_log_records_carry_the_type(self):
        r = logs.records(flyover(T0 + 60, span_s=1), DB)[0]
        self.assertEqual((r["t"], r["r"], r["desc"]), ("E190", "G-TEST", "EMBRAER ERJ-190-100"))
        self.assertNotIn("dbFlags", r)  # 0 is left out, as readsb does
        self.assertNotIn("t", logs.records(flyover(T0 + 60, span_s=1, icao24="ffffff"), DB)[0])


if __name__ == "__main__":
    unittest.main()

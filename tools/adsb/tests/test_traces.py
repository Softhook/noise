"""Tests for adsb.traces, using made-up readsb track files.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import collections
import gzip
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest

from adsb import traces as tr
from adsb.logs import log_paths, read_log_records

SITE_LAT, SITE_LON = 51.5, 0.1
BASE = 1_793_000_000  # 2026-10-26T... UTC


def trace(code, points, **extra):
    return {"icao": code, "timestamp": BASE, "r": "G-LCYN", "t": "E190", "dbFlags": 0, "trace": points, **extra}


NEAR = trace("4007f1", [
    # seconds, lat, lon, alt, gs, track, flags, rate, details, type, alt_geom
    [0.0, 51.505, 0.1, 1300, 140.0, 273.0, 0, -700,
     {"flight": "CFE12A  ", "squawk": "4321", "nic": 8, "rc": 186, "nav_qnh": 1012.8}, "adsb_icao", 1450],
    [4.5, 51.505, 0.095, 1250, 139.0, 273.0, 0, -704, None, "adsb_icao", 1400],
    [9.0, 51.505, 0.09, 1200, None, None, 8, None, None, "adsb_icao", None],  # geometric only
    [3700.0, 51.5, 0.1, "ground", 10.0, 90.0, 2, None, None, "adsb_icao", None],  # next hour, new leg
    ["bad", 51.5, 0.1, 1000],
])
FAR = trace("abcdef", [[0.0, 52.5, 0.1, 30000, 450.0, 0.0, 0, 0, None, "adsb_icao", 30200]])


def gz_json(obj):
    return gzip.compress(json.dumps(obj).encode())


class Points(unittest.TestCase):
    def test_fields_follow_the_logger(self):
        records = list(tr.point_records(NEAR))
        self.assertEqual(len(records), 4)
        first, second, third, fourth = records
        self.assertEqual(first["now"], BASE)
        self.assertEqual((first["hex"], first["t"], first["r"]), ("4007f1", "E190", "G-LCYN"))
        self.assertEqual((first["alt_baro"], first["alt_geom"], first["nic"], first["nav_qnh"]), (1300, 1450, 8, 1012.8))
        self.assertEqual(first["baro_rate"], -700)
        # Flight and squawk carry forward to points without details; quality fields don't
        self.assertEqual((second["flight"], second["squawk"]), ("CFE12A  ", "4321"))
        self.assertNotIn("nic", second)
        self.assertEqual(second["now"], BASE + 4.5)
        # Flag 8: the altitude is geometric
        self.assertNotIn("alt_baro", third)
        self.assertEqual(third["alt_geom"], 1200)
        self.assertNotIn("gs", third)
        self.assertEqual(fourth["alt_baro"], "ground")
        self.assertEqual(fourth["trace_flags"], 2)

    def test_rubbish_is_skipped(self):
        self.assertEqual(list(tr.point_records({"icao": None, "trace": []})), [])
        self.assertEqual(list(tr.point_records({"icao": "abc123", "timestamp": BASE, "trace": [None, [1]]})), [])


class Convert(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def history_folder(self):
        """A day of readsb's --write-globe-history folder, with internal state to be ignored."""
        day = os.path.join(self.dir, "globe_history", "2026", "10", "26")
        for code, data in (("4007f1", NEAR), ("abcdef", FAR)):
            folder = os.path.join(day, "traces", code[-2:])
            os.makedirs(folder)
            with open(os.path.join(folder, f"trace_full_{code}.json"), "wb") as f:
                f.write(gz_json(data))
        os.makedirs(os.path.join(self.dir, "globe_history", "internal_state"))
        with open(os.path.join(self.dir, "globe_history", "internal_state", "trace_full_000000.json"), "wb") as f:
            f.write(b"not a trace")
        os.makedirs(os.path.join(day, "heatmap"))
        with open(os.path.join(day, "heatmap", "00.bin.ttf"), "wb") as f:
            f.write(b"\0" * 10)
        return os.path.join(self.dir, "globe_history")

    def read_back(self, out):
        report = collections.Counter(damaged_files=[])
        return list(read_log_records(log_paths(out), report)), report

    def test_folder_to_hourly_files_that_analyse_reads(self):
        out = os.path.join(self.dir, "out")
        report = tr.convert([self.history_folder()], out, SITE_LAT, SITE_LON, 30, "test folder 2026-10-26")
        self.assertEqual((report["traces"], report["kept"], report["aircraft_kept"], report["hours"]), (2, 4, 1, 2))
        records, read = self.read_back(out)
        self.assertEqual(read["misdated_lines"], 0)
        self.assertEqual([r["now"] for r in records], sorted(r["now"] for r in records))
        self.assertEqual({r["hex"] for r in records}, {"4007f1"})
        with open(os.path.join(out, "SOURCE.txt")) as f:
            note = f.read()
        self.assertIn("Source: test folder 2026-10-26", note)
        self.assertIn("NOT the logger's own record", note)
        self.assertFalse([n for n in os.listdir(out) if n.startswith(".work")])

    def test_split_archive_is_read_in_order_without_unpacking(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, data in (("./traces/f1/trace_full_4007f1.json", gz_json(NEAR)),
                               ("./traces/ef/trace_full_abcdef.json", gz_json(FAR)),
                               ("./heatmap/00.bin.ttf", b"\0" * 10)):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        data = buffer.getvalue()
        half = len(data) // 2
        parts = []
        for suffix, chunk in (("ab", data[half:]), ("aa", data[:half])):  # Given out of order
            parts.append(os.path.join(self.dir, f"v2026.10.26-planes-readsb-prod-0.tar.{suffix}"))
            with open(parts[-1], "wb") as f:
                f.write(chunk)
        out = os.path.join(self.dir, "out")
        report = tr.convert(parts, out, SITE_LAT, SITE_LON, 30, "adsb.lol prod 2026-10-26")
        self.assertEqual(report["damaged"], [])
        self.assertEqual(report["kept"], 4)
        records, _ = self.read_back(out)
        self.assertEqual(len(records), 4)

    def test_damaged_archive_is_reported(self):
        path = os.path.join(self.dir, "broken.tar")
        with open(path, "wb") as f:
            f.write(b"x" * 1000)
        report = tr.convert([path], os.path.join(self.dir, "out"), SITE_LAT, SITE_LON, 30, "test")
        self.assertTrue(report["damaged"])

    def test_refuses_a_folder_with_logs_in_it(self):
        out = os.path.join(self.dir, "out")
        os.makedirs(out)
        open(os.path.join(out, "2026-10-26T10.jsonl.gz"), "wb").close()
        with self.assertRaises(SystemExit):
            tr.convert([self.history_folder()], out, SITE_LAT, SITE_LON, 30, "test")


if __name__ == "__main__":
    unittest.main()

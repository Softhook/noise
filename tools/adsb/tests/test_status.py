"""Tests for adsb.status, using made-up health logs.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from adsb import status as st

NOW = 1_793_000_000.0


def record(t, **values):
    base = {
        "time": t, "event": None, "lines": 1000, "written": 400, "far": 600, "invalid": 0,
        "dropped_disk_full": 0, "dropped_write_error": 0,
        "clock": {"synchronised": True, "reference": "GPS", "offset_s": 0.0004},
        "disk_free_gb": 200.0, "cpu_temp_c": 50.0, "throttled": "throttled=0x0", "uptime_s": 7200,
    }
    base.update(values)
    return base


class Status(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        os.makedirs(os.path.join(self.dir, "health"))
        os.makedirs(os.path.join(self.dir, "adsb"))

    def write(self, *records):
        with open(os.path.join(self.dir, "health", "day.jsonl"), "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            f.write("not json\n")

    def test_healthy(self):
        self.write(record(NOW - 600), record(NOW - 300))
        open(os.path.join(self.dir, "adsb", "2026-11-05T12.jsonl.gz"), "wb").close()
        lines, warnings = st.check(self.dir, 24, now=NOW)
        self.assertEqual(warnings, [])
        text = "\n".join(lines)
        self.assertIn("Clock: synchronised to GPS, offset 0.4 ms", text)
        self.assertIn("2,000 lines received, 800 kept", text)
        self.assertIn("Data files: 1", text)

    def test_no_records_means_not_running(self):
        lines, warnings = st.check(self.dir, 24, now=NOW)
        self.assertIn("Is the logger running?", warnings[0])

    def test_stale_log_and_unsynchronised_clock(self):
        self.write(record(NOW - 3600, clock={"synchronised": False}))
        _, warnings = st.check(self.dir, 24, now=NOW)
        text = " ".join(warnings)
        self.assertIn("60 minutes old", text)
        self.assertIn("isn't known to be synchronised", text)

    def test_wrong_site_location_is_caught(self):
        self.write(record(NOW - 300, written=0, far=1000))
        _, warnings = st.check(self.dir, 24, now=NOW)
        self.assertTrue(any("site latitude and longitude" in w for w in warnings))

    def test_problems_are_reported(self):
        self.write(
            record(NOW - 600, event="write_error"),
            record(NOW - 300, disk_free_gb=3.0, cpu_temp_c=82.0, throttled="throttled=0x50005",
                   dropped_write_error=12, lines=0, written=0, far=0),
        )
        _, warnings = st.check(self.dir, 24, now=NOW)
        text = " ".join(warnings)
        for expected in ("3.0 GB free", "hot", "power or heat", "12 lines dropped because of write errors",
                         "Disk write errors: 1"):
            self.assertIn(expected, text)

    def test_old_records_are_ignored(self):
        self.write(record(NOW - 3 * 86400, event="write_error"), record(NOW - 300))
        _, warnings = st.check(self.dir, 24, now=NOW)
        self.assertEqual(warnings, [])

    def test_command_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(st.main(["--log-dir", self.dir]), 1)


if __name__ == "__main__":
    unittest.main()

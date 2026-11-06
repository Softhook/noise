"""Tests for adsb.status, using made-up health logs.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest

from adsb import status as st

NOW = 1_793_000_000.0


def receiver(messages=60000, strong=1800, **values):
    return {"gain_db": 43.9, "messages": messages, "strong_signals": strong, "strong_share": strong / messages,
            "signal_dbfs": -14.8, "noise_dbfs": -33.5, "peak_signal_dbfs": -1.2, "samples_dropped": 0,
            "age_s": 20.0, **values}


def record(t, **values):
    base = {
        "time": t, "event": None, "lines": 1000, "written": 400, "far": 600, "invalid": 0,
        "dropped_disk_full": 0, "dropped_write_error": 0,
        "clock": {"synchronised": True, "reference": "GPS", "offset_s": 0.0004},
        "disk_free_gb": 200.0, "cpu_temp_c": 50.0, "throttled": "throttled=0x0", "uptime_s": 7200,
        "receiver": receiver(),
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
        self.assertIn("Receiver: gain 43.9 dB, signal -14.8 dBFS, noise -33.5 dBFS, peak -1.2 dBFS, "
                      "strong signals 3.0%", text)
        self.assertIn("Strong signals, last 24 hours: 3.0% of 120,000 messages", text)

    def test_gain_too_high_and_cpu_overloaded(self):
        # The share is over the whole period, not just the last record
        self.write(record(NOW - 600, receiver=receiver(strong=15000, samples_dropped=40)),
                   record(NOW - 300, receiver=receiver(strong=1000)))
        _, warnings = st.check(self.dir, 24, now=NOW)
        text = " ".join(warnings)
        self.assertIn("13% of messages are very strong", text)
        self.assertIn("dropped 40 sample blocks", text)

    def test_missing_receiver_statistics(self):
        self.write(record(NOW - 300, receiver=None))
        lines, warnings = st.check(self.dir, 24, now=NOW)
        self.assertEqual(warnings, [])
        self.assertIn("Receiver: no statistics from readsb", "\n".join(lines))
        old = record(NOW - 300)
        del old["receiver"]  # A health log from before receiver statistics were recorded
        self.write(old)
        lines, warnings = st.check(self.dir, 24, now=NOW)
        self.assertEqual(warnings, [])
        self.assertNotIn("Receiver", "\n".join(lines))

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

    def day_of_records(self, day_start, passes, interval=300):
        """Health records every 5 minutes for a whole UTC day, with `passes` evenly spaced passes."""
        count = 86400 // interval
        at = {k * count // passes: f"p{k:05d}" for k in range(passes)}
        return [record(day_start + i * interval, near={at[i]: 0.8} if i in at else {},
                       near_limits={"km": 2.0, "max_ft": 3000.0}) for i in range(count)]

    def test_close_passes_by_day(self):
        day = 1_792_972_800  # 2026-10-26 00:00 UTC, a Monday
        now = day + 3 * 86400 + 3600
        records = self.day_of_records(day, 60) + self.day_of_records(day + 86400, 55) \
            + self.day_of_records(day + 2 * 86400, 50)
        # One aircraft seen in three records in a row is one pass; back an hour later it's another
        records.append(record(now - 3000, near={"zz0001": 1.2}, near_limits={"km": 2.0, "max_ft": 3000.0}))
        records.append(record(now - 2700, near={"zz0001": 0.4}))
        records.append(record(now - 2400, near={"zz0001": 1.5}))
        records.append(record(now - 300, near={"zz0001": 0.9}))
        self.write(*records)
        lines, warnings = st.check(self.dir, 24, now=now)
        text = "\n".join(lines)
        self.assertIn("Close passes (within 2 km and below 3,000 ft), by UTC day:", text)
        self.assertIn("2026-10-26 Mon: 60\n", text)
        self.assertIn("2026-10-28 Wed: 50\n", text)
        self.assertIn("2026-10-29 Thu: 2 (part of the day)", text)
        self.assertIn("Last close pass: 2026-10-29 00:55:00 UTC (0.1 hours ago)", text)
        self.assertFalse(any("close passes" in w for w in warnings))

    def test_a_day_with_almost_no_passes_is_a_warning(self):
        day = 1_792_972_800
        records = self.day_of_records(day, 60) + self.day_of_records(day + 86400, 4) \
            + self.day_of_records(day + 2 * 86400, 50)
        self.write(*records)
        _, warnings = st.check(self.dir, 24, now=day + 3 * 86400 - 60)
        self.assertTrue(any("Only 4 close passes on 2026-10-27" in w for w in warnings), warnings)

    def test_no_pass_section_for_an_older_logger(self):
        self.write(record(NOW - 300))
        lines, _ = st.check(self.dir, 24, now=NOW)
        self.assertNotIn("Close passes", "\n".join(lines))

    def test_command_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(st.main(["--log-dir", self.dir]), 1)

    def test_html_page(self):
        self.write(record(time.time() - 300, cpu_temp_c=82.0))  # main uses the real time
        page = os.path.join(self.dir, "index.html")
        self.assertEqual(st.main(["--log-dir", self.dir, "--html", page]), 0)
        with open(page) as f:
            text = f.read()
        self.assertIn("The Pi is hot", text)
        self.assertIn("Clock: synchronised to GPS", text)
        self.assertFalse(os.path.exists(page + ".tmp"))
        lines, _ = st.check(self.dir, 24, now=NOW)
        self.assertIn("&lt;b&gt;", st.html_page(lines, ["<b>"], NOW))
        self.assertIn("No problems found.", st.html_page(lines, [], NOW))

    def test_receiver_down_or_silent_is_a_warning_at_once(self):
        # Hours of good data earlier in the day mustn't hide a receiver that stopped since
        good = [record(NOW - 86400 + i * 300, connected=True, newest_message_age_s=0.5) for i in range(200)]
        for last, expected in (
            (record(NOW - 300, connected=False, lines=0), "isn't connected to readsb"),
            (record(NOW - 300, connected=True, lines=0, newest_message_age_s=3600.0), "Nothing from readsb for 60 minutes"),
        ):
            with self.subTest(expected):
                self.write(*good, last)
                _, warnings = st.check(self.dir, 24, now=NOW)
                self.assertTrue(any(expected in w for w in warnings), warnings)
        self.write(*good, record(NOW - 300, connected=True, newest_message_age_s=2.0))
        self.assertEqual(st.check(self.dir, 24, now=NOW)[1], [])

    def test_on_the_pi_the_newest_record_is_found_by_this_boots_uptime(self):
        # After a power cut the clock starts behind, so this boot's records are older by time
        # than the last ones before the cut, which said the clock was fine.
        before = [record(NOW - 3600 + i * 300, boot_id="old", uptime_s=90_000 + i * 300) for i in range(12)]
        after = record(NOW - 2400, boot_id="new", uptime_s=900, clock={"synchronised": False})
        self.write(*before, after)
        live = {"boot_id": "new", "uptime_s": 1000.0, "clock": {"synchronised": False}, "services": {}}
        lines, warnings = st.check(self.dir, 24, now=NOW - 2300, live=live)
        text = "\n".join(lines)
        self.assertIn("Clock (now): NOT synchronised", text)
        self.assertIn("(2 minutes ago)", text)  # By uptime: 1000 - 900 s
        self.assertTrue(any("isn't known to be synchronised" in w for w in warnings))
        # And a logger that hasn't written since the boot is noticed, however the clock looks
        live = dict(live, boot_id="newer", clock={"synchronised": True})
        _, warnings = st.check(self.dir, 24, now=NOW, live=live)
        self.assertTrue(any("hasn't written a health record since the Pi started" in w for w in warnings))

    def test_services_that_are_not_running_are_warnings(self):
        self.write(record(NOW - 300))
        live = {"boot_id": None, "uptime_s": None, "clock": {"synchronised": True, "reference": "GPS"},
                "services": {"readsb": "failed", "adsb-logger": "active"}}
        _, warnings = st.check(self.dir, 24, now=NOW, live=live)
        self.assertEqual([w for w in warnings if "running" in w],
                         ["readsb is failed, not running. See: journalctl -u readsb -n 30"])

    def test_booting_from_an_sd_card_by_mistake_is_a_warning(self):
        self.write(record(NOW - 300))
        live = {"boot_id": None, "uptime_s": None, "clock": {"synchronised": True}, "services": {},
                "log_disk": "/dev/mmcblk0p2"}
        _, warnings = st.check(self.dir, 24, now=NOW, live=live)
        self.assertTrue(any("booted from an SD card (/dev/mmcblk0p2)" in w for w in warnings), warnings)
        live["log_disk"] = "/dev/sda2"
        self.assertEqual(st.check(self.dir, 24, now=NOW, live=live)[1], [])

    def test_html_page_checks_the_pis_clock_against_the_viewers(self):
        page = st.html_page(["x"], [], 1_793_000_000.5)
        self.assertIn("var made = 1793000000500,", page)
        self.assertIn("Pi's clock is wrong", page)


if __name__ == "__main__":
    unittest.main()

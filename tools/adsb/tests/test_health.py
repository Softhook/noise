"""Tests for adsb.health, using made-up health logs.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import json
import os
import shutil
import tempfile
import unittest

from adsb.common import overlaps
from adsb.health import read_health_log, unsynced_periods

CUT = 1_793_800_000.0  # A power cut, in true time


def rec(t, synced, boot, uptime, event=None):
    return {"time": t, "event": event, "clock": {"synchronised": synced}, "boot_id": boot, "uptime_s": uptime}


class PowerCut(unittest.TestCase):
    def test_data_stamped_after_a_power_cut_is_flagged_though_its_times_overlap_earlier_records(self):
        # Synchronised records every 5 minutes for the hour before the cut
        before = [rec(CUT - 3600 + i * 300, True, "boot-1", 50_000 + i * 300) for i in range(13)]
        # The Pi comes back hours later, but its clock starts from its last save, 45 minutes before
        # the cut, and isn't synchronised for 10 minutes; then it jumps to the right time.
        boot = CUT - 45 * 60 + 10  # Out of step with the earlier records, as it would be
        after = [rec(boot, False, "boot-2", 20, "start"), rec(boot + 300, False, "boot-2", 320),
                 rec(boot + 600, False, "boot-2", 620),
                 rec(CUT + 3 * 3600, True, "boot-2", 640, "clock_synchronised")]
        entries = sorted(before + after, key=lambda e: e["time"])
        periods = unsynced_periods(entries)
        # Everything stamped from the boot until the jump, in the boot's own (wrong) time
        bad = [boot + s for s in range(0, 620)]
        self.assertTrue(all(overlaps(periods, t, t) for t in bad))
        self.assertEqual(periods, [(boot, boot + 620)])

    def test_still_unsynchronised_at_the_end_runs_on_past_the_last_record(self):
        entries = [rec(1000, False, "b", 10), rec(1300, False, "b", 310)]
        self.assertEqual(unsynced_periods(entries), [(1000, 1000 + 300 + 900)])

    def test_records_from_an_older_logger_are_taken_in_time_order(self):
        entries = [{"time": 10, "clock": {"synchronised": False}}, {"time": 20, "clock": {"synchronised": True}},
                   {"time": 30, "clock": {"synchronised": False}}]
        self.assertEqual(unsynced_periods(entries), [(10, 20), (30, 30)])


class Reading(unittest.TestCase):
    def test_days_well_before_the_period_are_not_read(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        os.makedirs(os.path.join(folder, "health"))
        # The October file holds a record inside the period, so reading it would show
        for name, t in (("2026-10-01.jsonl", 1_793_836_801), ("2026-11-05.jsonl", 1_793_836_800)):
            with open(os.path.join(folder, "health", name), "w") as f:
                f.write(json.dumps({"time": t}) + "\n")
        with open(os.path.join(folder, "health", "2026-11-04.jsonl"), "wb") as f:
            f.write(b'{"time": 1793750400}\n\xff\xfe broken\n')  # Not UTF-8, as after a bad power cut
        times = [e["time"] for e in read_health_log(folder, since=1_793_836_800 - 86400)]
        self.assertEqual(times, [1_793_750_400, 1_793_836_800])


if __name__ == "__main__":
    unittest.main()

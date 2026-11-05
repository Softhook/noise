"""Tests for the WebTrak collector, using made-up chunks. Nothing here touches the network."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import tempfile
import unittest
import urllib.error

from webtrak import client, parse, store

MONITOR = {"id": "106", "name": "St Pauls Church, Thamesmead", "lat": 51.50535, "lon": 0.11075}

# 2026-11-05 08:02:30 GMT is handle 59795525. In winter local time is UTC.
WINTER = 59795525


def chunk_text(handle, local_start, lines, status="online"):
    end = local_start[:-2] + str(int(local_start[-2:]) + 29).zfill(2)
    header = (f'<data endTime="{end}" generated="2026-11-05 22:18:23" handle="{handle}" '
              f'radarStatus="{status}" startTime="{local_start}" type="data">')
    return header + "\n".join(lines) + "\n</data>\n"


def radar(local, track, lat, lon, height, callsign="KL978", direction="D"):
    return (f"radar,{local},{track},{direction},LCY,E190,{callsign},J,{lon},{lat},{height},80,PHEZA,1234,"
            f"LCY,AMS,,ScheduledFlight,{height + 6},4691134,tr_")


SAMPLE = chunk_text(WINTER, "2026-11-05 08:02:30", [
    radar("20261105080246", "10363488", 51.5040, 0.1080, 698),
    radar("20261105080250", "10363488", 51.5052, 0.1098, 723),
    radar("20261105080250", "999", 51.60, 0.30, 3000, callsign="FAR1", direction="O"),
    "noise,20261105080250,106,106,1,70.4",
    "noise,20261105080251,106,106,1,70.7",
    "noise,20261105080251,101,101,5,50.0",
    "noise,20261105080252,106,106,1,bad",
    "event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301",
    "event,20261105080230,101,101,1,78.42,20261105080237,87.04,75.00,89.13,16,20261105080246",
    "nonsense line",
])


class ParseTests(unittest.TestCase):
    def test_handles_are_utc_over_30(self):
        self.assertEqual(parse.utc_for_handle(WINTER), 1793865750)
        self.assertEqual(parse.handle_for_utc(1793865750 + 29), WINTER)

    def test_parses_levels_events_and_radar(self):
        chunk = parse.parse_chunk(SAMPLE)
        self.assertEqual(chunk.handle, WINTER)
        self.assertEqual(chunk.offset_s, 0)
        self.assertEqual([(lv.monitor, lv.level) for lv in chunk.levels], [("106", 70.4), ("106", 70.7), ("101", 50.0)])
        event = chunk.events[0]
        self.assertEqual(event.monitor, "106")
        self.assertEqual(event.lmax_time - event.start, 23)
        self.assertAlmostEqual(event.sel, event.leq + 10 * math.log10(event.duration), places=1)
        self.assertEqual(len(chunk.positions), 3)
        self.assertEqual(chunk.positions[0].height_m, 698)
        self.assertEqual(chunk.positions[0].altitude_m, 704)

    def test_summer_times_use_the_handles_offset(self):
        # 2026-07-01 12:00:00 BST is 11:00 UTC, handle 59430120.
        text = chunk_text(59430120, "2026-07-01 12:00:00", ["noise,20260701120005,106,106,5,55.0"])
        chunk = parse.parse_chunk(text)
        self.assertEqual(chunk.offset_s, 3600)
        self.assertEqual(chunk.levels[0].utc, parse.utc_for_handle(59430120) + 5)

    def test_error_and_empty_replies_are_not_available(self):
        with self.assertRaises(parse.NotAvailable):
            parse.parse_chunk('<error faultCode="3" faultDescription="Invalid request" handle="1" />')
        with self.assertRaises(parse.NotAvailable):
            parse.parse_chunk('<data endTime="1970-01-01 01:03:59" handle="07" radarStatus="offline" '
                              'startTime="1970-01-01 01:03:30" type="data"></data>', 7)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self, *parts):
        with open(os.path.join(self.dir, "nmt106", *parts), newline="") as f:
            return list(csv.DictReader(f))

    def test_saves_only_this_monitor_and_matches_the_event(self):
        s = store.MonitorStore(self.dir, MONITOR, radius_m=3000)
        summary = s.save(parse.parse_chunk(SAMPLE), SAMPLE)
        levels = self.read("levels", "2026-11-05.csv")
        self.assertEqual([r["level_db"] for r in levels], ["70.4", "70.7"])
        self.assertEqual(levels[0]["time_utc"], "2026-11-05T08:02:50Z")
        self.assertEqual(levels[0]["time_local"], "2026-11-05T08:02:50+00:00")
        aircraft = self.read("aircraft", "2026-11-05.csv")
        self.assertEqual({r["callsign"] for r in aircraft}, {"KL978"})  # FAR1 is outside the radius
        events = self.read("events.csv")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["callsign"], "KL978")
        self.assertEqual(events[0]["closest_height_m"], "723")
        self.assertEqual(events[0]["lmax_after_closest_s"], "3")
        self.assertEqual(summary["max"], 70.7)

    def test_repeats_are_skipped_and_restarts_carry_on(self):
        s = store.MonitorStore(self.dir, MONITOR)
        chunk = parse.parse_chunk(SAMPLE)
        self.assertIsNotNone(s.save(chunk))
        self.assertIsNone(s.save(parse.parse_chunk(SAMPLE)))
        # The same event repeated in the next chunk isn't written twice, even after a restart.
        s2 = store.MonitorStore(self.dir, MONITOR)
        self.assertEqual(s2.last_handle, WINTER)
        nxt = chunk_text(WINTER + 1, "2026-11-05 08:03:00", [
            "noise,20261105080300,106,106,1,65.2",
            "event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301"])
        summary = s2.save(parse.parse_chunk(nxt))
        self.assertEqual(summary["events"], [])
        self.assertEqual(len(self.read("events.csv")), 1)
        self.assertEqual(len(self.read("levels", "2026-11-05.csv")), 3)

    def test_restart_reloads_radar_for_matching(self):
        s = store.MonitorStore(self.dir, MONITOR)
        first = chunk_text(WINTER, "2026-11-05 08:02:30", [radar("20261105080250", "10363488", 51.5052, 0.1098, 723)])
        s.save(parse.parse_chunk(first))
        s2 = store.MonitorStore(self.dir, MONITOR)
        s2.prime_buffer()
        nxt = chunk_text(WINTER + 1, "2026-11-05 08:03:00", [
            "event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301"])
        summary = s2.save(parse.parse_chunk(nxt))
        self.assertEqual(summary["events"][0]["callsign"], "KL978")

    def test_gaps(self):
        s = store.MonitorStore(self.dir, MONITOR)
        for h in (10, 11, 12, 15):
            s._mark_saved(h)
        self.assertEqual(s.state["saved"], [[10, 12], [15, 15]])
        self.assertEqual(s.gaps(8, 17), [(8, 9), (13, 14), (16, 17)])
        self.assertEqual(s.gaps(10, 12), [])

    def test_event_with_no_aircraft(self):
        s = store.MonitorStore(self.dir, MONITOR)
        text = chunk_text(WINTER, "2026-11-05 08:02:30", [
            "event,20261105080230,106,106,5,66.0,20261105080233,72.0,64.0,75.0,6,20261105080236"])
        summary = s.save(parse.parse_chunk(text))
        self.assertEqual(summary["events"][0]["candidates"], 0)
        self.assertEqual(self.read("events.csv")[0]["callsign"], "")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(unittest.TestCase):
    def make(self, replies):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return FakeResponse(reply.encode())

        sleeps = []
        c = client.Client(opener=opener, sleep=sleeps.append, clock=lambda: 0.0)
        return c, calls, sleeps

    def test_latest_handle_and_host_lookup(self):
        sites = json.dumps([{"site_name": "lcy", "server_name": "example.test"}])
        c, calls, _ = self.make([sites, '<data startHandle="59797175" window="30" />'])
        self.assertEqual(c.latest_handle(), 59797175)
        self.assertEqual(calls[1], "https://example.test/WebTrak/lcy/data/handle/now")

    def test_retries_then_succeeds_and_spaces_requests(self):
        sites = json.dumps([{"site_name": "lcy", "server_name": "example.test"}])
        c, calls, sleeps = self.make([sites, urllib.error.URLError("down"), '<data startHandle="5" />'])
        self.assertEqual(c.latest_handle(), 5)
        self.assertIn(5, sleeps)  # the back-off
        self.assertTrue(all(s > 0 for s in sleeps))

    def test_monitors(self):
        config = json.dumps({"nmt_locations": [{"locid": 106, "name": "St Pauls Church, Thamesmead",
                                                "latitude": 51.50535, "longitude": 0.11075, "status": "active"}]})
        c, calls, _ = self.make([config])
        self.assertEqual(c.monitors()[0]["id"], "106")
        self.assertEqual(calls[0], client.CONFIG_URL)


if __name__ == "__main__":
    unittest.main()

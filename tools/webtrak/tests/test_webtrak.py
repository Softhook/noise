"""Tests for the WebTrak collector, using made-up chunks. Nothing here touches the network."""

from __future__ import annotations

import contextlib
import csv
import gzip
import http.client
import io
import json
import math
import os
import shutil
import tempfile
import unittest
import urllib.error

from webtrak import __main__ as cli
from webtrak import client, parse, server, stats, store

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


def later(handle, local_start, lines=()):
    """A chunk with a noise line, so it isn't empty."""
    return chunk_text(handle, local_start, [f"noise,{local_start.replace('-', '').replace(' ', '').replace(':', '')}"
                                            f",106,106,5,50.0", *lines])


# The chunks after SAMPLE. Its event's matching window ends at 08:03:53 (LAmax + 60 s), in the second.
FOLLOWING = [later(WINTER + 1, "2026-11-05 08:03:00"), later(WINTER + 2, "2026-11-05 08:03:30"),
             later(WINTER + 3, "2026-11-05 08:04:00")]
# The window starts at 08:01:53, so the two chunks before SAMPLE are needed too.
BEFORE = [later(WINTER - 2, "2026-11-05 08:01:30"), later(WINTER - 1, "2026-11-05 08:02:00")]


def until(handle):
    """finish() arguments for every event with its LAmax before the end of this chunk."""
    return 0, parse.utc_for_handle(handle + 1)


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
        # Before WebTrak's data range: a real date, but nothing in it.
        with self.assertRaises(parse.NotAvailable):
            parse.parse_chunk('<data endTime="2024-11-05 22:05:59" handle="57694811" radarStatus="offline" '
                              'startTime="2024-11-05 22:05:30" type="data"></data>', 57694811)

    def test_broken_replies_are_not_available(self):
        no_start = '<data handle="59795525" radarStatus="online" type="data">noise,x</data>'
        cut_off = SAMPLE.replace("</data>", "")
        for text in (no_start, cut_off, '<data startTime="garbage" handle="1">noise,1</data>'):
            with self.assertRaises(parse.NotAvailable):
                parse.parse_chunk(text)

    def test_placeholder_levels_are_not_valid(self):
        text = chunk_text(WINTER, "2026-11-05 08:02:30", ["noise,20261105080230,106,106,9,20.0",
                                                          "noise,20261105080231,106,106,1,20.0",
                                                          "noise,20261105080232,106,106,9,55.0",
                                                          "noise,20261105080233,106,106,5,55.0"])
        self.assertEqual([lv.valid for lv in parse.parse_chunk(text).levels], [False, False, False, True])

    def test_a_squawk_is_not_a_callsign(self):
        line = "radar,20261105080246,7,O,,C152,,P,0.11,51.50,570,36,,7000,,,,Default,576,1,tr_"
        with_reg = line.replace(",P,0.11,51.50,570,36,,", ",P,0.11,51.50,570,36,GBZHE,")
        chunk = parse.parse_chunk(chunk_text(WINTER, "2026-11-05 08:02:30", [line, with_reg]))
        self.assertEqual([p.callsign for p in chunk.positions], ["", "GBZHE"])
        self.assertEqual(chunk.positions[0].squawk, "7000")

    def test_events_carry_the_chunk_offset(self):
        text = chunk_text(59430120, "2026-07-01 12:00:00", [
            "event,20260701120000,106,106,1,71.0,20260701120010,80.0,67.0,84.0,20,20260701120020"])
        self.assertEqual(parse.parse_chunk(text).events[0].offset_s, 3600)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self, *parts):
        with open(os.path.join(self.dir, "nmt106", *parts), newline="") as f:
            return list(csv.DictReader(f))

    def save_all(self, s, texts):
        out = []
        for text in texts:
            out.append(s.save(parse.parse_chunk(text)))
        return out

    def test_saves_only_this_monitor_and_matches_the_event(self):
        s = store.MonitorStore(self.dir, MONITOR, radius_m=3000)
        self.save_all(s, BEFORE)
        summary = s.save(parse.parse_chunk(SAMPLE))
        levels = self.read("levels", "2026-11-05.csv")
        self.assertEqual([r["level_db"] for r in levels if r["flag"] == "1"], ["70.4", "70.7"])
        self.assertEqual(levels[2]["time_utc"], "2026-11-05T08:02:50Z")
        self.assertEqual(levels[2]["time_local"], "2026-11-05T08:02:50+00:00")
        aircraft = self.read("aircraft", "2026-11-05.csv")
        self.assertEqual({r["callsign"] for r in aircraft}, {"KL978"})  # FAR1 is outside the radius
        self.assertEqual(summary["max"], 70.7)
        # The event waits for the radar of the minute after its LAmax.
        self.assertEqual(summary["events"], [])
        self.assertEqual(s.state["pending"][0]["lmax"], 71.04)
        summaries = self.save_all(s, FOLLOWING)
        self.assertEqual([len(x["events"]) for x in summaries], [0, 1, 0])
        events = self.read("events.csv")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["callsign"], "KL978")
        # Closest between the 08:02:46 and 08:02:50 positions, not at either.
        self.assertEqual(events[0]["closest_height_m"], "717")
        self.assertEqual(events[0]["lmax_after_closest_s"], "4")
        self.assertEqual(s.state["pending"], [])

    def test_placeholder_levels_are_written_blank_and_left_out_of_the_summary(self):
        s = store.MonitorStore(self.dir, MONITOR)
        text = chunk_text(WINTER, "2026-11-05 08:02:30", ["noise,20261105080230,106,106,9,20.0",
                                                          "noise,20261105080231,106,106,5,60.0"])
        summary = s.save(parse.parse_chunk(text))
        self.assertEqual([(r["level_db"], r["flag"]) for r in self.read("levels", "2026-11-05.csv")],
                         [("", "9"), ("60.0", "5")])
        self.assertEqual((summary["seconds"], summary["leq"], summary["max"]), (1, 60.0, 60.0))

    def test_fetch_keeps_events_waiting_for_missing_radar(self):
        s = store.MonitorStore(self.dir, MONITOR)
        s.save(parse.parse_chunk(SAMPLE), give_up=False)  # the chunks before it are missing
        far = later(WINTER + 30, "2026-11-05 08:17:30")
        self.assertEqual(s.save(parse.parse_chunk(far), give_up=False)["events"], [])
        self.assertEqual(len(s.pending), 1)
        # finish() matches only the events in the period asked for.
        self.assertEqual(s.finish(parse.utc_for_handle(WINTER + 1), parse.utc_for_handle(WINTER + 31)), [])
        self.assertEqual(len(s.finish(parse.utc_for_handle(WINTER), parse.utc_for_handle(WINTER + 1))), 1)

    def test_matching_sees_radar_from_the_next_chunk(self):
        # Only a far-off aircraft in the event's own chunk; the one overhead comes in the next chunk.
        s = store.MonitorStore(self.dir, MONITOR)
        self.save_all(s, BEFORE)
        first = chunk_text(WINTER, "2026-11-05 08:02:30", [
            radar("20261105080258", "1", 51.52, 0.13, 900, callsign="FAR2"),
            "noise,20261105080258,106,106,1,70.0",
            "event,20261105080230,106,106,1,71.04,20261105080259,82.38,67.47,84.42,31,20261105080301"])
        nxt = later(WINTER + 1, "2026-11-05 08:03:00", [radar("20261105080302", "2", 51.5054, 0.1108, 400,
                                                                callsign="NEAR1")])
        self.save_all(s, [first, nxt] + FOLLOWING[1:])
        self.assertEqual(self.read("events.csv")[0]["callsign"], "NEAR1")

    def test_repeats_are_skipped_and_restarts_carry_on(self):
        s = store.MonitorStore(self.dir, MONITOR)
        chunk = parse.parse_chunk(SAMPLE)
        self.assertIsNotNone(s.save(chunk))
        self.assertIsNone(s.save(parse.parse_chunk(SAMPLE)))
        # After a restart, the waiting event is still waiting, and a repeat of it isn't added again.
        s2 = store.MonitorStore(self.dir, MONITOR)
        self.assertEqual(s2.last_handle, WINTER)
        self.assertEqual(len(s2.pending), 1)
        nxt = chunk_text(WINTER + 1, "2026-11-05 08:03:00", [
            "noise,20261105080300,106,106,1,65.2",
            "event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301"])
        s2.save(parse.parse_chunk(nxt))
        self.assertEqual(len(s2.pending), 1)
        self.assertEqual(len(self.read("levels", "2026-11-05.csv")), 3)
        self.assertEqual(len(s2.finish(*until(WINTER + 3))), 1)
        self.assertEqual(len(self.read("events.csv")), 1)
        self.assertEqual(store.MonitorStore(self.dir, MONITOR).pending, [])

    def test_restart_reloads_radar_for_matching(self):
        s = store.MonitorStore(self.dir, MONITOR)
        self.save_all(s, BEFORE)
        first = chunk_text(WINTER, "2026-11-05 08:02:30", [radar("20261105080250", "10363488", 51.5052, 0.1098, 723),
                                                             "noise,20261105080250,106,106,1,70.0"])
        s.save(parse.parse_chunk(first))
        s2 = store.MonitorStore(self.dir, MONITOR)
        s2.prime_buffer()
        nxt = later(WINTER + 1, "2026-11-05 08:03:00", [
            "event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301"])
        summaries = self.save_all(s2, [nxt] + FOLLOWING[1:])
        matched = [e for x in summaries for e in x["events"]]
        self.assertEqual([e["callsign"] for e in matched], ["KL978"])

    def test_radar_saved_earlier_is_read_back_for_a_later_fetch(self):
        # The chunk with the aircraft was saved in an earlier run; the event's chunk comes later.
        s = store.MonitorStore(self.dir, MONITOR)
        s.save(parse.parse_chunk(SAMPLE))
        s.finish(*until(WINTER + 10))
        os.remove(os.path.join(self.dir, "nmt106", "events.csv"))
        s2 = store.MonitorStore(self.dir, MONITOR)  # no prime_buffer: as if far from the last chunk
        nxt = later(WINTER + 1, "2026-11-05 08:03:00", [
            "event,20261105080245,106,106,1,70.0,20261105080252,80.0,67.0,84.0,10,20261105080255"])
        s2.save(parse.parse_chunk(nxt))
        self.assertEqual(s2.finish(*until(WINTER + 3))[0]["callsign"], "KL978")

    def test_gives_up_waiting_eventually(self):
        s = store.MonitorStore(self.dir, MONITOR)
        s.save(parse.parse_chunk(SAMPLE))  # the chunks after it never arrive
        far = later(WINTER + 30, "2026-11-05 08:17:30")
        self.assertEqual(len(s.save(parse.parse_chunk(far))["events"]), 1)

    def test_finish_leaves_later_events_waiting(self):
        s = store.MonitorStore(self.dir, MONITOR)
        s.save(parse.parse_chunk(SAMPLE))
        self.assertEqual(s.finish(*until(WINTER - 10)), [])
        self.assertEqual(len(s.pending), 1)

    def test_lock_stops_a_second_writer(self):
        if store.fcntl is None:
            self.skipTest("no fcntl")
        holder = store.MonitorStore(self.dir, MONITOR)
        holder.lock()
        with self.assertRaises(SystemExit):
            store.MonitorStore(self.dir, MONITOR).lock()

    def test_raw_cache_round_trip(self):
        cache = store.RawCache(self.dir)
        self.assertIsNone(cache.get(WINTER))
        cache.put(WINTER, SAMPLE)
        self.assertTrue(cache.path(WINTER).endswith(os.path.join("raw", "2026-11-05", f"{WINTER}.txt.gz")))
        self.assertEqual(cache.get(WINTER), SAMPLE)

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
        s.save(parse.parse_chunk(text))
        self.assertEqual(s.finish(*until(WINTER))[0]["candidates"], 0)
        self.assertEqual(self.read("events.csv")[0]["callsign"], "")


class ClosestApproachTests(unittest.TestCase):
    def position(self, utc, lat, lon, height, track="1"):
        return parse.Position(utc=utc, track=track, direction="A", airport="LCY", aircraft_type="E190",
                              callsign="X", registration="", squawk="", lat=lat, lon=lon, height_m=height,
                              altitude_m=None, speed_ms=None, origin="", destination="")

    def test_closest_point_is_found_between_positions(self):
        # Flying due east at 80 m/s, 300 m up, passing right over the monitor half way between two fixes.
        step = 320 / (111320 * math.cos(math.radians(MONITOR["lat"])))
        points = [self.position(100, MONITOR["lat"], MONITOR["lon"] - step / 2, 300),
                  self.position(104, MONITOR["lat"], MONITOR["lon"] + step / 2, 300)]
        slant, ground, height, when = store.closest_approach(points, MONITOR)
        self.assertAlmostEqual(when, 102, places=1)
        self.assertLess(ground, 2)
        self.assertAlmostEqual(slant, 300, delta=1)

    def test_no_interpolation_across_a_gap_in_the_radar(self):
        step = 4000 / (111320 * math.cos(math.radians(MONITOR["lat"])))
        points = [self.position(100, MONITOR["lat"], MONITOR["lon"] - step / 2, 300),
                  self.position(150, MONITOR["lat"], MONITOR["lon"] + step / 2, 300)]
        self.assertEqual(store.closest_approach(points, MONITOR)[3], 100)

    def test_match_picks_the_nearest_track(self):
        event = parse.Event("106", 90, 100, 110, 70, 80, 68, 85, 20, "1")
        near = self.position(100, MONITOR["lat"], MONITOR["lon"], 500, track="near")
        far = self.position(100, MONITOR["lat"] + 0.01, MONITOR["lon"], 500, track="far")
        row = store.match_event(event, [far, near], MONITOR)
        self.assertEqual((row["track"], row["closest_slant_m"], row["candidates"]), ("near", 500, 2))


class ConsoleTests(unittest.TestCase):
    def test_an_aircraft_without_a_callsign_is_still_shown(self):
        row = {"start_local": "2026-11-05T08:02:30+00:00", "lmax_db": 70.0, "sel_db": 80.0, "duration_s": 10.0,
               "event_class": "1", "callsign": "", "track": "42", "type": "C152", "direction": "O", "airport": "",
               "closest_slant_m": 600, "closest_height_m": 550}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.print_events([row, {**row, "track": None, "candidates": 0}], MONITOR)
        lines = out.getvalue().splitlines()
        self.assertIn("track 42 C152", lines[0])
        self.assertIn("no aircraft in range", lines[1])


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

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
            if isinstance(reply, FakeResponse):
                return reply
            return FakeResponse(reply.encode())

        sleeps = []
        c = client.Client(opener=opener, sleep=sleeps.append, clock=lambda: 0.0)
        c._data_host = "example.test"
        return c, calls, sleeps

    def test_latest_handle_and_host_lookup(self):
        sites = json.dumps([{"site_name": "lcy", "server_name": "example.test"}])
        c, calls, _ = self.make([sites, '<data startHandle="59797175" window="30" />'])
        c._data_host = None
        self.assertEqual(c.latest_handle(), 59797175)
        self.assertEqual(calls[1], "https://example.test/WebTrak/lcy/data/handle/now")

    def test_retries_then_succeeds_and_spaces_requests(self):
        sites = json.dumps([{"site_name": "lcy", "server_name": "example.test"}])
        c, calls, sleeps = self.make([sites, urllib.error.URLError("down"), '<data startHandle="5" />'])
        c._data_host = None
        self.assertEqual(c.latest_handle(), 5)
        self.assertIn(5, sleeps)  # the back-off
        self.assertTrue(all(s > 0 for s in sleeps))

    def test_gzipped_replies_are_decoded(self):
        reply = FakeResponse(gzip.compress(b'<data startHandle="7" />'), {"Content-Encoding": "gzip"})
        c, _, _ = self.make([reply])
        self.assertEqual(c.latest_handle(), 7)

    def test_retry_after_is_honoured(self):
        busy = urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": "120"}, None)
        c, _, sleeps = self.make([busy, '<data startHandle="8" />'])
        self.assertEqual(c.latest_handle(), 8)
        self.assertIn(120, sleeps)

    def test_a_cut_off_reply_is_retried_then_reported_as_oserror(self):
        cut = http.client.IncompleteRead(b"<data", 100)
        c, calls, _ = self.make([cut, '<data startHandle="6" />'])
        self.assertEqual(c.latest_handle(), 6)
        c, calls, _ = self.make([cut] * 4)
        with self.assertRaises(OSError):
            c.latest_handle()
        self.assertEqual(len(calls), 4)

    def test_not_found_is_not_retried(self):
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        c, calls, _ = self.make([missing])
        with self.assertRaises(urllib.error.HTTPError):
            c.latest_handle()
        self.assertEqual(len(calls), 1)

    def test_gap_is_timed_from_the_end_of_a_reply(self):
        now = [0.0]
        sleeps = []

        def opener(request, timeout):
            now[0] += 3.0  # a slow reply
            return FakeResponse(b'<data startHandle="9" />')

        c = client.Client(opener=opener, sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)),
                          clock=lambda: now[0], min_interval=2.0)
        c._data_host = "example.test"
        c.latest_handle()
        c.latest_handle()
        self.assertEqual(sleeps, [2.0])

    def test_monitors(self):
        config = json.dumps({"nmt_locations": [{"locid": 106, "name": "St Pauls Church, Thamesmead",
                                                "latitude": 51.50535, "longitude": 0.11075, "status": "active"}]})
        c, calls, _ = self.make([config])
        self.assertEqual(c.monitors()[0]["id"], "106")
        self.assertEqual(calls[0], client.CONFIG_URL)


class FakeClient:
    """Serves chunk texts by handle; None means a network failure."""

    def __init__(self, texts):
        self.texts = texts
        self.asked = []

    def chunk_text(self, handle):
        self.asked.append(handle)
        text = self.texts.get(handle, '<error faultCode="3" faultDescription="Invalid request" />')
        if text is None:
            raise OSError("down")
        return text


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.texts = {WINTER - 2: BEFORE[0], WINTER - 1: BEFORE[1], WINTER: SAMPLE,
                      WINTER + 1: FOLLOWING[0], WINTER + 2: FOLLOWING[1], WINTER + 3: FOLLOWING[2]}

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_range(self, fake, stores, cache=None, retry=None, first=WINTER - 2, last=WINTER + 3):
        with contextlib.redirect_stdout(io.StringIO()):
            return cli.save_range(fake, cache, stores, first, last, quiet=True, retry=retry)

    def test_several_monitors_share_each_download_and_the_cache(self):
        other = {"id": "101", "name": "Ramada Hotel", "lat": 51.5073, "lon": 0.0391}
        stores = [(MONITOR, store.MonitorStore(self.dir, MONITOR)), (other, store.MonitorStore(self.dir, other))]
        cache = store.RawCache(self.dir)
        fake = FakeClient(self.texts)
        self.assertEqual(self.run_range(fake, stores, cache), (6, 0))
        self.assertEqual(len(fake.asked), 6)
        with open(os.path.join(self.dir, "nmt101", "events.csv"), newline="") as f:
            self.assertEqual(next(csv.DictReader(f))["lmax_db"], "78.42")
        # A new monitor later reads from the cache, without asking WebTrak.
        third = {"id": "103", "name": "Galleons Reach", "lat": 51.50613, "lon": 0.0746}
        fake2 = FakeClient({})
        self.assertEqual(self.run_range(fake2, [(third, store.MonitorStore(self.dir, third))], cache), (6, 0))
        self.assertEqual(fake2.asked, [])

    def test_a_failure_doesnt_stop_the_rest(self):
        self.texts[WINTER] = None
        s = store.MonitorStore(self.dir, MONITOR)
        self.assertEqual(self.run_range(FakeClient(self.texts), [(MONITOR, s)]), (5, 1))
        self.assertEqual(s.gaps(WINTER - 2, WINTER + 3), [(WINTER, WINTER)])

    def test_stops_after_failures_in_a_row(self):
        down = {h: None for h in self.texts}
        fake = FakeClient(down)
        saved, failed = self.run_range(fake, [(MONITOR, store.MonitorStore(self.dir, MONITOR))])
        self.assertEqual((saved, failed), (0, 6))
        self.assertEqual(len(fake.asked), cli.MAX_FAILURES_IN_A_ROW)

    def test_unavailable_chunks_are_not_saved_and_retried_later(self):
        del self.texts[WINTER]
        now = [0.0]
        retry = cli.Retry(clock=lambda: now[0])
        s = store.MonitorStore(self.dir, MONITOR)
        fake = FakeClient(self.texts)
        self.run_range(fake, [(MONITOR, s)], retry=retry)
        self.assertFalse(s.has(WINTER))
        fake.asked.clear()
        self.run_range(fake, [(MONITOR, s)], retry=retry)
        self.assertEqual(fake.asked, [])  # too soon to ask again
        now[0] = 61
        self.texts[WINTER] = SAMPLE
        self.run_range(fake, [(MONITOR, s)], retry=retry)
        self.assertEqual(fake.asked, [WINTER])
        self.assertTrue(s.has(WINTER))

    def test_retry_waits_longer_each_time(self):
        now = [0.0]
        retry = cli.Retry(first=60, most=200, clock=lambda: now[0])
        self.assertTrue(retry.failed(5))
        self.assertFalse(retry.failed(5))
        self.assertFalse(retry.failed(5))
        self.assertEqual(retry.next[5][1], 200)
        retry.forget_before(6)
        self.assertEqual(retry.next, {})


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        s = store.MonitorStore(self.dir, MONITOR)
        for text in BEFORE + [SAMPLE] + FOLLOWING:
            s.save(parse.parse_chunk(text))
        self.mdir = os.path.join(self.dir, "nmt106")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_percentiles_and_energy_mean(self):
        self.assertAlmostEqual(stats.energy_mean([60, 60]), 60)
        self.assertAlmostEqual(stats.energy_mean([60, 70]), 67.4, places=1)
        values = list(range(1, 101))
        self.assertEqual((stats.exceeded(values, 10), stats.exceeded(values, 90)), (90, 10))
        self.assertIsNone(stats.energy_mean([]))

    def test_summary_of_saved_chunks(self):
        start = parse.utc_for_handle(WINTER - 2)
        summary = stats.summary(self.mdir, start, parse.utc_for_handle(WINTER + 4))
        self.assertEqual(summary["coverage"]["chunks"], 6)
        self.assertEqual(summary["coverage"]["saved"], 6)
        self.assertEqual(summary["events"], 1)
        self.assertEqual(summary["event_list"][0]["callsign"], "KL978")
        self.assertEqual(summary["types"][0]["type"], "E190")
        self.assertEqual(summary["lmax"], 70.7)
        self.assertIsNotNone(summary["aircraft_share"])
        json.dumps(summary)  # ready to send as it is

    def test_a_period_with_nothing_saved(self):
        summary = stats.summary(self.mdir, parse.utc_for_handle(WINTER + 100), parse.utc_for_handle(WINTER + 110))
        self.assertEqual((summary["coverage"]["seconds"], summary["laeq"], summary["events"]), (0, None, 0))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        site = os.path.join(self.root, "lcy")
        s = store.MonitorStore(site, MONITOR)
        for text in BEFORE + [SAMPLE]:
            s.save(parse.parse_chunk(text))
        self.app = server.App(self.root, "lcy", client=None)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_status_lists_saved_monitors(self):
        status = self.app.status()
        self.assertEqual([m["id"] for m in status["monitors"]], ["106"])
        self.assertEqual(status["monitors"][0]["chunks"], 3)
        self.assertFalse(status["monitors"][0]["writing"])
        self.assertEqual(status["jobs"], [])

    def test_plan_counts_what_is_missing(self):
        plan = self.app.plan({"nmt": "106", "from": "2026-11-05 08:01", "to": "2026-11-05 08:05", "delay": "2"})
        self.assertEqual((plan["chunks"], plan["to_save"], plan["to_download"]), (8, 5, 5))

    def test_coverage_marks_saved_chunks(self):
        bits = self.app.coverage({"day": "2026-11-05"})["monitors"]["106"]
        self.assertEqual(len(bits), 2880)
        self.assertEqual(bits.count("1"), 3)
        self.assertEqual(bits[WINTER - parse.handle_for_utc(parse.local_to_utc("2026-11-05 00:00"))], "1")
        # A clock-change day has 25 hours.
        self.assertEqual(len(self.app.coverage({"day": "2026-10-25"})["monitors"]["106"]), 3000)

    def test_bad_requests_are_refused(self):
        with self.assertRaises(server.BadRequest):
            self.app.plan({"nmt": "../etc", "from": "2026-11-05 08:00", "to": "2026-11-05 09:00"})
        with self.assertRaises(server.BadRequest):
            self.app.statistics({"nmt": "106", "from": "2026-11-05 09:00", "to": "2026-11-05 08:00"})
        with self.assertRaises(server.BadRequest):
            self.app.start_job({"kind": "rm", "nmt": "106"})

    def test_statistics_bucket_follows_the_zoom(self):
        zoomed = self.app.statistics({"nmt": "106", "from": "2026-11-05 08:00:00", "to": "2026-11-05 08:02:30", "bucket": "5"})
        self.assertEqual(zoomed["bucket_s"], 5)
        self.assertEqual(zoomed["end"] - zoomed["start"], 150)
        self.assertEqual(self.app.statistics({"nmt": "106", "from": "2026-11-05 08:00", "to": "2026-11-05 09:00"})["bucket_s"], 60)
        # Too fine for a long period: made coarser to keep the reply small.
        self.assertEqual(server._bucket("1", 31 * 86400), 600)
        with self.assertRaises(server.BadRequest):
            self.app.statistics({"nmt": "106", "from": "2026-11-05 08:00", "to": "2026-11-05 09:00", "bucket": "7"})

    def test_data_deleted_by_hand_is_no_longer_saved(self):
        mdir = os.path.join(self.root, "lcy", "nmt106")
        for name in os.listdir(os.path.join(mdir, "levels")):
            os.remove(os.path.join(mdir, "levels", name))
        self.assertEqual(self.app.status()["monitors"], [])
        self.assertEqual(self.app.coverage({"day": "2026-11-05"})["monitors"], {})
        plan = self.app.plan({"nmt": "106", "from": "2026-11-05 08:01", "to": "2026-11-05 08:05", "delay": "2"})
        self.assertEqual(plan["to_save"], plan["chunks"])
        # A download starting again sees the gap too, so it fetches the day again.
        self.assertEqual(store.MonitorStore(os.path.join(self.root, "lcy"), MONITOR).state["saved"], [])

    def test_on_disk_keeps_the_days_still_there(self):
        mdir = os.path.join(self.root, "lcy", "nmt106")
        os.makedirs(os.path.join(mdir, "levels"), exist_ok=True)
        day = lambda text: parse.handle_for_utc(parse.local_to_utc(text))
        ranges = [[day("2026-11-04 23:00"), day("2026-11-06 01:00")]]
        for name in os.listdir(os.path.join(mdir, "levels")):
            os.remove(os.path.join(mdir, "levels", name))
        open(os.path.join(mdir, "levels", "2026-11-04.csv"), "w").close()
        open(os.path.join(mdir, "levels", "2026-11-06.csv"), "w").close()
        self.assertEqual(store.on_disk(mdir, ranges),
                         [[ranges[0][0], day("2026-11-05 00:00") - 1], [day("2026-11-06 00:00"), ranges[0][1]]])

    def test_a_busy_monitor_cant_get_a_second_download(self):
        if store.fcntl is None:
            self.skipTest("no fcntl")
        holder = store.MonitorStore(os.path.join(self.root, "lcy"), MONITOR)
        holder.lock()
        self.assertTrue(store.is_locked(holder.dir))
        with self.assertRaises(server.BadRequest):
            self.app.start_job({"kind": "fetch", "nmt": "106", "from": "2026-11-05 08:00", "to": "2026-11-05 09:00"})


if __name__ == "__main__":
    unittest.main()

"""Tests for adsb_logger, using a made-up stream on a local socket. No radio is involved.

Run from the project folder with: python3 -m unittest discover tools/adsb
"""

import glob
import gzip
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

import adsb_logger as al

SITE_LAT, SITE_LON = 51.5, 0.1
NEAR = {"now": 1.5, "hex": "abc123", "lat": 51.51, "lon": 0.1, "alt_baro": 1000}
FAR = {"now": 1.5, "hex": "def456", "lat": 53.0, "lon": 0.1, "alt_baro": 35000}


def line(record):
    return json.dumps(record).encode()


def read_gz(path):
    with gzip.open(path, "rb") as f:
        return f.read()


class Geometry(unittest.TestCase):
    def test_distance_of_a_tenth_of_a_degree_of_latitude(self):
        self.assertAlmostEqual(al.distance_km(51.5, 0.1, 51.6, 0.1), 11.12, places=1)


class ClassifyLine(unittest.TestCase):
    def classify(self, raw):
        return al.classify_line(raw, SITE_LAT, SITE_LON, 30)[0]

    def test_near_and_far(self):
        self.assertEqual(self.classify(line(NEAR)), "position")
        self.assertEqual(self.classify(line(FAR)), "far")

    def test_no_position_and_rubbish(self):
        self.assertEqual(self.classify(line({"hex": "abc123"})), "no_position")
        self.assertEqual(self.classify(b'{"now": 1.5, "hex'), "invalid")
        self.assertEqual(self.classify(b"[1, 2]"), "invalid")

    def test_readsb_now_format_is_valid_json(self):
        self.assertEqual(self.classify(b'{"now" : 1.500,"hex":"abc123","lat":51.51,"lon":0.1}'), "position")


class Writer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.clock = 1_793_000_000.0

    def writer(self):
        return al.HourlyWriter(self.dir, 30, now=lambda: self.clock)

    def test_changes_file_each_hour(self):
        w = self.writer()
        w.write(b"a\n")
        self.clock += 3600
        w.write(b"b\n")
        w.close()
        paths = sorted(glob.glob(os.path.join(self.dir, "*.jsonl.gz")))
        self.assertEqual([read_gz(p) for p in paths], [b"a\n", b"b\n"])

    def test_restart_in_the_same_hour_starts_a_new_file(self):
        for content in (b"a\n", b"b\n"):
            w = self.writer()
            w.write(content)
            w.close()
        paths = sorted(glob.glob(os.path.join(self.dir, "*.jsonl.gz")))
        self.assertEqual(len(paths), 2)
        self.assertEqual({read_gz(p) for p in paths}, {b"a\n", b"b\n"})

    def test_flushed_lines_survive_a_power_cut(self):
        w = self.writer()
        w.write(b"saved\n")
        w.flush()
        w.write(b"lost\n")
        copy = os.path.join(self.dir, "copy.gz")
        shutil.copy(w.path, copy)
        w.close()
        recovered = b""
        with gzip.open(copy, "rb") as f:
            try:
                for item in f:
                    recovered += item
            except EOFError:
                pass
        self.assertEqual(recovered, b"saved\n")


class Chrony(unittest.TestCase):
    def test_synchronised(self):
        text = "47505300,GPS,1,1793000000.1,0.000123,0.000100,0.002,1.1,0.1,0.2,0.1,0.01,16.0,Normal"
        parsed = al.parse_chrony(text)
        self.assertTrue(parsed["synchronised"])
        self.assertEqual(parsed["reference"], "GPS")
        self.assertAlmostEqual(parsed["offset_s"], 0.000123)

    def test_not_synchronised_and_unknown(self):
        unsynced = "0,,0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,1.0,1.0,0.0,Not synchronised"
        self.assertFalse(al.parse_chrony(unsynced)["synchronised"])
        self.assertIsNone(al.parse_chrony("nonsense")["synchronised"])


def fake_status(_, clock):
    return {"clock": clock}


def make_logger(log_dir, port=1, clock=None, **settings):
    config = {
        "site": {"lat": SITE_LAT, "lon": SITE_LON},
        "logger": {"log_dir": log_dir, "host": "127.0.0.1", "port": port, "reconnect_seconds": 0.05, **settings},
    }
    return al.Logger(config, status=fake_status, clock=clock or (lambda: {"synchronised": True}))


def wait_for(condition, timeout=5.0):
    """Wait for a condition instead of a fixed sleep, so slow machines don't fail the tests."""
    finish = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > finish:
            raise AssertionError("timed out waiting")
        time.sleep(0.01)


def health_events(log_dir):
    events = []
    for path in glob.glob(os.path.join(log_dir, "health", "*.jsonl")):
        with open(path) as f:
            events.extend(json.loads(item) for item in f)
    return events


class Stream(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_saves_lines_exactly_filters_far_and_reconnects(self):
        server = socket.socket()
        self.addCleanup(server.close)
        server.bind(("127.0.0.1", 0))
        server.listen()
        logger = make_logger(self.dir, port=server.getsockname()[1])
        readsb_line = b'{"now" : 1.500,"hex":"abc123","lat":51.51,"lon":0.1}'

        def serve():
            first, _ = server.accept()
            # A line split across two sends, a far aircraft, and a partial line at disconnection.
            first.sendall(readsb_line[:10])
            time.sleep(0.05)
            first.sendall(readsb_line[10:] + b"\n" + line(FAR) + b"\n" + b'{"partial')
            first.close()
            second, _ = server.accept()
            second.sendall(line(NEAR) + b"\n")
            second.close()
            wait_for(lambda: logger.disconnects >= 2)
            logger.stop()

        thread = threading.Thread(target=serve)
        thread.start()
        logger.run()
        thread.join()

        saved = b"".join(read_gz(p) for p in glob.glob(os.path.join(self.dir, "adsb", "*.jsonl.gz")))
        self.assertIn(readsb_line + b"\n", saved)
        self.assertIn(line(NEAR) + b"\n", saved)
        self.assertNotIn(b"def456", saved)
        self.assertNotIn(b"partial", saved)
        names = [e["event"] for e in health_events(self.dir)]
        self.assertGreaterEqual(names.count("connected"), 2)
        self.assertIn("disconnected", names)
        self.assertEqual(names[-1], "stop")

    def test_an_oversized_line_is_dropped_whole(self):
        class Chunks:
            """A connection that delivers one chunk per read, then closes."""
            def __init__(self, *chunks):
                self.chunks = list(chunks)

            def settimeout(self, _):
                pass

            def recv(self, _):
                return self.chunks.pop(0) if self.chunks else b""

        logger = make_logger(self.dir)
        logger.check_clock()  # So the first tick doesn't write a health record, which resets the counts
        logger.check_disk()
        stream = Chunks(b"x" * 300, b"x" * 300, b"y" * 50 + b"\n" + line(NEAR) + b"\n")
        with mock.patch.object(al, "MAX_PARTIAL_LINE", 100):
            logger.read_stream(stream)
        logger.writer.close()
        saved = b"".join(read_gz(p) for p in glob.glob(os.path.join(self.dir, "adsb", "*.jsonl.gz")))
        self.assertEqual(saved, line(NEAR) + b"\n")
        self.assertEqual(logger.counts["invalid"], 1)

    def test_survives_having_nothing_to_connect_to(self):
        logger = make_logger(self.dir, port=1)
        timer = threading.Timer(0.2, logger.stop)
        timer.start()
        logger.run()
        timer.join()
        self.assertEqual(health_events(self.dir)[-1]["event"], "stop")

    def test_pauses_when_the_disk_is_low_and_records_why(self):
        logger = make_logger(self.dir, min_free_gb=1e12)
        logger.check_disk()
        logger.handle_line(line(NEAR))
        self.assertEqual(glob.glob(os.path.join(self.dir, "adsb", "*")), [])
        events = health_events(self.dir)
        self.assertEqual(events[-1]["event"], "disk_low_paused")
        self.assertEqual(logger.counts["dropped_disk_full"], 1)
        logger.settings["min_free_gb"] = 0
        logger.check_disk()
        logger.handle_line(line(NEAR))
        logger.writer.close()
        self.assertEqual(len(glob.glob(os.path.join(self.dir, "adsb", "*"))), 1)


class ClockAndErrors(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_clock_changes_are_recorded_and_checked_often_until_synchronised(self):
        states = iter([False, False, True])
        logger = make_logger(self.dir, clock=lambda: {"synchronised": next(states)}, clock_check_seconds=0)
        logger.check_clock()
        logger.tick()  # Still not synchronised: checked again, with no new event
        logger.tick()  # Now synchronised
        events = [e["event"] for e in health_events(self.dir)]
        self.assertEqual(events, ["clock_not_synchronised", "clock_synchronised"])
        self.assertTrue(health_events(self.dir)[-1]["clock"]["synchronised"])

    def test_write_errors_are_recorded_and_retried_later(self):
        logger = make_logger(self.dir, write_retry_seconds=0.05)

        def broken(_):
            raise OSError(5, "Input/output error")

        original = logger.writer.write
        logger.writer.write = broken
        logger.handle_line(line(NEAR))
        logger.handle_line(line(NEAR))  # Dropped while waiting to retry, without another error
        events = [e for e in health_events(self.dir) if e["event"] == "write_error"]
        self.assertEqual(len(events), 1)
        self.assertIn("Input/output error", events[0]["error"])
        self.assertEqual(logger.counts["dropped_write_error"], 2)  # Reported in the next health record
        logger.writer.write = original
        time.sleep(0.06)
        logger.handle_line(line(NEAR))
        logger.writer.close()
        self.assertEqual(len(glob.glob(os.path.join(self.dir, "adsb", "*.jsonl.gz"))), 1)

    def test_health_log_failure_does_not_stop_the_logger(self):
        logger = make_logger(os.path.join(self.dir, "missing"))
        os.chmod(self.dir, 0o500)
        self.addCleanup(os.chmod, self.dir, 0o700)
        logger.health("test")  # Can't write, but mustn't raise


if __name__ == "__main__":
    unittest.main()

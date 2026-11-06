"""Tests for adsb.logger, using a made-up stream on a local socket. No radio is involved.

Run from tools/adsb with: make test (or python3 -m unittest)
"""

import glob
import gzip
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from adsb import logger as al
from adsb.geometry import distance_km

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tools/adsb

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
        self.assertAlmostEqual(distance_km(51.5, 0.1, 51.6, 0.1), 11.12, places=1)


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


# Cut down from a real stats.json, in readsb's own spacing
READSB_STATS = """{ "now" : 1793000060.0, "gain_db" : 43.9, "estimated_ppm" : 0.4,
"last1min":{"start":1793000000.0,"end":1793000060.0,"local":{"accepted":[9,1],"strong_signals":5}},
"last5min":{"start":1793000000.0,"end":1793000040.0,"local":{"samples_processed":3600000000,
"samples_dropped":0,"samples_lost":0,"modeac":0,"modes":900000,"bad":800000,"unknown_icao":40000,
"accepted":[58000,2000],"signal":-14.8,"noise":-33.5,"peak_signal":-1.2,"strong_signals":1800,
"pre_phase_1":[ 1, 2, 3, 4, 5],"best_phase" :[ 1, 2, 3, 4, 5]},"messages_valid": 60000}}"""


class ReceiverStats(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = os.path.join(self.dir, "stats.json")

    def write(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def test_reads_the_last_five_minutes(self):
        self.write(READSB_STATS)
        receiver = al.read_receiver(self.path, now=1_793_000_060.0)
        self.assertEqual(receiver["messages"], 60000)
        self.assertEqual(receiver["strong_signals"], 1800)
        self.assertAlmostEqual(receiver["strong_share"], 0.03)
        self.assertEqual(receiver["gain_db"], 43.9)
        self.assertEqual(receiver["noise_dbfs"], -33.5)
        self.assertEqual(receiver["samples_dropped"], 0)
        self.assertEqual(receiver["age_s"], 20.0)

    def test_missing_damaged_or_no_radio(self):
        self.assertIsNone(al.read_receiver(self.path))
        self.write('{ "now" : 1793000060.0, "gain_db" : 4')  # Read while readsb was replacing it
        self.assertIsNone(al.read_receiver(self.path))
        self.write('{"now": 1.0, "last5min": {"start": 0, "end": 1, "messages_valid": 0}}')  # --net-only
        self.assertIsNone(al.read_receiver(self.path))

    def test_no_messages_yet(self):
        self.write('{"last5min": {"end": 1, "local": {"accepted": [0], "strong_signals": 0}}}')
        self.assertIsNone(al.read_receiver(self.path)["strong_share"])

    def test_every_health_record_includes_it(self):
        self.write(READSB_STATS)
        logger = make_logger(self.dir, readsb_stats=self.path)
        logger.health("test")
        self.assertEqual(health_events(self.dir)[0]["receiver"]["strong_signals"], 1800)


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

    def test_odd_hex_values_are_kept_without_crashing(self):
        logger = make_logger(self.dir)
        logger.handle_line(b'{"hex":["abc"],"lat":51.51,"lon":0.1}')
        logger.handle_line(b'{"hex":null,"lat":51.51,"lon":0.1}')
        logger.close_writer()
        self.assertEqual(logger.counts["written"], 2)
        self.assertEqual(logger.aircraft, set())

    def test_close_low_aircraft_are_listed_in_the_health_record(self):
        logger = make_logger(self.dir)
        for raw in (
            b'{"hex":"aaa111","lat":%.4f,"lon":%.4f,"alt_baro":1200}' % (SITE_LAT + 0.009, SITE_LON),  # 1 km
            b'{"hex":"aaa111","lat":%.4f,"lon":%.4f,"alt_baro":1100}' % (SITE_LAT + 0.0045, SITE_LON),  # nearer
            b'{"hex":"bbb222","lat":%.4f,"lon":%.4f,"alt_baro":9000}' % (SITE_LAT, SITE_LON),  # too high
            b'{"hex":"ccc333","lat":%.4f,"lon":%.4f,"alt_baro":1000}' % (SITE_LAT + 0.05, SITE_LON),  # too far
            b'{"hex":"ddd444","lat":%.4f,"lon":%.4f,"alt_baro":"ground"}' % (SITE_LAT, SITE_LON),
        ):
            logger.handle_line(raw)
        logger.close_writer()
        logger.health()
        logger.health()
        first, second = health_events(self.dir)
        self.assertEqual(first["near"], {"aaa111": 0.5})
        self.assertEqual(first["near_limits"], {"km": 2.0, "max_ft": 3000.0})
        self.assertEqual(second["near"], {})  # Reset with the other counts

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

    def test_a_change_of_clock_state_starts_a_new_file(self):
        states = iter([False, True])
        logger = make_logger(self.dir, clock=lambda: {"synchronised": next(states)})
        logger.check_clock()
        logger.handle_line(line(NEAR))
        logger.check_clock()  # Now synchronised
        logger.handle_line(line(NEAR))
        logger.close_writer()
        files = sorted(glob.glob(os.path.join(self.dir, "adsb", "*.jsonl.gz")))
        self.assertEqual(len(files), 2)
        self.assertEqual(len({e["file"] for e in health_events(self.dir)} - {None}), 1)

    def test_repeated_write_errors_make_it_exit_and_start_afresh(self):
        logger = make_logger(self.dir, write_retry_seconds=0)

        def broken(_):
            raise OSError(30, "Read-only file system")

        logger.writer.write = broken
        for _ in range(al.MAX_WRITE_FAILURES - 1):
            logger.handle_line(line(NEAR))
        self.assertFalse(logger.stopping)
        logger.handle_line(line(NEAR))
        self.assertTrue(logger.stopping)
        self.assertEqual(logger.exit_code, 1)

    def test_a_successful_flush_resets_the_count_of_write_errors(self):
        logger = make_logger(self.dir, write_retry_seconds=0, flush_seconds=0)
        logger.write_failed(OSError(5, "Input/output error"))
        logger.write_failed(OSError(5, "Input/output error"))
        logger.handle_line(line(NEAR))
        logger.tick()
        self.assertEqual(logger.write_failures, 0)
        logger.close_writer()

    def test_lists_the_files_it_is_writing_for_collect(self):
        run = os.path.join(self.dir, "run")
        os.makedirs(run)
        logger = make_logger(self.dir, open_files=os.path.join(run, "open-files"))
        logger.handle_line(line(NEAR))
        logger.health()
        logger.close_writer()
        with open(os.path.join(run, "open-files")) as f:
            names = f.read().split()
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].startswith("adsb/") and names[0].endswith(".jsonl.gz"))
        self.assertTrue(names[1].startswith("health/") and names[1].endswith(".jsonl"))
        self.assertTrue(all(os.path.exists(os.path.join(self.dir, n)) for n in names))

    def test_each_health_record_names_its_boot(self):
        logger = make_logger(self.dir)
        logger.boot_id = "boot-1"
        logger.health()
        self.assertEqual(health_events(self.dir)[-1]["boot_id"], "boot-1")

    def test_the_same_error_goes_to_the_journal_only_now_and_then(self):
        logger = make_logger(self.dir)
        with mock.patch.object(al, "log") as journal:
            for _ in range(5):
                logger.log_once(ConnectionRefusedError(111, "Connection refused"))
            logger.log_once("something else")
        self.assertEqual(journal.call_count, 2)

    def test_health_log_failure_does_not_stop_the_logger(self):
        logger = make_logger(os.path.join(self.dir, "missing"))
        os.chmod(self.dir, 0o500)
        self.addCleanup(os.chmod, self.dir, 0o700)
        logger.health("test")  # Can't write, but mustn't raise


class PiImports(unittest.TestCase):
    """The Pi runs logger and status, which must load only the standard library and the Pi modules."""

    PI_MODULES = {"adsb", "adsb.__main__", "adsb.logger", "adsb.status", "adsb.health", "adsb.geometry"}

    def test_pi_commands_load_only_the_pi_modules(self):
        script = (
            "import sys; before = set(sys.modules)\n"
            "import adsb.__main__, adsb.logger, adsb.status\n"
            "new = sorted(set(sys.modules) - before)\n"
            "print('\\n'.join(new))\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", script], cwd=TOOL_DIR, capture_output=True, text=True, check=True
        )
        loaded = set(done.stdout.split())
        ours = {name for name in loaded if name == "adsb" or name.startswith("adsb.")}
        self.assertEqual(ours - self.PI_MODULES, set())
        stdlib = getattr(sys, "stdlib_module_names", None)  # Python 3.10 and later
        if stdlib is not None:
            self.assertEqual({name.split(".")[0] for name in loaded - ours} - set(stdlib), set())


if __name__ == "__main__":
    unittest.main()

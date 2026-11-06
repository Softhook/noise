#!/usr/bin/env python3
"""Save readsb's JSON position stream to hourly gzip files, and log the health of the Pi.

  python3 -m adsb log --config /etc/adsb-logger/site.json

Lines are stored exactly as readsb sent them, so a mistake in analysis can't damage the record.
Each restart starts a new file, because data added after a damaged gzip section couldn't be read.
Runs on the Pi, so it imports only the standard library and the package's
Pi-side modules (health, geometry). See docs/pi-setup.md and docs/PLAN.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import zlib

from .geometry import distance_km
from .health import DEFAULT_LOG_DIR, read_boot_id

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 30154,
    "log_dir": DEFAULT_LOG_DIR,
    "max_km": 30.0,
    "flush_seconds": 30.0,
    "health_seconds": 300.0,
    "min_free_gb": 2.0,
    "reconnect_seconds": 5.0,
    "clock_check_seconds": 10.0,  # How often to check the clock until it's synchronised
    "write_retry_seconds": 60.0,
    "readsb_stats": "/run/readsb/stats.json",  # Written by readsb every minute; in memory, not on disk
    # The files the logger is writing to, so deploy/collect.sh leaves them for the next visit. In
    # memory (the service's RuntimeDirectory), and only written if its folder exists.
    "open_files": "/run/adsb-logger/open-files",
    # Aircraft this close and low are listed in each health record, so adsb status can count the
    # passes each day. Only a site-visit check; the analysis works from the full log.
    "near_km": 2.0,
    "near_max_ft": 3000.0,
}
NUMERIC_SETTINGS = [key for key in DEFAULTS if key not in ("host", "log_dir", "readsb_stats", "open_files")]
MAX_PARTIAL_LINE = 1024 * 1024
DISK_CHECK_SECONDS = 60.0
SYNCED_CLOCK_CHECK_SECONDS = 60.0
MAX_FLUSH_SECONDS = 60.0  # The plan allows at most 60 s of data lost in a power cut
# After this many write errors in a row, with no successful flush between them, the logger exits
# and systemd starts it again. If the SSD itself has failed, the disk watchdog reboots the Pi
# (deploy/disk-check.sh).
MAX_WRITE_FAILURES = 3
REPEAT_LOG_SECONDS = 600.0  # The same error, such as readsb being down, goes to the journal this often


def log(message):
    """Write to stderr, which systemd sends to the journal."""
    print(f"adsb log: {message}", file=sys.stderr, flush=True)


def classify_line(line, site_lat, site_lon, max_km):
    """Return (decision, record). Unreadable lines are kept, so nothing is silently lost."""
    try:
        record = json.loads(line)
        lat, lon = record.get("lat"), record.get("lon")
    except (ValueError, AttributeError):
        return "invalid", None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return "no_position", record
    if distance_km(site_lat, site_lon, lat, lon) > max_km:
        return "far", record
    return "position", record


class HourlyWriter:
    """Write lines to one gzip file per UTC hour, flushing to disk regularly."""

    def __init__(self, directory, flush_seconds, now=time.time, monotonic=time.monotonic):
        self.directory = directory
        self.flush_seconds = flush_seconds
        self.now = now
        self.monotonic = monotonic
        self.flushed_bytes = 0  # Size of the current file at its last flush
        self.hour = None
        self.raw = None
        self.gz = None
        self.path = None
        self.last_flush = 0.0
        self.unflushed = False

    def write(self, line):
        hour = dt.datetime.fromtimestamp(self.now(), dt.timezone.utc).strftime("%Y-%m-%dT%H")
        if hour != self.hour:
            self.close()
            self._open(hour)
        self.gz.write(line)
        self.unflushed = True

    def _open(self, hour):
        os.makedirs(self.directory, exist_ok=True)
        number = 0
        while True:
            suffix = "" if number == 0 else f".{number}"
            path = os.path.join(self.directory, f"{hour}{suffix}.jsonl.gz")
            try:
                self.raw = open(path, "xb")
                break
            except FileExistsError:
                number += 1
        self.gz = gzip.GzipFile(fileobj=self.raw, mode="wb")
        self.hour, self.path = hour, path
        self.last_flush = self.monotonic()
        self.flushed_bytes = 0

    def flush(self):
        """Flush to disk. True if there was anything to flush."""
        if self.gz is None or not self.unflushed:
            return False
        self.gz.flush(zlib.Z_SYNC_FLUSH)
        self.raw.flush()
        os.fsync(self.raw.fileno())
        self.last_flush = self.monotonic()
        self.flushed_bytes = self.raw.tell()
        self.unflushed = False
        return True

    def tick(self):
        if self.monotonic() - self.last_flush >= self.flush_seconds:
            return self.flush()
        return False

    def close(self):
        if self.gz is None:
            return
        try:
            self.gz.close()
            self.raw.flush()
            os.fsync(self.raw.fileno())
        finally:
            self.raw.close()
            self.gz = self.raw = self.hour = None
            self.unflushed = False


def parse_chrony(text):
    """Pick out the useful fields of `chronyc -c tracking`, keeping the raw text as well."""
    fields = text.strip().split(",")
    result = {"raw": text.strip()}
    if len(fields) < 14:
        result["synchronised"] = None
        return result
    try:
        result["reference"] = fields[1]
        result["stratum"] = int(fields[2])
        result["offset_s"] = float(fields[4])
        result["rms_offset_s"] = float(fields[6])
    except ValueError:
        pass
    result["leap_status"] = fields[13]
    result["synchronised"] = fields[13] != "Not synchronised"
    return result


def run_command(*command):
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def read_first_number(path):
    try:
        with open(path) as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_clock():
    chrony = run_command("chronyc", "-c", "tracking")
    return parse_chrony(chrony) if chrony else {"synchronised": None}


def read_receiver(path, now=None):
    """Signal levels and gain from readsb's stats.json, over its last 5 minutes, or None.

    The share of messages stronger than -3 dBFS shows whether the gain is too high, and so
    whether close aircraft may be missed. See docs/logs.md.
    """
    try:
        with open(path) as f:
            stats = json.load(f)
        period = stats["last5min"]
        local = period["local"]
        messages = sum(local["accepted"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    strong = local.get("strong_signals")
    end = period.get("end")
    now = time.time() if now is None else now
    return {
        "gain_db": stats.get("gain_db"),
        "messages": messages,
        "strong_signals": strong,
        "strong_share": round(strong / messages, 4) if messages and isinstance(strong, int) else None,
        "signal_dbfs": local.get("signal"),
        "noise_dbfs": local.get("noise"),
        "peak_signal_dbfs": local.get("peak_signal"),
        "samples_dropped": local.get("samples_dropped"),
        "age_s": round(now - end, 1) if isinstance(end, (int, float)) else None,
    }


def system_status(log_dir, clock):
    """Read what we can about the Pi. Anything unavailable is recorded as null."""
    temp = read_first_number("/sys/class/thermal/thermal_zone0/temp")
    try:
        free = round(shutil.disk_usage(log_dir).free / 1e9, 2)
    except OSError:
        free = None
    return {
        "clock": clock,
        "cpu_temp_c": None if temp is None else temp / 1000,
        "throttled": run_command("vcgencmd", "get_throttled"),
        "uptime_s": read_first_number("/proc/uptime"),
        "disk_free_gb": free,
    }


class Logger:
    def __init__(self, config, status=system_status, clock=read_clock):
        site = config["site"]
        self.site_lat, self.site_lon = float(site["lat"]), float(site["lon"])
        self.settings = {**DEFAULTS, **config.get("logger", {})}
        for key in NUMERIC_SETTINGS:
            self.settings[key] = float(self.settings[key])
        self.log_dir = self.settings["log_dir"]
        self.status, self.read_clock = status, clock
        self.writer = HourlyWriter(
            os.path.join(self.log_dir, "adsb"), min(self.settings["flush_seconds"], MAX_FLUSH_SECONDS)
        )
        self.clock = {"synchronised": None}
        self.stopping = self.connected = self.paused = False
        self.retry_writes_at = None  # Set after a write error
        self.write_failures = 0  # In a row, since the last successful flush
        self.exit_code = 0
        self.boot_id = read_boot_id()
        self.noted_open = None  # The open files last written to settings["open_files"]
        self.health_path = None
        self.last_logged = (None, -math.inf)
        self.disconnects = 0
        self.last_message = None
        self.last_health = time.monotonic()
        self.last_clock_check = self.last_disk_check = -math.inf
        self._reset_counts()

    def _reset_counts(self):
        self.counts = dict.fromkeys(
            ("lines", "written", "far", "invalid", "no_position", "dropped_disk_full", "dropped_write_error"), 0
        )
        self.aircraft = set()
        self.near = {}  # hex -> closest distance in km since the last health record

    def handle_line(self, line):
        self.counts["lines"] += 1
        self.last_message = time.monotonic()
        decision, record = classify_line(line, self.site_lat, self.site_lon, self.settings["max_km"])
        if record is not None and isinstance(record.get("hex"), str):
            self.aircraft.add(record["hex"])
        if decision != "position":
            self.counts[decision] += 1
        if decision == "far":
            return
        if decision == "position":
            self.note_near(record)
        if self.paused:
            self.counts["dropped_disk_full"] += 1
            return
        if self.retry_writes_at is not None:
            if time.monotonic() < self.retry_writes_at:
                self.counts["dropped_write_error"] += 1
                return
            self.retry_writes_at = None
        try:
            self.writer.write(line + b"\n")
        except OSError as error:
            self.write_failed(error)
            self.counts["dropped_write_error"] += 1
            return
        self.counts["written"] += 1
        if self.writer.path != (self.noted_open or (None,))[0]:
            self.note_open_files()

    def note_near(self, record):
        """Remember an aircraft that passed close to the garden, for the daily count in adsb status."""
        code, altitude = record.get("hex"), record.get("alt_baro")
        if not isinstance(code, str) or not isinstance(altitude, (int, float)):
            return  # On the ground, or no height yet
        if altitude > self.settings["near_max_ft"]:
            return
        km = distance_km(self.site_lat, self.site_lon, record["lat"], record["lon"])
        if km <= self.settings["near_km"] and km < self.near.get(code, math.inf):
            self.near[code] = round(km, 2)

    def close_writer(self):
        try:
            self.writer.close()
        except OSError as error:
            log(f"can't close {self.writer.path}: {error}")

    def write_failed(self, error):
        """Stop writing for a while after a disk error, and record it, rather than looping on it.

        After MAX_WRITE_FAILURES in a row, exit, so systemd starts the logger afresh.
        """
        self.close_writer()
        self.retry_writes_at = time.monotonic() + self.settings["write_retry_seconds"]
        self.write_failures += 1
        log(f"write error: {error}")
        self.health("write_error", error=str(error))
        if self.write_failures >= MAX_WRITE_FAILURES and not self.stopping:
            log(f"{self.write_failures} write errors in a row: exiting, to start afresh")
            self.exit_code = 1
            self.stopping = True

    def note_open_files(self):
        """Write the files being written to, relative to log_dir, for deploy/collect.sh."""
        current = (self.writer.path, self.health_path)
        if current == self.noted_open:
            return
        self.noted_open = current
        path = self.settings["open_files"]
        if not path or not os.path.isdir(os.path.dirname(path)):
            return  # Not running as the service, as in development
        names = sorted(os.path.relpath(p, self.log_dir) for p in current if p)
        try:
            with open(f"{path}.tmp", "w") as f:
                f.write("".join(f"{name}\n" for name in names))
            os.replace(f"{path}.tmp", path)
        except OSError as error:
            log(f"can't write {path}: {error}")

    def log_once(self, message):
        """Log a message, but the same one again only every REPEAT_LOG_SECONDS, to keep the journal readable."""
        text = str(message)
        previous, when = self.last_logged
        if text != previous or time.monotonic() - when >= REPEAT_LOG_SECONDS:
            log(text)
            self.last_logged = (text, time.monotonic())

    def health(self, event=None, **extra):
        now = time.time()
        entry = {
            "time": now, "event": event, "connected": self.connected, **extra, **self.counts,
            "aircraft": len(self.aircraft),
            "near": dict(sorted(self.near.items())),
            "near_limits": {"km": self.settings["near_km"], "max_ft": self.settings["near_max_ft"]},
            "disconnects": self.disconnects,
            "newest_message_age_s": None if self.last_message is None
            else round(time.monotonic() - self.last_message, 1),
            "file": self.writer.path,
            "receiver": read_receiver(self.settings["readsb_stats"]),
            "boot_id": self.boot_id,
        }
        entry.update(self.status(self.log_dir, self.clock))
        try:
            folder = os.path.join(self.log_dir, "health")
            os.makedirs(folder, exist_ok=True)
            day = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m-%d")
            self.health_path = os.path.join(folder, f"{day}.jsonl")
            with open(self.health_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as error:
            # The disk may be failing. Say so in the system journal and keep going.
            log(f"can't write health log: {error}")
        self.note_open_files()
        self._reset_counts()
        self.last_health = time.monotonic()

    def check_clock(self):
        """Read the clock's state, and record each change of synchronisation as an event."""
        previous = self.clock.get("synchronised")
        self.clock = self.read_clock()
        self.last_clock_check = time.monotonic()
        synced = self.clock.get("synchronised")
        if synced is not None and synced != previous:
            # Start a new file, so each file is wholly from a synchronised clock or wholly not
            self.close_writer()
            self.health("clock_synchronised" if synced else "clock_not_synchronised")

    def check_disk(self):
        """Pause writing when the disk is nearly full, and resume when there's room again."""
        self.last_disk_check = time.monotonic()
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            low = shutil.disk_usage(self.log_dir).free / 1e9 < self.settings["min_free_gb"]
        except OSError as error:
            log(f"can't check disk: {error}")
            return
        if low == self.paused:
            return
        if low:
            self.close_writer()
        self.paused = low
        self.health("disk_low_paused" if low else "disk_ok_resumed")

    def tick(self):
        try:
            if self.writer.tick():
                self.write_failures = 0
        except OSError as error:
            self.write_failed(error)
        now = time.monotonic()
        # Check the clock often until it's synchronised, so short unsynchronised periods are caught.
        synced = self.clock.get("synchronised") is True
        clock_interval = SYNCED_CLOCK_CHECK_SECONDS if synced else self.settings["clock_check_seconds"]
        if now - self.last_clock_check >= clock_interval:
            self.check_clock()
        if now - self.last_disk_check >= DISK_CHECK_SECONDS:
            self.check_disk()
        if now - self.last_health >= self.settings["health_seconds"]:
            self.health()

    def read_stream(self, connection):
        partial = b""
        discarding = False  # True while skipping the rest of a line that grew too long
        connection.settimeout(1.0)
        while not self.stopping:
            try:
                data = connection.recv(65536)
            except socket.timeout:
                self.tick()
                continue
            if not data:
                return
            lines = (partial + data).split(b"\n")
            partial = lines.pop()
            if discarding and lines:
                lines.pop(0)  # The end of the oversized line
                discarding = False
            if len(partial) > MAX_PARTIAL_LINE:
                if not discarding:
                    self.counts["invalid"] += 1
                partial = b""
                discarding = True
            for line in lines:
                if line.strip():
                    self.handle_line(line)
            self.tick()

    def wait(self, seconds):
        finish = time.monotonic() + seconds
        while not self.stopping and time.monotonic() < finish:
            time.sleep(min(0.2, seconds))
            self.tick()

    def run(self):
        self.check_disk()
        self.check_clock()
        self.health("start")
        address = (self.settings["host"], int(self.settings["port"]))
        while not self.stopping:
            try:
                with socket.create_connection(address, timeout=5) as connection:
                    self.connected = True
                    self.health("connected")
                    self.read_stream(connection)
            except OSError as error:
                self.log_once(error)
            if self.connected:
                self.connected = False
                self.disconnects += 1
                try:
                    self.writer.flush()
                except OSError as error:
                    self.write_failed(error)
                self.health("disconnected")
            self.wait(self.settings["reconnect_seconds"])
        self.close_writer()
        self.health("stop")

    def stop(self, *_):
        self.stopping = True


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, help="JSON file; see site.example.json")
    args = parser.parse_args(argv)
    try:
        with open(args.config) as f:
            logger = Logger(json.load(f))
    except (OSError, ValueError, KeyError, TypeError) as error:
        # A clear line in the journal; systemd keeps retrying until the config is fixed
        log(f"can't use config {args.config}: {error!r}")
        return 2
    signal.signal(signal.SIGTERM, logger.stop)
    signal.signal(signal.SIGINT, logger.stop)
    logger.run()
    return logger.exit_code


if __name__ == "__main__":
    sys.exit(main())

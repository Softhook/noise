"""Read the logger's health log: clock synchronisation, events, and whether the logger was listening.

The logger writes this log, and adsb status reads it on the Pi, so this must only import the
standard library.
"""

from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import math
import os

DEFAULT_LOG_DIR = "/var/lib/adsb-logger"
# An unsynchronised period still open at a boot's last record may have gone on this long after it
UNSYNCED_TAIL_S = 900
# A day's health file can hold records from other days if the clock was wrong, so files are only
# skipped this far outside the period asked for
FILE_DAY_MARGIN_S = 2 * 86400


def read_boot_id():
    """The kernel's random id for this boot, so records from different boots can be told apart."""
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip() or None
    except OSError:
        return None


def file_day_start(path):
    try:
        day = dt.datetime.strptime(os.path.basename(path), "%Y-%m-%d.jsonl")
    except ValueError:
        return None
    return day.replace(tzinfo=dt.timezone.utc).timestamp()


def read_health_log(log_dir, since=-math.inf):
    """Every readable health record from `since` on, in time order. Written by the logger."""
    entries = []
    for path in sorted(glob.glob(os.path.join(log_dir, "health", "*.jsonl"))):
        day = file_day_start(path)
        if day is not None and day + 86400 + FILE_DAY_MARGIN_S < since:
            continue
        with open(path, errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    entry["time"] = float(entry["time"])
                except (ValueError, KeyError, TypeError):
                    continue
                if entry["time"] >= since:
                    entries.append(entry)
    entries.sort(key=lambda e: e["time"])
    return entries

def health_summary(log_dir):
    """Read the logger's health log: when the clock wasn't synchronised, and what went wrong.

    See unsynced_periods for how the times when the clock wasn't synchronised are found.
    """
    entries = read_health_log(log_dir)
    unsynced = unsynced_periods(entries)
    events = collections.Counter(e["event"] for e in entries if e.get("event"))
    return {"records": len(entries), "unsynced": unsynced, "events": events, "entries": entries}


def unsynced_periods(entries):
    """(start, end) times when the clock wasn't synchronised, in the times the data was stamped with.

    The clock is unsynchronised from a record that says so until the next record that says it's
    synchronised. After a power cut the Pi starts with the time it last saved, which is behind,
    so the records from before the cut and after the boot overlap in time. Each boot's records
    (`boot_id`) are therefore taken in the order they were written (`uptime_s`), and a period
    lasts as long as the uptime says, counted from the time on its first record. That's the time
    base the data in it was stamped with, even when the clock later jumps to the right time.
    Records without them, from an older logger, are taken in time order instead.
    """
    boots = collections.defaultdict(list)
    for entry in entries:
        boots[entry.get("boot_id")].append(entry)
    periods = []
    for boot_id, group in boots.items():
        by_uptime = boot_id is not None and all(isinstance(e.get("uptime_s"), (int, float)) for e in group)
        if by_uptime:
            group = sorted(group, key=lambda e: e["uptime_s"])

        def elapsed(a, b):
            return b["uptime_s"] - a["uptime_s"] if by_uptime else b["time"] - a["time"]

        start = None
        for entry in group:
            synced = (entry.get("clock") or {}).get("synchronised")
            if synced is False and start is None:
                start = entry
            elif synced is True and start is not None:
                periods.append((start["time"], start["time"] + elapsed(start, entry)))
                start = None
        if start is not None:
            tail = UNSYNCED_TAIL_S if by_uptime else 0
            periods.append((start["time"], start["time"] + elapsed(start, group[-1]) + tail))
    return sorted(periods)


def logger_was_listening(entries, start, end, max_spacing_s=900):
    """True if the health log shows the logger running, connected and receiving from start to end.

    A gap in the kept data is then a quiet sky near the garden, not lost data. Without health
    records covering the whole gap, it counts as lost.
    """
    inside = [e for e in entries if start <= e["time"] <= end]
    times = [start] + [e["time"] for e in inside] + [end]
    if any(b - a > max_spacing_s for a, b in zip(times, times[1:])):
        return False
    if any(e.get("connected") is False or e.get("event") in ("start", "stop", "disconnected") for e in inside):
        return False
    return sum(e.get("lines") or 0 for e in inside) > 0

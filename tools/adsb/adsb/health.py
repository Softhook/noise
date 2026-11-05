"""Read the logger's health log: clock synchronisation, events, and whether the logger was listening.

The logger writes this log, and adsb status reads it on the Pi, so this must only import the
standard library.
"""

from __future__ import annotations

import collections
import glob
import json
import math
import os

DEFAULT_LOG_DIR = "/var/lib/adsb-logger"


def read_health_log(log_dir, since=-math.inf):
    """Every readable health record from `since` on, in time order. Written by the logger."""
    entries = []
    for path in sorted(glob.glob(os.path.join(log_dir, "health", "*.jsonl"))):
        with open(path) as f:
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

    The clock is treated as unsynchronised from each record that says so until the next record
    that says it's synchronised, or to the end of the log.
    """
    entries = read_health_log(log_dir)
    unsynced, start = [], None
    for entry in entries:
        synced = (entry.get("clock") or {}).get("synchronised")
        if synced is False and start is None:
            start = entry["time"]
        elif synced is True and start is not None:
            unsynced.append((start, entry["time"]))
            start = None
    if start is not None:
        unsynced.append((start, entries[-1]["time"]))
    events = collections.Counter(e["event"] for e in entries if e.get("event"))
    return {"records": len(entries), "unsynced": unsynced, "events": events, "entries": entries}


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

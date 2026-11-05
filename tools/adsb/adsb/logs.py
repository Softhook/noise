"""Find and read the logger's hourly ADS-B files. The files are only ever read."""

from __future__ import annotations

import glob
import gzip
import json
import os
import re
import zlib

from .common import number, parse_utc


LOG_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2})(?:\.(\d+))?\.jsonl\.gz$")
# A line's time should be within its file's hour. readsb and the logger read the same clock, so a
# line far outside it has a corrupt time, and would otherwise upset the time order of everything after.
MISDATED_BEFORE_S = 3600
MISDATED_AFTER_S = 7200


def file_hour(path):
    """Start of the UTC hour a log file was named for, or None for an unexpected name."""
    match = LOG_NAME.match(os.path.basename(path))
    return parse_utc(match.group(1).replace("T", " ") + ":00") if match else None


def log_paths(log_dir, start=None, end=None):
    """Log files in time order. A restart's file (T12.1) comes after the file it follows (T12).

    With start or end, files more than an hour outside the period are skipped.
    """
    found = []
    for path in glob.glob(os.path.join(log_dir, "**", "*.jsonl.gz"), recursive=True):
        match = LOG_NAME.match(os.path.basename(path))
        if match:
            hour = file_hour(path)
            if start is not None and hour + MISDATED_AFTER_S < start:
                continue
            if end is not None and hour - MISDATED_BEFORE_S >= end:
                continue
            found.append((0, hour, int(match.group(2) or 0), path))
        else:
            found.append((1, 0, 0, path))  # Unexpected names go last, in name order
    return [item[3] for item in sorted(found)]


def read_log_records(paths, report):
    """Yield every readable record. A damaged file is read up to the damage and then reported.

    In a file named for its hour, a record whose `now` is far outside that hour is counted as
    misdated and skipped.
    """
    for path in paths:
        report["files"] += 1
        hour = file_hour(path)
        try:
            with gzip.open(path, "rb") as f:
                for line in f:
                    report["lines"] += 1
                    try:
                        record = json.loads(line)
                    except ValueError:
                        report["invalid_lines"] += 1
                        continue
                    if not isinstance(record, dict):
                        report["invalid_lines"] += 1
                        continue
                    now = number(record.get("now"))
                    if hour is not None and now is not None and not (
                        hour - MISDATED_BEFORE_S <= now < hour + MISDATED_AFTER_S
                    ):
                        report["misdated_lines"] += 1
                        continue
                    yield record
        except (EOFError, OSError, zlib.error) as error:
            report["damaged_files"].append(f"{os.path.basename(path)}: {error}")

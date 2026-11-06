#!/usr/bin/env python3
"""Check the logger on a site visit: is it running, is the clock right, and is data being kept?

  python3 -m adsb status [--log-dir /var/lib/adsb-logger] [--hours 24] [--html PAGE]

Reads the health log and lists the data files. It changes nothing in the log folder. Exits with 1
if there are warnings, so it can also be used in scripts. With --html it writes the report as a
web page instead, for the status page on the Pi (deploy/adsb-status.timer), and exits with 0.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import html
import os
import sys
import time

from .health import DEFAULT_LOG_DIR, read_health_log

THRESHOLDS = {
    "stale_health_s": 900,  # The logger writes at least every 5 minutes
    "min_free_gb": 10,
    "max_far_share": 0.98,
    "max_cpu_temp_c": 75,
}


def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def data_files(log_dir):
    """Return (count, total bytes, newest path) for the ADS-B files."""
    paths = glob.glob(os.path.join(log_dir, "adsb", "*.jsonl.gz"))
    newest = max(paths, key=os.path.getmtime, default=None)
    return len(paths), sum(map(os.path.getsize, paths)), newest


def check(log_dir, hours, now=None):
    """Return (report lines, warnings)."""
    now = time.time() if now is None else now
    entries = read_health_log(log_dir, since=now - hours * 3600)
    lines, warnings = [], []
    if not entries:
        warnings.append(f"No health records in the last {hours:g} hours. Is the logger running?")
        return lines, warnings

    last = entries[-1]
    age = now - last["time"]
    lines.append(f"Last health record: {utc(last['time'])} ({age / 60:.0f} minutes ago)")
    if age > THRESHOLDS["stale_health_s"]:
        warnings.append(f"The last health record is {age / 60:.0f} minutes old. Is the logger running?")

    clock = last.get("clock") or {}
    synced = clock.get("synchronised")
    offset = clock.get("offset_s")
    lines.append(
        f"Clock: {'synchronised' if synced else 'NOT synchronised' if synced is False else 'unknown'}"
        + (f" to {clock.get('reference')}" if clock.get("reference") else "")
        + (f", offset {offset * 1000:.1f} ms" if isinstance(offset, (int, float)) else "")
    )
    if synced is not True:
        warnings.append("The clock isn't known to be synchronised. Check the GPS has a view of the sky.")

    free = last.get("disk_free_gb")
    if free is not None:
        lines.append(f"Disk free: {free:.1f} GB")
        if free < THRESHOLDS["min_free_gb"]:
            warnings.append(f"Only {free:.1f} GB free.")
    temp = last.get("cpu_temp_c")
    if temp is not None:
        lines.append(f"CPU temperature: {temp:.0f} °C")
        if temp > THRESHOLDS["max_cpu_temp_c"]:
            warnings.append(f"The Pi is hot ({temp:.0f} °C).")
    throttled = last.get("throttled")
    if throttled:
        lines.append(f"Power and heat flags: {throttled}")
        if throttled.strip() != "throttled=0x0":
            warnings.append(f"The Pi reports power or heat problems ({throttled}). Check the power supply.")
    if last.get("uptime_s") is not None:
        lines.append(f"Uptime: {last['uptime_s'] / 3600:.1f} hours")

    totals = collections.Counter()
    events = collections.Counter()
    for entry in entries:
        for key in ("lines", "written", "far", "invalid", "dropped_disk_full", "dropped_write_error"):
            if isinstance(entry.get(key), (int, float)):
                totals[key] += entry[key]
        if entry.get("event"):
            events[entry["event"]] += 1
    lines.append(
        f"Last {hours:g} hours: {totals['lines']:,} lines received, {totals['written']:,} kept, "
        f"{totals['far']:,} too far away, {totals['invalid']:,} unreadable"
    )
    if totals["lines"] == 0:
        warnings.append("No ADS-B data received. Check readsb and the antenna.")
    elif totals["written"] == 0:
        warnings.append("Nothing is being kept, so everything is being discarded as too far away. "
                        "Check the site latitude and longitude in the config.")
    elif totals["far"] / totals["lines"] > THRESHOLDS["max_far_share"]:
        warnings.append(f"{totals['far'] / totals['lines']:.0%} of lines are too far away. Check the site location.")
    for key, text in (("dropped_disk_full", "lines dropped because the disk was full"),
                      ("dropped_write_error", "lines dropped because of write errors")):
        if totals[key]:
            warnings.append(f"{totals[key]:,} {text}.")
    if events:
        lines.append("Events: " + ", ".join(f"{name} x{n}" for name, n in sorted(events.items())))
    for name, text in (("write_error", "Disk write errors"), ("disk_low_paused", "Logging paused for a full disk"),
                       ("clock_not_synchronised", "Clock lost synchronisation")):
        if events[name]:
            warnings.append(f"{text}: {events[name]} times.")
    if events["disconnected"] > hours:
        warnings.append(f"readsb disconnected {events['disconnected']} times.")

    count, size, newest = data_files(log_dir)
    lines.append(f"Data files: {count}, " + (f"{size / 1e9:.2f} GB" if size >= 1e9 else f"{size / 1e6:.1f} MB"))
    if newest:
        newest_age = now - os.path.getmtime(newest)
        lines.append(f"Newest file: {os.path.basename(newest)}, changed {newest_age / 60:.0f} minutes ago")
    return lines, warnings


def html_page(lines, warnings, now):
    """The report as a small web page that reloads itself every minute."""
    escape = html.escape
    items = "".join(f"<li>{escape(w)}</li>" for w in warnings)
    verdict = f"<h2>Warnings</h2><ul class=warn>{items}</ul>" if warnings else "<p class=ok>No problems found.</p>"
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<meta http-equiv=refresh content=60><title>ADS-B logger status</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:1.5rem auto;padding:0 1rem}}
pre{{white-space:pre-wrap}}.ok{{color:#116622;font-weight:bold}}.warn{{color:#a01010}}</style></head>
<body><h1>ADS-B logger status</h1>
<p>Checked {escape(utc(now))}. This page reloads every minute. <a href="/tar1090/">Live map</a></p>
{verdict}<pre>{escape(chr(10).join(lines))}</pre></body></html>
"""


def write_atomically(path, text):
    """Replace the page in one step, so the web server never sends half of it."""
    temporary = f"{path}.tmp"
    with open(temporary, "w") as f:
        f.write(text)
    os.replace(temporary, path)


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--html", metavar="PAGE", help="write the report to this web page instead")
    args = parser.parse_args(argv)
    now = time.time()
    lines, warnings = check(args.log_dir, args.hours, now=now)
    if args.log_dir == DEFAULT_LOG_DIR and os.path.isdir(args.log_dir) and not os.path.ismount(args.log_dir):
        warnings.insert(0, f"{args.log_dir} isn't a mounted disk, so the logger is waiting for the SSD.")
    if args.html:
        write_atomically(args.html, html_page(lines, warnings, now))
        return 0
    print("\n".join(lines))
    if warnings:
        print("\nWARNINGS")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("\nNo problems found.")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())

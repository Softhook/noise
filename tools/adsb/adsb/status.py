#!/usr/bin/env python3
"""Check the logger on a site visit: is it running, is the clock right, and is data being kept?

  python3 -m adsb status [--log-dir /var/lib/adsb-logger] [--hours 24] [--html PAGE]

Reads the health log and lists the data files. It changes nothing in the log folder. Exits with 1
if there are warnings, so it can also be used in scripts. With --html it writes the report as a
web page instead, for the status page on the Pi (deploy/adsb-status.timer), and exits with 0.

On the Pi (with the default --log-dir) it also checks the clock, readsb and the logger directly,
rather than only through the log, and finds the newest health record by this boot's uptime.
After a power cut the clock starts behind, so the newest record by time may be from before the cut.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import html
import math
import os
import statistics
import subprocess
import sys
import time

from .health import DEFAULT_LOG_DIR, read_boot_id, read_health_log

THRESHOLDS = {
    "stale_health_s": 900,  # The logger writes at least every 5 minutes
    "min_free_gb": 10,
    "max_far_share": 0.98,
    "max_cpu_temp_c": 75,
    # Share of messages above -3 dBFS. About 5% is the usual aim; near an airport up to 10% is fine.
    # Higher means the gain is too high, so the closest aircraft, the ones we need, may be missed.
    # https://github.com/wiedehopf/adsb-wiki/wiki/Optimizing-gain
    "max_strong_share": 0.10,
    # A whole day with fewer close passes than this share of the usual day suggests the receiver
    # or antenna failed. Loose on purpose: wind direction and LCY's weekend closure change the count a lot.
    "min_day_passes_share": 0.2,
    "min_usual_day_passes": 10,  # Don't compare until a usual day has at least this many
    # readsb hears aircraft far beyond the garden, day and night, so this long with nothing means
    # the stick, antenna or readsb has failed
    "max_silence_s": 900,
}
PASS_DAYS = 7
PASS_GAP_S = 1200  # The same aircraft back after this long is a new pass


def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def data_files(log_dir):
    """Return (count, total bytes, newest path) for the ADS-B files."""
    paths = glob.glob(os.path.join(log_dir, "adsb", "*.jsonl.gz"))
    newest = max(paths, key=os.path.getmtime, default=None)
    return len(paths), sum(map(os.path.getsize, paths)), newest


def live_state():
    """What the Pi can tell us now, without the log: this boot, the clock, and the services."""
    from .logger import read_clock, read_first_number  # Pi-side, standard library only

    services = {}
    for name in ("readsb", "adsb-logger"):
        try:  # is-active prints the state, and exits with non-zero unless it's active
            done = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.stdout.strip():
            services[name] = done.stdout.strip()
    try:
        done = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", DEFAULT_LOG_DIR],
                              capture_output=True, text=True, timeout=5)
        log_disk = done.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        log_disk = None
    return {"boot_id": read_boot_id(), "uptime_s": read_first_number("/proc/uptime"),
            "clock": read_clock(), "services": services, "log_disk": log_disk}


def newest_record(entries, now, live):
    """Return (the newest health record, its age in seconds), or (None, None).

    With this boot's id and uptime, the newest is the one from this boot with the highest uptime,
    and its age comes from the uptime, so a wrong clock can't hide a stopped logger.
    """
    if live and live.get("boot_id") and isinstance(live.get("uptime_s"), (int, float)):
        this_boot = [e for e in entries
                     if e.get("boot_id") == live["boot_id"] and isinstance(e.get("uptime_s"), (int, float))]
        if not this_boot:
            return None, None
        last = max(this_boot, key=lambda e: e["uptime_s"])
        return last, live["uptime_s"] - last["uptime_s"]
    last = entries[-1]
    return last, now - last["time"]


def check(log_dir, hours, now=None, live=None):
    """Return (report lines, warnings). `live` is from live_state(), on the Pi."""
    now = time.time() if now is None else now
    since = now - hours * 3600
    # Read once, for both the period asked for and the week of close passes
    every = read_health_log(log_dir, since=min(since, now - (PASS_DAYS + 1) * 86400))
    entries = [e for e in every if e["time"] >= since]
    lines, warnings = [], []
    if live:
        live_report(live, lines, warnings)
    if not entries:
        warnings.append(f"No health records in the last {hours:g} hours. Is the logger running?")
        return lines, warnings

    last, age = newest_record(entries, now, live)
    if last is None:
        warnings.append(f"The logger hasn't written a health record since the Pi started "
                        f"{live['uptime_s'] / 60:.0f} minutes ago. Is it running?")
        last = entries[-1]
    else:
        lines.append(f"Last health record: {utc(last['time'])} ({age / 60:.0f} minutes ago)")
        if age > THRESHOLDS["stale_health_s"]:
            warnings.append(f"The last health record is {age / 60:.0f} minutes old. Is the logger running?")
        stream_report(last, warnings)

    if not (live and live.get("clock", {}).get("synchronised") is not None):
        clock_report(last.get("clock") or {}, "", lines, warnings)

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
    receiver_report(entries, hours, lines, warnings)

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

    passes_report(every, now, lines, warnings)

    count, size, newest = data_files(log_dir)
    lines.append(f"Data files: {count}, " + (f"{size / 1e9:.2f} GB" if size >= 1e9 else f"{size / 1e6:.1f} MB"))
    if newest:
        newest_age = now - os.path.getmtime(newest)
        lines.append(f"Newest file: {os.path.basename(newest)}, changed {newest_age / 60:.0f} minutes ago")
    return lines, warnings


def clock_report(clock, when, lines, warnings):
    synced = clock.get("synchronised")
    offset = clock.get("offset_s")
    lines.append(
        f"Clock{when}: {'synchronised' if synced else 'NOT synchronised' if synced is False else 'unknown'}"
        + (f" to {clock.get('reference')}" if clock.get("reference") else "")
        + (f", offset {offset * 1000:.1f} ms" if isinstance(offset, (int, float)) else "")
    )
    if synced is not True:
        warnings.append("The clock isn't known to be synchronised. Check the GPS has a view of the sky.")


def live_report(live, lines, warnings):
    """The checks made directly on the Pi, rather than through the log."""
    if (live.get("log_disk") or "").startswith("/dev/mmcblk"):
        warnings.append(f"The Pi booted from an SD card ({live['log_disk']}), not the SSD, so the logger "
                        "won't run. Remove the SD card and reboot.")
    clock = live.get("clock") or {}
    if clock.get("synchronised") is not None:
        clock_report(clock, " (now)", lines, warnings)
    for name, state in sorted((live.get("services") or {}).items()):
        if state != "active":
            warnings.append(f"{name} is {state}, not running. See: journalctl -u {name} -n 30")


def stream_report(last, warnings):
    """Is readsb sending anything? A dead stick or a stopped readsb shows here first."""
    if last.get("event") == "stop":
        warnings.append(f"The logger stopped at {utc(last['time'])}. Start it with: sudo systemctl start adsb-logger")
        return
    if last.get("connected") is False:
        warnings.append("The logger isn't connected to readsb, so nothing is being logged. "
                        "Check readsb: journalctl -u readsb -n 30")
        return
    silence = last.get("newest_message_age_s")
    if isinstance(silence, (int, float)) and silence > THRESHOLDS["max_silence_s"]:
        warnings.append(f"Nothing from readsb for {silence / 60:.0f} minutes. Check the stick, the antenna "
                        "and readsb.")
    elif silence is None and last.get("connected") and not last.get("event") and "newest_message_age_s" in last:
        warnings.append("Nothing from readsb since the logger started. Check the stick, the antenna and readsb.")


def receiver_report(entries, hours, lines, warnings):
    """Gain and signal levels from readsb, and the share of strong signals over the whole period."""
    if "receiver" not in entries[-1]:
        return  # Written by a logger from before receiver statistics were recorded
    last = entries[-1]["receiver"]
    if not last:
        lines.append("Receiver: no statistics from readsb (/run/readsb/stats.json)")
        return
    parts = []
    for key, label, unit in (("gain_db", "gain", "dB"), ("signal_dbfs", "signal", "dBFS"),
                             ("noise_dbfs", "noise", "dBFS"), ("peak_signal_dbfs", "peak", "dBFS")):
        if isinstance(last.get(key), (int, float)):
            parts.append(f"{label} {last[key]:.1f} {unit}")
    if last.get("strong_share") is not None:
        parts.append(f"strong signals {last['strong_share']:.1%}")
    lines.append("Receiver: " + (", ".join(parts) or "no signal figures"))

    # Each record covers readsb's last 5 minutes, so the sums give the share over the period.
    messages = strong = dropped = 0
    for entry in entries:
        receiver = entry.get("receiver") or {}
        if isinstance(receiver.get("messages"), int) and isinstance(receiver.get("strong_signals"), int):
            messages += receiver["messages"]
            strong += receiver["strong_signals"]
        if isinstance(receiver.get("samples_dropped"), int):
            dropped += receiver["samples_dropped"]
    if messages:
        share = strong / messages
        lines.append(f"Strong signals, last {hours:g} hours: {share:.1%} of {messages:,} messages")
        if share > THRESHOLDS["max_strong_share"]:
            warnings.append(f"{share:.0%} of messages are very strong, so the gain may be too high and the "
                            "closest aircraft missed. Lower the gain (see docs/pi-setup.md).")
    if dropped:
        warnings.append(f"readsb dropped {dropped:,} sample blocks, which means the Pi's CPU is overloaded.")


def daily_passes(entries):
    """Count the passes close to the garden for each UTC day, from the health records' `near` lists.

    Returns (counts by day, set of days the health log covers from start to end, time of the last
    pass, the limits used), or None if the logger doesn't record close passes.
    """
    if not any("near" in e for e in entries):
        return None
    counts, last_seen, last_pass, limits = collections.Counter(), {}, None, None
    for entry in entries:
        limits = entry.get("near_limits") or limits
        for code in entry.get("near") or {}:
            t = entry["time"]
            if t - last_seen.get(code, -math.inf) > PASS_GAP_S:
                counts[utc_day(t)] += 1
            last_seen[code] = t
            last_pass = t if last_pass is None else max(last_pass, t)
    first, last = entries[0]["time"], entries[-1]["time"]
    complete, day = set(), utc_day(first)
    while day <= utc_day(last):
        start = dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
        if first <= start + 900 and last >= start + 86400 - 900:
            complete.add(day)
        day = utc_day(start + 86400)
    return counts, complete, last_pass, limits


def passes_report(entries, now, lines, warnings):
    """Close passes per day, so a site visit shows at once if the flights we need stopped arriving."""
    entries = [e for e in entries if e["time"] >= now - (PASS_DAYS + 1) * 86400]
    found = daily_passes(entries) if entries else None
    if found is None:
        return
    counts, complete, last_pass, limits = found
    limits = limits or {}
    within = (f" (within {limits['km']:g} km and below {limits['max_ft']:,.0f} ft)"
              if isinstance(limits.get("km"), (int, float)) and isinstance(limits.get("max_ft"), (int, float))
              else "")
    lines.append(f"Close passes{within}, by UTC day:")
    days = sorted({utc_day(e["time"]) for e in entries})[-PASS_DAYS:]
    for day in days:
        weekday = dt.datetime.strptime(day, "%Y-%m-%d").strftime("%a")
        note = "" if day in complete else " (part of the day)"
        lines.append(f"  {day} {weekday}: {counts[day]}{note}")
    lines.append("Last close pass: " + (f"{utc(last_pass)} ({(now - last_pass) / 3600:.1f} hours ago)"
                                        if last_pass else "none recorded"))
    whole = [counts[d] for d in days if d in complete]
    if len(whole) >= 2:
        for day in days:
            if day not in complete:
                continue
            others = [counts[d] for d in days if d in complete and d != day]
            usual = statistics.median(others)
            if usual >= THRESHOLDS["min_usual_day_passes"] and \
                    counts[day] < THRESHOLDS["min_day_passes_share"] * usual:
                warnings.append(f"Only {counts[day]} close passes on {day}, against about {usual:.0f} on "
                                "other days. Check the antenna and the stick, and the log for gaps.")


def utc_day(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d")


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
<p id=age class=warn hidden></p>
{verdict}<pre>{escape(chr(10).join(lines))}</pre>
<script>
// Compare the Pi's time with this phone's: a page that's too old means the status timer stopped,
// and one from the future, or hours old, means the Pi's clock is wrong
var made = {now * 1000:.0f}, ahead = (Date.now() - made) / 1000;
if (ahead < -120 || ahead > 180) {{
  var p = document.getElementById("age");
  p.textContent = "This page's time is " + Math.round(Math.abs(ahead) / 60) + " minutes "
    + (ahead < 0 ? "ahead of" : "behind") + " this device's clock. Either the page has stopped "
    + "updating, or the Pi's clock is wrong: check the clock line below.";
  p.hidden = false;
}}
</script></body></html>
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
    on_pi = args.log_dir == DEFAULT_LOG_DIR
    lines, warnings = check(args.log_dir, args.hours, now=now, live=live_state() if on_pi else None)
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

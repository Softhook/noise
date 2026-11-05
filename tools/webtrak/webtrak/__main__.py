"""Collect noise monitor data from London City Airport's WebTrak.

usage: python3 -m webtrak COMMAND [options]      (from tools/webtrak)

commands:
  monitors   list the site's noise monitors and their ids
  follow     keep collecting as new data appears (about 25 minutes behind real time)
  fetch      download a past period, in local time
  range      show the period WebTrak holds
  serve      a local web app for starting downloads, watching them and seeing statistics

NMT6, St Pauls Church in Thamesmead, is monitor 106 and is the default. --nmt 106,103 collects
several monitors from the same downloads.
Run python3 -m webtrak COMMAND --help for each command's options.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import sys
import time

from . import client as client_mod
from . import parse, store

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(HERE, "data")
DEFAULT_MONITOR = "106"

# Used if the site configuration can't be read. From WebTrak's configuration on 5 Nov 2026.
KNOWN_MONITORS = {
    "lcy": [
        {"id": "101", "name": "Ramada Hotel", "lat": 51.5073, "lon": 0.0391},
        {"id": "102", "name": "Festival Site", "lat": 51.5042, "lon": 0.0378},
        {"id": "103", "name": "Galleons Reach Apartment Site", "lat": 51.50613, "lon": 0.0746},
        {"id": "104", "name": "London Royal docks compound", "lat": 51.50195, "lon": 0.0731},
        {"id": "105", "name": "East India Dock Basin", "lat": 51.5086, "lon": 0.0029},
        {"id": "106", "name": "St Pauls Church, Thamesmead", "lat": 51.50535, "lon": 0.11075},
    ],
}


def log(message):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def load_monitors(client, site, out_dir):
    """The site's monitors: from WebTrak, else the copy saved last time, else the built-in list."""
    cache = os.path.join(out_dir, "monitors.json")
    try:
        monitors = client.monitors()
        os.makedirs(out_dir, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(monitors, f, indent=1)
        return monitors
    except Exception as error:  # the config service is separate from the data; carry on without it
        log(f"couldn't read the monitor list ({error}); using the saved copy")
    try:
        with open(cache) as f:
            return json.load(f)
    except (OSError, ValueError):
        return KNOWN_MONITORS.get(site, [])


def find_monitor(monitors, monitor_id):
    for m in monitors:
        if str(m["id"]) == str(monitor_id):
            return {"id": str(m["id"]), "name": m["name"], "lat": float(m["lat"]), "lon": float(m["lon"])}
    raise SystemExit(f"monitor {monitor_id} isn't in the site's monitor list; try the monitors command")


def print_events(events, monitor):
    for e in events:
        who, extra = "no aircraft in range", ""
        if e.get("track"):
            who = e.get("callsign") or f"track {e['track']}"
            extra = (f" {e.get('type') or '?'} {e.get('direction')}/{e.get('airport') or '-'}"
                     f" at {e['closest_slant_m']} m slant, {e['closest_height_m']} m up")
        print(f"    NMT{monitor['id']} EVENT {e['start_local'][11:19]}  LAmax {e['lmax_db']:.1f}  "
              f"SEL {e['sel_db']:.1f}  {e['duration_s']:.0f} s  class {e['event_class']}  -> {who}{extra}", flush=True)


def describe(summary, monitor, quiet=False):
    if summary is None or quiet:
        return
    level = (f"LAeq,30s {summary['leq']:5.1f}  max {summary['max']:5.1f} dB" if summary["leq"] is not None
             else "no levels")
    status = "" if summary["radar_status"] in ("online", "") else f"  radar {summary['radar_status']}"
    print(f"{summary['start'][11:19]}  NMT{monitor['id']}  {level}  aircraft nearby {summary['aircraft']}{status}",
          flush=True)
    print_events(summary["events"], monitor)


def handle_ranges(handles):
    """Compact text for a list of handles, as UTC times: '2026-11-05T08:00:00Z to 08:04:30Z (10)'."""
    out, handles = [], sorted(handles)
    i = 0
    while i < len(handles):
        j = i
        while j + 1 < len(handles) and handles[j + 1] == handles[j] + 1:
            j += 1
        a, b = store.iso_utc(parse.utc_for_handle(handles[i])), store.iso_utc(parse.utc_for_handle(handles[j]))
        out.append(a if i == j else f"{a} to {b[11:]} ({j - i + 1})")
        i = j + 1
    return ", ".join(out[:5]) + (f" and {len(out) - 5} more ranges" if len(out) > 5 else "")


class Retry:
    """When to ask again for a chunk that wasn't available or failed: after 1, 2, 4 ... 30 minutes."""

    def __init__(self, first=60, most=1800, clock=time.monotonic):
        self.first, self.most, self.clock = first, most, clock
        self.next = {}  # handle -> (monotonic time to try again, last wait)

    def waiting(self, handle):
        return handle in self.next and self.clock() < self.next[handle][0]

    def failed(self, handle):
        """Note a failure; True if it's the first for this handle."""
        first = handle not in self.next
        wait = self.first if first else min(self.most, self.next[handle][1] * 2)
        self.next[handle] = (self.clock() + wait, wait)
        return first

    def done(self, handle):
        self.next.pop(handle, None)

    def forget_before(self, handle):
        for h in [h for h in self.next if h < handle]:
            del self.next[h]


MAX_FAILURES_IN_A_ROW = 3
# Chunks fetched either side of a period, so that events near its ends see all the radar they need.
PAD = store.MATCH_WINDOW_S // parse.WINDOW_S + 1


def get_chunk(client, cache, handle):
    """A chunk from the raw cache, or else from WebTrak (and then cached). Raises NotAvailable or OSError."""
    if cache is not None:
        text = cache.get(handle)
        if text is not None:
            try:
                return parse.parse_chunk(text, handle)
            except parse.NotAvailable:
                pass  # shouldn't have been cached; ask again
    text = client.chunk_text(handle)
    chunk = parse.parse_chunk(text, handle)
    if cache is not None:
        cache.put(handle, text)
    return chunk


def missing(stores, first, last):
    """Handles from first to last (inclusive) that at least one store hasn't saved, in order."""
    return sorted({h for _, s in stores for a, b in s.gaps(first, last) for h in range(a, b + 1)})


class Stop:
    """Set by SIGINT or SIGTERM, so a run stops between chunks rather than in the middle of writing one."""

    def __init__(self):
        self.now = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self.set)

    def set(self, *_):
        self.now = True

    def __bool__(self):
        return self.now


def save_range(client, cache, stores, first, last, quiet=False, retry=None, give_up=True, stop=None):
    """Fetch and save every handle from first to last that some store hasn't saved.

    Returns (saved, failed): failed counts network failures, which a later run can retry.
    """
    todo = missing(stores, first, last)
    saved = failed = in_a_row = 0
    unavailable = []
    for handle in todo:
        if stop:
            log("stopping")
            break
        if retry is not None and retry.waiting(handle):
            continue
        try:
            chunk = get_chunk(client, cache, handle)
        except parse.NotAvailable:
            if retry is None or retry.failed(handle):
                unavailable.append(handle)
            continue
        except OSError as error:
            failed += 1
            in_a_row += 1
            if retry is not None:
                retry.failed(handle)
            log(f"chunk {handle} ({store.iso_utc(parse.utc_for_handle(handle))}) failed: {error}")
            if in_a_row >= MAX_FAILURES_IN_A_ROW:
                log(f"{in_a_row} failures in a row; WebTrak looks unreachable, stopping this pass")
                failed += sum(1 for h in todo if h > handle)
                break
            continue
        in_a_row = 0
        if retry is not None:
            retry.done(handle)
        for monitor, monitor_store in stores:
            describe(monitor_store.save(chunk, give_up), monitor, quiet)
        saved += 1
    if unavailable:
        log(f"not available from WebTrak: {handle_ranges(unavailable)}")
    return saved, failed


def common_args(parser, delay):
    parser.add_argument("--site", default="lcy", help="WebTrak site name (default lcy)")
    parser.add_argument("--nmt", default=DEFAULT_MONITOR, help="monitor id, or several separated by commas "
                        "(default 106, NMT6 St Pauls Thamesmead)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output folder (default tools/webtrak/data)")
    parser.add_argument("--radius", type=float, default=3000, help="save radar positions within this many metres "
                        "of the monitor (default 3000)")
    parser.add_argument("--no-raw", action="store_true", help="don't keep downloaded chunks (they are kept by "
                        "default, gzipped, so a chunk is never downloaded twice)")
    parser.add_argument("--delay", type=float, default=delay, help=f"seconds between requests (default {delay:g}, "
                        "minimum 0.5)")
    parser.add_argument("--quiet", action="store_true", help="don't print each chunk")


def setup(args):
    client = client_mod.Client(site=args.site, min_interval=max(0.5, args.delay))
    out_dir = os.path.join(args.out, args.site)
    ids = list(dict.fromkeys(m.strip() for m in str(args.nmt).split(",") if m.strip()))
    if not ids:
        raise SystemExit("--nmt needs at least one monitor id")
    monitors = load_monitors(client, args.site, out_dir)
    stores = []
    for monitor_id in ids:
        monitor = find_monitor(monitors, monitor_id)
        monitor_store = store.MonitorStore(out_dir, monitor, radius_m=args.radius)
        monitor_store.lock()
        stores.append((monitor, monitor_store))
    cache = None if args.no_raw else store.RawCache(out_dir)
    return client, cache, stores


def names(stores):
    return ", ".join(f"NMT{m['id']} {m['name']}" for m, _ in stores)


def cmd_follow(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Keep collecting as new WebTrak data appears.")
    common_args(parser, delay=1.0)
    parser.add_argument("--backfill", type=float, default=1.0, help="on a first run, or after a long break, "
                        "go back at most this many hours; missing chunks in this period are retried "
                        "(default 1)")
    parser.add_argument("--poll", type=float, default=30, help="seconds between checks for new data (default 30)")
    args = parser.parse_args(argv)
    client, cache, stores = setup(args)
    for _, monitor_store in stores:
        monitor_store.prime_buffer()
    log(f"following {names(stores)}, saving to {os.path.dirname(stores[0][1].dir)}")

    stop = Stop()
    reported_lag = None
    retry = Retry()
    while not stop:
        try:
            latest = client.latest_handle()
        except (OSError, parse.NotAvailable) as error:
            log(f"couldn't reach WebTrak: {error}")
            latest = None
        if latest is not None:
            earliest = latest - int(args.backfill * 3600 / parse.WINDOW_S) + 1
            for monitor, monitor_store in stores:
                last = monitor_store.last_handle
                if last is not None and last + 1 < earliest:
                    log(f"NMT{monitor['id']} gap: {earliest - last - 1} chunks are older than --backfill and are "
                        f"skipped; use fetch to get them")
            retry.forget_before(earliest)
            save_range(client, cache, stores, earliest, latest, args.quiet, retry, stop=stop)
            lag = round((time.time() - parse.utc_for_handle(latest) - parse.WINDOW_S) / 60)
            if reported_lag is None or abs(lag - reported_lag) >= 5:
                log(f"WebTrak is {lag} minutes behind real time")
                reported_lag = lag
        end = time.monotonic() + args.poll
        while not stop and time.monotonic() < end:
            time.sleep(0.5)
    log("stopped; events still waiting for radar are kept and matched on the next run")
    return 0


def cmd_fetch(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Download a past period from WebTrak.")
    common_args(parser, delay=2.0)
    parser.add_argument("--from", dest="start", required=True, help="local start, 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--to", dest="end", required=True, help="local end, 'YYYY-MM-DD HH:MM' (not included)")
    args = parser.parse_args(argv)
    start, end = parse.local_to_utc(args.start), parse.local_to_utc(args.end)
    if end <= start:
        raise SystemExit("--to must be after --from")
    client, cache, stores = setup(args)
    first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
    held_from = None
    try:
        held_text = client.date_range()[0]
        held_from = parse.handle_for_utc(parse.local_to_utc(held_text))
        if first < held_from:
            log(f"WebTrak's data starts at {held_text} local time; starting there")
            first = held_from
    except (OSError, ValueError) as error:
        log(f"couldn't read WebTrak's date range ({error}); carrying on")
    try:
        latest = client.latest_handle()
    except (OSError, parse.NotAvailable) as error:
        raise SystemExit(f"couldn't reach WebTrak: {error}")
    if last > latest:
        log("the end is later than WebTrak has data for; stopping at the latest chunk")
        last = latest
    if last < first:
        raise SystemExit("WebTrak holds no data for that period")
    # A little either side too, so events near the ends are matched against all the radar around them.
    lo, hi = max(first - PAD, held_from or 0), min(latest, last + PAD)
    todo = missing(stores, lo, hi)
    downloads = sum(1 for h in todo if cache is None or not cache.has(h))
    log(f"{names(stores)}: {len(todo)} chunks to save, {downloads} to download, about "
        f"{downloads * (client.min_interval + client_mod.TYPICAL_REPLY_S) / 60:.0f} minutes")
    stop = Stop()
    saved, failed = save_range(client, cache, stores, lo, hi, args.quiet, give_up=False, stop=stop)
    if not stop:  # a stopped run leaves its events waiting, for the rerun that carries on
        for monitor, monitor_store in stores:
            rows = monitor_store.finish(parse.utc_for_handle(first), parse.utc_for_handle(last + 1))
            if not args.quiet:
                print_events(rows, monitor)
    log(f"saved {saved} chunks to {os.path.dirname(stores[0][1].dir)}")
    if stop:
        log("stopped early; run the same command again to carry on")
        return 1
    if failed:
        log(f"{failed} chunks failed; run the same command again to fetch just those")
        return 1
    return 0


def cmd_monitors(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="List the site's noise monitors.")
    parser.add_argument("--site", default="lcy")
    args = parser.parse_args(argv)
    out_dir = os.path.join(DEFAULT_OUT, args.site)
    for m in load_monitors(client_mod.Client(site=args.site), args.site, out_dir):
        print(f"{m['id']:>5}  {m['lat']:.5f} {m['lon']:.5f}  {m['name']}  {m.get('status', '')}")
    return 0


def cmd_range(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Show the period WebTrak holds.")
    parser.add_argument("--site", default="lcy")
    args = parser.parse_args(argv)
    c = client_mod.Client(site=args.site)
    first, last = c.date_range()
    latest = c.latest_handle()
    lag = (time.time() - parse.utc_for_handle(latest) - parse.WINDOW_S) / 60
    print(f"from {first} to {last} local time; the newest chunk is {lag:.0f} minutes behind real time")
    return 0


def cmd_serve(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Run the local web app (http://127.0.0.1:PORT).")
    parser.add_argument("--site", default="lcy")
    parser.add_argument("--out", default=DEFAULT_OUT, help="data folder (default tools/webtrak/data)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = parser.parse_args(argv)
    from . import server
    return server.serve(os.path.abspath(args.out), args.site, args.port, open_browser=not args.no_browser)


COMMANDS = {"follow": cmd_follow, "fetch": cmd_fetch, "monitors": cmd_monitors, "range": cmd_range,
            "serve": cmd_serve}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        print(f"unknown command {command!r}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    return COMMANDS[command](rest, prog=f"webtrak {command}")


if __name__ == "__main__":
    sys.exit(main())

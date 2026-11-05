"""Collect noise monitor data from London City Airport's WebTrak.

usage: python3 -m webtrak COMMAND [options]      (from tools/webtrak)

commands:
  monitors   list the site's noise monitors and their ids
  follow     keep collecting as new data appears (about 25 minutes behind real time)
  fetch      download a past period, in local time
  range      show the period WebTrak holds

NMT6, St Pauls Church in Thamesmead, is monitor 106 and is the default.
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

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 and earlier
    ZoneInfo = None

from . import client as client_mod
from . import parse, store

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(HERE, "data")
DEFAULT_MONITOR = "106"
SITE_ZONE = "Europe/London"

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


def find_monitor(client, site, out_dir, monitor_id):
    cache = os.path.join(out_dir, "monitors.json")
    monitors = None
    try:
        monitors = client.monitors()
        os.makedirs(out_dir, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(monitors, f, indent=1)
    except Exception as error:  # the config service is separate from the data; carry on without it
        log(f"couldn't read the monitor list ({error}); using the saved copy")
        try:
            with open(cache) as f:
                monitors = json.load(f)
        except (OSError, ValueError):
            monitors = KNOWN_MONITORS.get(site, [])
    for m in monitors:
        if str(m["id"]) == str(monitor_id):
            return {"id": str(m["id"]), "name": m["name"], "lat": float(m["lat"]), "lon": float(m["lon"])}
    raise SystemExit(f"monitor {monitor_id} isn't in the site's monitor list; try the monitors command")


def local_to_utc(text):
    """'YYYY-MM-DD HH:MM' in airport local time, to UTC seconds."""
    moment = dt.datetime.strptime(text.strip().replace("T", " "), "%Y-%m-%d %H:%M" if text.count(":") == 1
                                  else "%Y-%m-%d %H:%M:%S")
    if ZoneInfo is None:
        raise SystemExit("Python 3.9 or later is needed for local times")
    return moment.replace(tzinfo=ZoneInfo(SITE_ZONE)).timestamp()


def describe(summary, monitor, quiet=False):
    if summary is None or quiet:
        return
    level = (f"LAeq,30s {summary['leq']:5.1f}  max {summary['max']:5.1f} dB" if summary["leq"] is not None
             else "no levels")
    status = "" if summary["radar_status"] in ("online", "") else f"  radar {summary['radar_status']}"
    print(f"{summary['start'][11:19]}  NMT{monitor['id']}  {level}  aircraft nearby {summary['aircraft']}{status}",
          flush=True)
    for e in summary["events"]:
        who = e.get("callsign") or "no aircraft in range"
        extra = ""
        if e.get("callsign"):
            extra = (f" {e.get('type') or '?'} {e.get('direction')}/{e.get('airport') or '-'}"
                     f" at {e['closest_slant_m']} m slant, {e['closest_height_m']:.0f} m up")
        print(f"    EVENT {e['start_local'][11:19]}  LAmax {e['lmax_db']:.1f}  SEL {e['sel_db']:.1f}  "
              f"{e['duration_s']:.0f} s  class {e['event_class']}  -> {who}{extra}", flush=True)


def save_range(client, monitor_store, monitor, first, last, quiet=False):
    """Fetch and save every unsaved handle from first to last. Returns how many were saved."""
    saved = 0
    for a, b in monitor_store.gaps(first, last):
        for handle in range(a, b + 1):
            try:
                text = client.chunk_text(handle)
                chunk = parse.parse_chunk(text, handle)
            except parse.NotAvailable as error:
                log(f"chunk {handle} ({store.iso_utc(parse.utc_for_handle(handle))}) not available: {error}")
                continue
            except OSError as error:
                log(f"chunk {handle} failed: {error}; will retry later")
                return saved
            describe(monitor_store.save(chunk, text), monitor, quiet)
            saved += 1
    return saved


def common_args(parser):
    parser.add_argument("--site", default="lcy", help="WebTrak site name (default lcy)")
    parser.add_argument("--nmt", default=DEFAULT_MONITOR, help="monitor id (default 106, NMT6 St Pauls Thamesmead)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="output folder (default tools/webtrak/data)")
    parser.add_argument("--radius", type=float, default=3000, help="save radar positions within this many metres "
                        "of the monitor (default 3000)")
    parser.add_argument("--keep-raw", action="store_true", help="also save each chunk as received, gzipped")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1, minimum 0.5)")
    parser.add_argument("--quiet", action="store_true", help="don't print each chunk")


def setup(args):
    client = client_mod.Client(site=args.site, min_interval=max(0.5, args.delay))
    out_dir = os.path.join(args.out, args.site)
    monitor = find_monitor(client, args.site, out_dir, args.nmt)
    monitor_store = store.MonitorStore(out_dir, monitor, radius_m=args.radius, keep_raw=args.keep_raw)
    return client, monitor, monitor_store


def cmd_follow(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Keep collecting as new WebTrak data appears.")
    common_args(parser)
    parser.add_argument("--backfill", type=float, default=1.0, help="on a first run, or after a long break, "
                        "go back at most this many hours (default 1)")
    parser.add_argument("--poll", type=float, default=30, help="seconds between checks for new data (default 30)")
    args = parser.parse_args(argv)
    client, monitor, monitor_store = setup(args)
    monitor_store.prime_buffer()
    log(f"following NMT{monitor['id']} {monitor['name']}, saving to {monitor_store.dir}")

    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(now=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    reported_lag = None
    while not stop["now"]:
        try:
            latest = client.latest_handle()
        except (OSError, parse.NotAvailable) as error:
            log(f"couldn't reach WebTrak: {error}")
            latest = None
        if latest is not None:
            earliest = latest - int(args.backfill * 3600 / parse.WINDOW_S) + 1
            first = earliest if monitor_store.last_handle is None else max(earliest, monitor_store.last_handle + 1)
            if monitor_store.last_handle is not None and monitor_store.last_handle + 1 < earliest:
                log(f"gap: {earliest - monitor_store.last_handle - 1} chunks are older than --backfill and are "
                    f"skipped; use fetch to get them")
            save_range(client, monitor_store, monitor, first, latest, args.quiet)
            lag = round((time.time() - parse.utc_for_handle(latest) - parse.WINDOW_S) / 60)
            if reported_lag is None or abs(lag - reported_lag) >= 5:
                log(f"WebTrak is {lag} minutes behind real time")
                reported_lag = lag
        end = time.monotonic() + args.poll
        while not stop["now"] and time.monotonic() < end:
            time.sleep(0.5)
    log("stopped")
    return 0


def cmd_fetch(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Download a past period from WebTrak.")
    common_args(parser)
    parser.add_argument("--from", dest="start", required=True, help="local start, 'YYYY-MM-DD HH:MM'")
    parser.add_argument("--to", dest="end", required=True, help="local end, 'YYYY-MM-DD HH:MM' (not included)")
    args = parser.parse_args(argv)
    start, end = local_to_utc(args.start), local_to_utc(args.end)
    if end <= start:
        raise SystemExit("--to must be after --from")
    client, monitor, monitor_store = setup(args)
    first, last = parse.handle_for_utc(start), parse.handle_for_utc(end - 1)
    latest = client.latest_handle()
    if last > latest:
        log("the end is later than WebTrak has data for; stopping at the latest chunk")
        last = latest
    todo = sum(b - a + 1 for a, b in monitor_store.gaps(first, last))
    log(f"NMT{monitor['id']} {monitor['name']}: {todo} chunks to fetch, about {todo * client.min_interval / 60:.0f} "
        f"minutes or more")
    saved = save_range(client, monitor_store, monitor, first, last, args.quiet)
    log(f"saved {saved} chunks to {monitor_store.dir}")
    return 0


def cmd_monitors(argv, prog):
    parser = argparse.ArgumentParser(prog=prog, description="List the site's noise monitors.")
    parser.add_argument("--site", default="lcy")
    args = parser.parse_args(argv)
    for m in client_mod.Client(site=args.site).monitors():
        print(f"{m['id']:>5}  {m['lat']:.5f} {m['lon']:.5f}  {m['name']}  {m['status']}")
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


COMMANDS = {"follow": cmd_follow, "fetch": cmd_fetch, "monitors": cmd_monitors, "range": cmd_range}


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

#!/usr/bin/env python3
"""Make a simulated day of logger output, with the answers, so the analysis and viewer can be tested.

  python3 -m adsb simulate demo  [--out data/demo] [--seed 1]    logs, weather, truth, results and viewer
  python3 -m adsb simulate logs  --out DIR [--seed 1]             logs, weather and truth only
  python3 -m adsb simulate serve [--port 30154] [--speed 10]      replay as a fake readsb, to test the logger

All of it is invented. The garden is placed at the example config's location, 500 m north of a
straight RWY 27 centreline and 4 km from the threshold, as the measurement plan assumes; nothing
here comes from real flights or the real garden. Arrivals use RWY 27 in the morning, then the
wind changes and RWY 09 is used.

Built in, so the analysis has something to find: a fleet whose aircraft fly several times a day, an
aircraft with no geometric altitude, one sending sea-level height as geometric, a reception gap
near the garden, QNH changing through the day, a helicopter, high overflights, an unreadable line,
and a power cut that damages a log file and leaves the clock briefly unsynchronised.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import math
import os
import random
import shutil
import socket
import sys
import time

from . import analyse
from .common import FEET, format_utc
from .geometry import Site
from .logger import HourlyWriter

SITE = {"lat": 51.5, "lon": 0.1, "ground_elevation_m": 3.0, "mic_height_m": 3.0}
GEOID_M = 45.0
RUNWAY_ELEVATION_M = 20 * FEET
OFFSET_M = 500.0  # Garden north of the RWY 27 centreline
THRESHOLD_DISTANCE_M = 4000.0  # From the RWY 27 threshold to the point abeam the garden
RUNWAY_LENGTH_M = 1508.0
OUTWARD_BEARING = 93.0  # From the RWY 27 threshold out to the east, over Thamesmead
LOGGER_RADIUS_KM = 30.0
FLUSH_SECONDS = 30.0

# Type: (approach angle, threshold crossing height in ft, approach speed in kt)
FLEET_TYPES = {
    "E190": (5.5, 35, 135),
    "E290": (5.5, 35, 130),
    "E295": (5.5, 35, 132),
    "BCS1": (5.5, 35, 125),
    "A20N": (4.49, 50, 133),
}
FLEET = ["E190"] * 18 + ["E290"] * 4 + ["E295"] * 4 + ["BCS1"] * 6 + ["A20N"] * 6

DAY = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc).timestamp()
DEFAULT_TIMES = {
    "start": DAY + 6.5 * 3600,
    "runway_change": DAY + 13.25 * 3600,
    "end": DAY + 21.5 * 3600,
    "power_cut": DAY + 12 * 3600 + 610,
    "power_cut_seconds": 240.0,
    "clock_sync_seconds": 90.0,
}


def unit(bearing):
    r = math.radians(bearing)
    return math.sin(r), math.cos(r)


U = unit(OUTWARD_BEARING)
N = (-U[1], U[0])  # Left of outward, which is roughly north


def along(d, lateral=0.0):
    """Ground position at distance d east of the RWY 27 threshold, lateral metres north of the line."""
    tx = -OFFSET_M * N[0] - THRESHOLD_DISTANCE_M * U[0]
    ty = -OFFSET_M * N[1] - THRESHOLD_DISTANCE_M * U[1]
    return tx + d * U[0] + lateral * N[0], ty + d * U[1] + lateral * N[1]


def qnh_at(t):
    return 1016 + 4 * math.sin(2 * math.pi * (t - DAY) / 86400 * 1.3)


def temp_at(t):
    """A cold November day, about 11 °C below the standard atmosphere, so temperature matters."""
    return 4 + 3 * math.sin(2 * math.pi * ((t - DAY) / 86400 - 0.375))


GRAVITY = 9.80665
GAS_CONSTANT = 287.053
LAPSE = 0.0065
POSITION_NOISE_M = 8.0  # Typical of good ADS-B positions


def pressure_altitude_ft(height_m, qnh, temp_c=15.0):
    """What the aircraft's altimeter reports at a true height, in an atmosphere with this sea-level
    temperature and the standard lapse rate. Worked out from the pressure, independently of the
    analysis's correction, so the tests check that correction rather than repeat it."""
    pressure = qnh * (1 - LAPSE * height_m / (temp_c + 273.15)) ** (GRAVITY / (GAS_CONSTANT * LAPSE))
    return 145366.45 * (1 - (pressure / 1013.25) ** 0.190284)


class Flight:
    def __init__(self, code, callsign, kind, aircraft_type, t0, t1, path, quirk="", angle=None):
        self.code, self.callsign, self.kind, self.type = code, callsign, kind, aircraft_type
        self.t0, self.t1, self.path, self.quirk, self.angle = t0, t1, path, quirk, angle
        self.registration = None
        self.sends_qnh = False


def arrival_27(t_land, aircraft_type, rng):
    angle, tch_ft, speed_kt = FLEET_TYPES[aircraft_type]
    angle = rng.gauss(angle, 0.04)
    speed = rng.gauss(speed_kt, 4) * 0.514444
    lateral = rng.gauss(0, 40)
    cap = 3000 * FEET

    def path(t):
        d = max(0.0, (t_land - t) * speed)
        x, y = along(d, lateral)
        return x, y, min(cap, RUNWAY_ELEVATION_M + tch_ft * FEET + d * math.tan(math.radians(angle)))

    return angle, t_land - 34000 / speed, t_land, path


def departure_09(t_lift, rng):
    climb = rng.uniform(6.0, 9.0)
    speed = rng.uniform(150, 175) * 0.514444
    lateral0 = rng.gauss(0, 60)
    cap = 4000 * FEET

    def path(t):
        d = -500 + max(0.0, t - t_lift) * speed
        lateral = lateral0 + max(0.0, d - 2500) * math.tan(math.radians(12))
        x, y = along(d, lateral)
        return x, y, min(cap, RUNWAY_ELEVATION_M + 10 + (d + 500) * math.tan(math.radians(climb)))

    return climb, t_lift, t_lift + 30000 / speed, path


def departure_27(t_lift, rng):
    climb = rng.uniform(6.0, 9.0)
    speed = rng.uniform(150, 175) * 0.514444

    def path(t):
        d = -RUNWAY_LENGTH_M + 500 - max(0.0, t - t_lift) * speed
        x, y = along(d)
        return x, y, min(4000 * FEET, RUNWAY_ELEVATION_M + 10 + (-RUNWAY_LENGTH_M + 500 - d) * math.tan(math.radians(climb)))

    return climb, t_lift, t_lift + 26000 / speed, path


def arrival_09(t_land, aircraft_type, rng):
    angle, tch_ft, speed_kt = FLEET_TYPES[aircraft_type]
    speed = rng.gauss(speed_kt, 4) * 0.514444

    def path(t):
        before = max(0.0, (t_land - t) * speed)
        x, y = along(-RUNWAY_LENGTH_M - before)
        return x, y, min(2000 * FEET, RUNWAY_ELEVATION_M + tch_ft * FEET + before * math.tan(math.radians(angle)))

    return angle, t_land - 26000 / speed, t_land, path


def straight(t0, duration, start, heading, speed, height):
    ux, uy = unit(heading)

    def path(t):
        s = (t - t0) * speed
        return start[0] + s * ux, start[1] + s * uy, height

    return t0, t0 + duration, path


def build_flights(rng, times):
    hexes = [0x400000 + rng.randrange(0x40000) for _ in FLEET]
    fleet = [(f"{code:06x}", kind, f"SIM-{n:03d}") for n, (code, kind) in enumerate(zip(hexes, FLEET), 1)]
    busy_until = {code: 0.0 for code, _, _ in fleet}
    flights = []
    number = 100

    def next_aircraft(t, prefer=None):
        # Aircraft turn round on the ground for at least 30 minutes, so one hex never flies two flights at once.
        free = [a for a in fleet if busy_until[a[0]] < t - 1800]
        if prefer:
            preferred = [a for a in free if a[1] == prefer]
            free = preferred or free
        if not free:
            raise RuntimeError("simulated fleet too small for the schedule")
        return rng.choice(free)

    t = times["start"]
    arrivals_27 = 0
    while t < times["end"]:
        code, kind, reg = next_aircraft(t, "A20N" if rng.random() < 0.12 else None)
        number += 1
        callsign = f"SIM{number}"
        if t < times["runway_change"]:
            angle, t0, t1, path = arrival_27(t, kind, rng)
            flight = Flight(code, callsign, "rwy27_arrival", kind, t0, t1, path, angle=angle)
            # Some arrivals have quirks for the analysis to cope with, chosen by order.
            flight.quirk = {2: "no_geometric", 4: "geometric_is_sea_level", 6: "gap_near_garden"}.get(arrivals_27, "")
            arrivals_27 += 1
        else:
            angle, t0, t1, path = arrival_09(t, kind, rng)
            flight = Flight(code, callsign, "rwy09_arrival", kind, t0, t1, path, angle=angle)
        flight.registration = reg
        flight.sends_qnh = rng.random() < 0.5
        flights.append(flight)
        busy_until[code] = t + 2400

        lift = t + rng.uniform(150, 250)
        code, kind, reg = next_aircraft(lift)
        number += 1
        if lift < times["runway_change"]:
            climb, t0, t1, path = departure_27(lift, rng)
            flight = Flight(code, f"SIM{number}", "rwy27_departure", kind, t0, t1, path, angle=climb)
        else:
            climb, t0, t1, path = departure_09(lift, rng)
            flight = Flight(code, f"SIM{number}", "rwy09_departure", kind, t0, t1, path, angle=climb)
        flight.registration = reg
        flights.append(flight)
        busy_until[code] = lift + 2400
        t += rng.uniform(300, 540)

    t = times["start"] - 600
    while t < times["end"]:
        code = f"{0x300000 + rng.randrange(0x100000):06x}"
        if rng.random() < 0.1:
            code = "~" + code  # A non-ICAO address, as from TIS-B
        heading = rng.uniform(0, 360)
        hx, hy = unit(heading)
        middle = (rng.uniform(-12000, 12000), rng.uniform(-12000, 12000))
        start = (middle[0] - 25000 * hx, middle[1] - 25000 * hy)
        height = rng.choice([rng.uniform(1800, 3200), rng.uniform(3600, 11000)])
        t0, t1, path = straight(t, 50000 / 130, start, heading, 130, height)
        flights.append(Flight(code, f"OVR{rng.randrange(1000, 9999)}", "overflight", "A320", t0, t1, path))
        t += rng.uniform(240, 600)

    for fraction in (0.25, 0.7):
        t0, t1, path = straight(times["start"] + fraction * (times["end"] - times["start"]), 240, (-6000, 300), 90, 50, 300)
        flights.append(Flight("43ea01", "SIMHELI", "helicopter", "EC35", t0, t1, path))
    return flights


def true_closest(flight, site_mic_amsl):
    """Closest ground and slant points, found by fine sampling of the true path."""
    best_ground = best_slant = None
    steps = int((flight.t1 - flight.t0) / 0.1)
    for i in range(steps + 1):
        t = flight.t0 + i * 0.1
        x, y, h = flight.path(t)
        ground = math.hypot(x, y)
        slant = math.hypot(ground, h - site_mic_amsl)
        if best_ground is None or ground < best_ground[0]:
            best_ground = (ground, t, h, y)
        if best_slant is None or slant < best_slant[0]:
            best_slant = (slant, t)
    return best_ground, best_slant


def make_records(flights, rng, site):
    records = []
    for flight in flights:
        if flight.quirk == "gap_near_garden":
            (_, gap_centre, _, _), _ = true_closest(flight, site.mic_amsl)
        steps = int((flight.t1 - flight.t0) / 0.5)
        for i in range(steps + 1):
            t = flight.t0 + i * 0.5 + rng.uniform(0, 0.05)
            x, y, h = flight.path(t)
            distance = math.hypot(x, y)
            if distance > LOGGER_RADIUS_KM * 1000:
                continue
            if rng.random() < (0.5 if distance > 25000 else 0.2):
                continue
            if flight.quirk == "gap_near_garden" and abs(t - gap_centre) < 12:
                continue
            x1, y1, h1 = flight.path(t + 0.5)
            x0, y0, h0 = flight.path(t - 0.5)
            qnh = qnh_at(t)
            seen = round(rng.uniform(0, 0.2), 3)
            x += rng.gauss(0, POSITION_NOISE_M)
            y += rng.gauss(0, POSITION_NOISE_M)
            lat = site.lat + math.degrees(y / site.metres_per_rad_north)
            lon = site.lon + math.degrees(x / site.metres_per_rad_east)
            record = {
                "now": round(t + seen, 3), "hex": flight.code,
                "type": "tisb_other" if flight.code.startswith("~") else "adsb_icao",
                "flight": f"{flight.callsign:<8}",
            }
            if flight.registration:
                record.update(r=flight.registration, t=flight.type, dbFlags=0)
            record["alt_baro"] = 25 * round(pressure_altitude_ft(h, qnh, temp_at(t)) / 25)
            if flight.quirk != "no_geometric":
                geom = h if flight.quirk == "geometric_is_sea_level" else h + GEOID_M
                record["alt_geom"] = 25 * round(geom / FEET / 25)
            record.update(
                gs=round(math.hypot(x1 - x0, y1 - y0) / 0.514444, 1),
                track=round(math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360, 2),
                baro_rate=64 * round((h1 - h0) / FEET * 60 / 64),
            )
            if flight.sends_qnh:
                record["nav_qnh"] = float(round(qnh))
            record.update(
                category="A7" if flight.kind == "helicopter" else "A3",
                lat=round(lat, 6), lon=round(lon, 6), nic=5 if rng.random() < 0.03 else 8, rc=186, seen_pos=seen,
                messages=1000 + i, seen=0.0, rssi=round(-30 + 25 * math.exp(-distance / 8000), 1),
            )
            records.append(record)
        if flight.kind.endswith("arrival"):
            x, y, _ = flight.path(flight.t1)
            for k in range(1, 4):
                records.append({
                    "now": round(flight.t1 + k, 3), "hex": flight.code, "type": "adsb_icao",
                    "flight": f"{flight.callsign:<8}", "alt_baro": "ground",
                    "lat": round(site.lat + math.degrees(y / site.metres_per_rad_north), 6),
                    "lon": round(site.lon + math.degrees(x / site.metres_per_rad_east), 6),
                    "nic": 8, "rc": 186, "seen_pos": 0.0,
                })
    records.sort(key=lambda r: r["now"])
    return records


def readsb_line(record):
    """Format as readsb does, with its spaced `"now" :` key."""
    return json.dumps(record, separators=(",", ":")).replace('{"now":', '{"now" : ', 1).encode()


def power_cut(writer):
    """Lose everything written since the last flush, leaving the file without its gzip ending."""
    if writer.hour is None:
        return
    path, kept = writer.path, writer.flushed_bytes
    writer.close()
    os.truncate(path, kept)


def write_logs(records, out_dir, times):
    """Write the records with the logger's own file writer, driven by simulated time."""
    clock = {"t": records[0]["now"] if records else 0.0}
    writer = HourlyWriter(
        os.path.join(out_dir, "logs", "adsb"), FLUSH_SECONDS, now=lambda: clock["t"], monotonic=lambda: clock["t"]
    )
    cut, back = times["power_cut"], times["power_cut"] + times["power_cut_seconds"]
    cut_done = False
    written = 0
    for n, record in enumerate(records):
        t = clock["t"] = record["now"]
        if not cut_done and t >= cut:
            power_cut(writer)
            cut_done = True
        if cut <= t < back:
            continue
        writer.write(readsb_line(record) + b"\n")
        writer.tick()
        written += 1
        if n == len(records) // 3:
            writer.write(b'{"now" : 17930\n')  # A line cut short, as after a dropped connection
    writer.close()
    return written


def write_health(records, out_dir, times):
    folder = os.path.join(out_dir, "logs", "health")
    os.makedirs(folder, exist_ok=True)
    cut, back = times["power_cut"], times["power_cut"] + times["power_cut_seconds"]
    synced_from = back + times["clock_sync_seconds"]
    # The same events, in the same order, as the logger writes after starting and checking its clock.
    entries = [
        (times["start"] - 900, "clock_synchronised"), (times["start"] - 900, "start"), (times["start"] - 899, "connected"),
        (back, "clock_not_synchronised"), (back, "start"), (back + 1, "connected"), (synced_from, "clock_synchronised"),
    ]
    t = times["start"] - 600
    while t < times["end"] + 900:
        if not cut <= t < back:
            entries.append((t, None))
        t += 300
    stamps = [r["now"] for r in records]
    lines = []
    previous = None
    for t, event in sorted(entries, key=lambda e: e[0]):
        count = bisect.bisect_left(stamps, t) - (bisect.bisect_left(stamps, previous) if previous else 0)
        previous = t
        synced = not (back <= t < synced_from)
        lines.append(json.dumps({
            "time": t, "event": event, "connected": True, "lines": count, "written": count, "far": 0,
            "invalid": 0, "no_position": 0, "dropped_disk_full": 0, "dropped_write_error": 0,
            "aircraft": None, "disconnects": 0,
            "newest_message_age_s": 0.5,
            "clock": {"synchronised": synced, "reference": "GPS" if synced else "", "offset_s": 0.0002 if synced else 3.1},
            "cpu_temp_c": 48.0, "throttled": "throttled=0x0", "uptime_s": t - back if t >= back else t - times["start"] + 900,
            "disk_free_gb": 230.0, "simulated": True,
        }))
    day = dt.datetime.fromtimestamp(times["start"], dt.timezone.utc).strftime("%Y-%m-%d")
    with open(os.path.join(folder, f"{day}.jsonl"), "w") as f:
        f.write("\n".join(lines) + "\n")


def metar_temp(value):
    rounded = round(value)
    return f"M{abs(rounded):02d}" if rounded < 0 else f"{rounded:02d}"


def write_weather(path, times):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["station", "valid", "metar"])
        t = math.floor((times["start"] - 3600) / 1800) * 1800 + 1200
        while t < times["end"] + 3600:
            moment = dt.datetime.fromtimestamp(t, dt.timezone.utc)
            temp = temp_at(t)
            metar = (
                f"EGLC {moment:%d%H%M}Z AUTO 25008KT 9999 FEW030 {metar_temp(temp)}/{metar_temp(temp - 4)} "
                f"Q{math.floor(qnh_at(t)):04d}"  # METARs round QNH down
            )
            writer.writerow(["EGLC", f"{moment:%Y-%m-%d %H:%M}", metar])
            t += 1800


TRUTH_COLUMNS = [
    "hex", "callsign", "type", "kind", "quirk", "start_utc", "true_lateral_m", "true_garden_side",
    "true_height_at_closest_ground_amsl_m", "true_closest_ground_time", "true_closest_slant_m",
    "true_path_angle_deg", "during_power_cut",
]


def write_truth(path, flights, site, times):
    rows = []
    cut0, cut1 = times["power_cut"] - FLUSH_SECONDS - 60, times["power_cut"] + times["power_cut_seconds"] + times["clock_sync_seconds"] + 60
    for flight in flights:
        (ground, ground_t, height, y), (slant, _) = true_closest(flight, site.mic_amsl)
        rows.append({
            "hex": flight.code, "callsign": flight.callsign, "type": flight.type, "kind": flight.kind,
            "quirk": flight.quirk, "start_utc": format_utc(flight.t0), "true_lateral_m": round(ground, 2),
            "true_garden_side": "north" if y < 0 else "south",
            "true_height_at_closest_ground_amsl_m": round(height, 2), "true_closest_ground_time": round(ground_t, 2),
            "true_closest_slant_m": round(slant, 2),
            "true_path_angle_deg": "" if flight.angle is None else round(flight.angle, 3),
            "during_power_cut": int(flight.t1 >= cut0 and flight.t0 <= cut1),
        })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, TRUTH_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def site_config():
    return {"site": dict(SITE), "geoid_height_m": GEOID_M, "simulated": True}


MARKER = "SIMULATED.txt"


def prepare_folder(out_dir):
    """Clear an earlier simulation's output, but never touch a folder this script didn't make."""
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        if not os.path.exists(os.path.join(out_dir, MARKER)):
            raise SystemExit(f"{out_dir} isn't empty and wasn't made by this simulator, so it's left alone.")
        for name in ("logs", "results"):
            shutil.rmtree(os.path.join(out_dir, name), ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, MARKER), "w") as f:
        f.write("Made by the ADS-B simulator (python3 -m adsb simulate). Everything in this folder is invented.\n")


def simulate(out_dir, seed=1, times=None):
    """Write logs/, eglc_metars.csv, truth.csv and site.json into out_dir. Returns the truth rows."""
    times = {**DEFAULT_TIMES, **(times or {})}
    prepare_folder(out_dir)
    rng = random.Random(seed)
    config = site_config()
    site = Site(config)
    flights = build_flights(rng, times)
    records = make_records(flights, rng, site)
    write_logs(records, out_dir, times)
    write_health(records, out_dir, times)
    write_weather(os.path.join(out_dir, "eglc_metars.csv"), times)
    with open(os.path.join(out_dir, "site.json"), "w") as f:
        json.dump(config, f, indent=2)
    return write_truth(os.path.join(out_dir, "truth.csv"), flights, site, times)


def serve(port, speed, seed):
    """Act as readsb's JSON port, replaying a simulated day faster than real time."""
    rng = random.Random(seed)
    site = Site(site_config())
    records = make_records(build_flights(rng, DEFAULT_TIMES), rng, site)
    server = socket.create_server(("127.0.0.1", port))
    print(f"Simulated readsb on port {port}, {len(records)} lines at {speed}x. Ctrl-C to stop.", flush=True)
    while True:
        connection, _ = server.accept()
        print("Logger connected", flush=True)
        start_wall, start_sim = time.monotonic(), records[0]["now"]
        try:
            for record in records:
                wait = (record["now"] - start_sim) / speed - (time.monotonic() - start_wall)
                if wait > 0:
                    time.sleep(wait)
                connection.sendall(readsb_line(record) + b"\n")
        except OSError:
            print("Logger disconnected", flush=True)
        finally:
            connection.close()


TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tools/adsb


def main(argv=None, prog=None):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "logs"):
        p = sub.add_parser(name)
        p.add_argument("--out", default=os.path.join(TOOL_DIR, "data", "demo"))
        p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=30154)
    p.add_argument("--speed", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == "serve":
        serve(args.port, args.speed, args.seed)
        return 0
    truth = simulate(args.out, args.seed)
    print(f"Simulated {len(truth)} flights into {args.out}")
    if args.command == "demo":
        with open(os.path.join(args.out, "site.json")) as f:
            config = json.load(f)
        results = os.path.join(args.out, "results")
        _, summary = analyse.run(config, os.path.join(args.out, "logs"), results, os.path.join(args.out, "eglc_metars.csv"))
        print(summary, end="")
        print(f"Open {os.path.join(results, 'viewer.html')} in a browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

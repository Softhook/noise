"""The fleet table: each airframe's type, as its country's official register gives it.

    python3 -m survey fleet                  check every registration the builds saw near a receptor
    python3 -m survey fleet G-LCYN HB-AZH    check these
    python3 -m survey fleet --dry-run        list what would be asked, and ask nothing

registry/fleet.csv is kept in git, one row per airframe. An airframe's type doesn't change, so a
registration is asked about once, and asked again only with --recheck. The build's resolve step
then gives every pass of that airframe its type from here (resolve.py).

Which registrations: those of flights in the built deployments (`make build` first) that came
within --km of a receptor and below --ft, as the survey app's passes table starts with, so
the list is the aircraft the survey is about rather than every one in a source's area.

A row's register says where it came from: a code from registers.py (uk, ch), or `manual`, for an
entry a person checked by hand (a register that can't be asked online, such as Germany's), which
is never overwritten. A registration its register doesn't have gets a row with status `not found`,
so it isn't asked again; resolve ignores those rows.
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
import tempfile

from . import manifest, registers, schema
from .common import number, registration

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET_PATH = os.path.join(HERE, "registry", "fleet.csv")
DEPLOYMENTS = os.path.join(os.path.dirname(HERE), "deployments")

FIELDS = ["registration", "mark", "status", "icao_type", "model", "marketing_name", "manufacturer",
          "serial_number", "year_built", "icao24", "engines", "mtow_kg", "noise_standard",
          "approach_epndb", "lateral_epndb", "flyover_epndb", "register", "register_ref", "checked_utc", "note"]
MANUAL = "manual"
NOT_FOUND = "not found"
# The survey app's passes table starts at 3 km and 3,000 ft
DEFAULT_KM = 3.0
DEFAULT_FT = 3000.0
FT_M = 0.3048


def read(path=None):
    """{registration: row}, or {} if there's no table yet. path: FLEET_PATH if None."""
    path = path or FLEET_PATH
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {row["registration"]: row for row in csv.DictReader(f) if row.get("registration")}


def write(entries, path=None):
    """Write the table, by registration, in one step so a reader never sees half of it."""
    path = path or FLEET_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".fleet.", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", newline="") as f:
            w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
            w.writeheader()
            for reg in sorted(entries):
                w.writerow({k: "" if v is None else v for k, v in entries[reg].items()})
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def known_type(entry):
    """The type an entry settles, or "" if it doesn't settle one (not found, or no type given)."""
    if not entry or entry.get("status") == NOT_FOUND:
        return ""
    return entry.get("icao_type") or ""


def seen(manifests, km=DEFAULT_KM, ft=DEFAULT_FT):
    """{registration: number of flights} for flights in the built deployments that came within km
    of a receptor and below ft. A deployment that isn't built is skipped, with a note."""
    counts, notes = {}, []
    for path in manifests:
        m = manifest.load(path)
        folder = os.path.join(m["out_dir"], "common")
        if not os.path.exists(os.path.join(folder, "flights.csv")):
            notes.append(f"{m['deployment']} isn't built, so it's left out (make build)")
            continue
        near = set()
        for a in schema.read_rows(folder, "approaches"):
            ground, height = number(a["ground_m"]), number(a["height_m"])
            if ground is not None and ground <= km * 1000 and (height is None or height <= ft * FT_M):
                near.add((a["source"], a["source_id"]))
        for f in schema.read_rows(folder, "flights"):
            if f["registration"] and (f["source"], f["source_id"]) in near:
                counts[f["registration"]] = counts.get(f["registration"], 0) + 1
    return counts, notes


def to_check(regs, entries, recheck=False):
    """(ask, no_register): the registrations to ask their register about, and those no register
    in registers.REGISTERS covers and that aren't in the table yet. A manual entry is never asked
    about; any other is asked about again only with recheck."""
    ask, no_register = [], []
    for reg in sorted(regs):
        entry = entries.get(reg)
        if entry and (entry.get("register") == MANUAL or not recheck):
            continue
        (ask if registers.nationality(reg) else no_register).append(reg)
    return ask, no_register


def check(regs, entries, http=None, log=sys.stderr):
    """Ask each registration's register, and put the answers in entries. Returns the registrations
    that couldn't be asked (LookupFailed), which keep any entry they had."""
    http = http or registers.Http()
    failed = []
    for reg in regs:
        try:
            got = registers.look_up(reg, http)
        except registers.LookupFailed as error:
            failed.append(reg)
            print(f"{reg}: couldn't ask its register: {error}", file=log)
            continue
        if got is None:
            code, name, _ = registers.REGISTERS[registers.nationality(reg)]
            got = {"registration": reg, "status": NOT_FOUND, "register": code,
                   "checked_utc": registers.today(), "note": f"not on the {name} register"}
            print(f"{reg}: not on the register", file=log)
        else:
            print(f"{got['mark']}: {got['icao_type'] or 'no type'}  {got['model']}  ({got['status']})", file=log)
        entries[reg] = got
    return failed


def main(args):
    args.fleet = args.fleet or FLEET_PATH
    entries = read(args.fleet)
    notes = []
    if args.registrations:
        regs = {registration(r): 1 for r in args.registrations}
    else:
        regs, notes = seen(args.manifest or sorted(glob.glob(os.path.join(DEPLOYMENTS, "*.json"))), args.km, args.ft)
    for note in notes:
        print(note, file=sys.stderr)
    ask, no_register = to_check(regs, entries, args.recheck)
    print(f"{len(regs)} registrations, {len(ask)} to ask a register about, "
          f"{len(regs) - len(ask) - len(no_register)} already in {os.path.relpath(args.fleet)}", file=sys.stderr)
    if no_register:
        print(f"No register we can ask online for these {len(no_register)}; check them by hand and add them "
              f"as `{MANUAL}`:\n  " + " ".join(no_register), file=sys.stderr)
    if args.dry_run:
        for reg in ask:
            print(f"would ask: {reg}")
        return 0
    failed = []
    try:
        failed = check(ask, entries)
    finally:
        write(entries, args.fleet)  # Keep what was found, even if stopped part-way
    print(f"-> {os.path.relpath(args.fleet)}", file=sys.stderr)
    return 1 if failed else 0


def add_arguments(p):
    p.add_argument("registrations", nargs="*", help="registrations to check (default: those the builds saw)")
    p.add_argument("--manifest", action="append", help="only these deployments' builds (default: every one)")
    p.add_argument("--km", type=float, default=DEFAULT_KM, help=f"within this of a receptor (default {DEFAULT_KM:g})")
    p.add_argument("--ft", type=float, default=DEFAULT_FT, help=f"and below this height (default {DEFAULT_FT:g})")
    p.add_argument("--recheck", action="store_true", help="ask again about ones already in the table (except manual ones)")
    p.add_argument("--dry-run", action="store_true", help="list what would be asked, and ask nothing")
    p.add_argument("--fleet", default=None, help=argparse.SUPPRESS)

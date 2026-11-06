"""python -m opensky COMMAND ..."""

from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")  # urllib3 on macOS's LibreSSL Python

from . import aircraft, compare, logs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="opensky", description="Aircraft near NMT6 from OpenSky's Trino database.")
    commands = parser.add_subparsers(dest="command", required=True)
    compare.add_arguments(commands.add_parser("compare", help=compare.__doc__.split("\n")[0]))
    logs.add_arguments(commands.add_parser("logs", help=logs.__doc__.split("\n")[0]))
    aircraft.add_arguments(commands.add_parser("aircraft", help=aircraft.__doc__.split("\n")[0]))
    args = parser.parse_args(argv)
    if args.command == "compare":
        compare.run(args)
    elif args.command == "logs":
        logs.run(args)
    elif args.command == "aircraft":
        aircraft.run(args)


if __name__ == "__main__":
    main()

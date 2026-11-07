"""noise COMMAND ...   (or python -m survey COMMAND, from anywhere once installed: make setup)

commands:
  build    build deployments: analyse what's out of date, then write the common tables
  serve    the survey app: every source's tracks and noise, by day, at http://127.0.0.1:8766
  fleet    look up aircraft types in the official registers, into registry/fleet.csv
  sql      query a built deployment's tables with SQL, in DuckDB
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="survey", description="Join the survey's sources through common tables.")
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build", help="build deployments: analyse what's out of date, then write the common tables")
    b.add_argument("deployments", nargs="*", metavar="DEPLOYMENT",
                   help="a deployment's name (in tools/survey/deployments) or a manifest's path; default every one")
    s = commands.add_parser("serve", help="the survey app (this computer only)")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--no-browser", action="store_true", help="don't open a browser")
    from . import fleet
    fleet.add_arguments(commands.add_parser("fleet", help="look up aircraft types in the official registers"))
    from . import sql
    sql.add_arguments(commands.add_parser("sql", help="query a built deployment's tables with SQL (DuckDB)"))
    args = parser.parse_args(argv)
    if args.command == "build":
        from . import build, manifest
        try:
            return build.main(args)
        except manifest.ManifestError as error:
            print(f"noise build: {error}", file=sys.stderr)
            return 2
    if args.command == "fleet":
        return fleet.main(args)
    if args.command == "sql":
        from . import manifest
        try:
            return sql.main(args)
        except manifest.ManifestError as error:
            print(f"noise sql: {error}", file=sys.stderr)
            return 2
    from . import server
    return server.main(args)


if __name__ == "__main__":
    sys.exit(main())

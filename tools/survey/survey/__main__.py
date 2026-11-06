"""python3 -m survey COMMAND ...   (from tools/survey)

commands:
  build    run a deployment's adapters and write its common tables
  serve    the survey app: every source's tracks and noise, by day, at http://127.0.0.1:8766
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="survey", description="Join the survey's sources through common tables.")
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build", help="run a deployment's adapters and write its common tables")
    b.add_argument("--manifest", required=True, help="a manifest in tools/deployments")
    s = commands.add_parser("serve", help="the survey app (this computer only)")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--no-browser", action="store_true", help="don't open a browser")
    args = parser.parse_args(argv)
    if args.command == "build":
        from . import build
        return build.main(args)
    from . import server
    return server.main(args)


if __name__ == "__main__":
    sys.exit(main())

"""noise COMMAND ...   the survey's tools, from anywhere (install with `make setup`)

The survey:
  build [DEPLOYMENT ...]   analyse whatever is out of date, then build the common tables
                           (every deployment in tools/survey/deployments if none is named)
  serve                    the survey app, at http://127.0.0.1:8766
  fleet                    look up aircraft types in the official registers (online)
  sql DEPLOYMENT [QUERY]   query a built deployment's tables with SQL (DuckDB); a prompt without a query

Each tool's own commands (noise TOOL --help for its list):
  adsb       the garden's ADS-B logger, analysis, METARs, adsb.lol traces, simulator
  opensky    OpenSky's research database: logs for a period, comparison with WebTrak
  webtrak    London City's WebTrak: fetch, follow, quality check, its download app
  fusion     look inside Fusion session folders, read-only

Data goes in data/ at the top of the repository, or wherever NOISE_DATA says: raw/ for what was
collected or downloaded, derived/ for what is worked out from it (see tools/survey/README.md).

This only dispatches: each tool stays its own package, and is imported only when it's asked for.
"""

from __future__ import annotations

import importlib
import os
import sys

# The repository: the tools find data/, the deployments and the fleet table from where their code is
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def installed_in_place():
    """True if this is the editable install (make setup): the code is still in the repository."""
    return (os.path.exists(os.path.join(REPO, "pyproject.toml"))
            and os.path.isdir(os.path.join(REPO, "tools", "survey", "deployments")))

TOOLS = {"adsb": "adsb.__main__", "opensky": "opensky.__main__", "webtrak": "webtrak.__main__",
         "survey": "survey.__main__", "fusion": "fusion.inspector"}
SURVEY_COMMANDS = ("build", "serve", "fleet", "sql")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if not installed_in_place():
        print("noise: this copy isn't in the repository, so it can't find data/ or the deployments.\n"
              "Install it with make setup (an editable install) instead.", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    if command in SURVEY_COMMANDS:
        tool, rest = "survey", argv
    elif command in TOOLS:
        tool = command
    else:
        print(f"unknown command {command!r}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    return importlib.import_module(TOOLS[tool]).main(rest) or 0

"""ADS-B tools for the Thamesmead noise survey.

usage: python3 -m adsb COMMAND [options]      (from tools/adsb, or with it on PYTHONPATH)

commands:
  log        save readsb's stream and the health log (runs on the Pi)
  status     check the logger on a site visit (runs on the Pi)
  analyse    turn logs into flights, a summary and a viewer (runs on a laptop)
  simulate   make a simulated day, or replay one as a fake readsb
  traces     turn readsb track files, such as adsb.lol's archive, into log files
  metars     download METARs for a period, for analyse --weather

Run python3 -m adsb COMMAND --help for each command's options.
"""

from __future__ import annotations

import importlib
import sys

# Imported only when used, so the logger on the Pi never loads the analysis code.
COMMANDS = {
    "log": "adsb.logger",
    "status": "adsb.status",
    "analyse": "adsb.analyse",
    "simulate": "adsb.simulate",
    "traces": "adsb.traces",
    "metars": "adsb.metars",
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        print(f"unknown command {command!r}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    return importlib.import_module(COMMANDS[command]).main(rest, prog=f"adsb {command}")


if __name__ == "__main__":
    sys.exit(main())

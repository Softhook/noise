"""Where the survey's code, deployments, fleet table and data are. Every other module asks here.

Every tool's data lives in one local folder outside the tools: the repository's data/
(git-ignored), or wherever NOISE_DATA says. raw/ holds what was collected or downloaded, written
once; derived/ what is worked out from it, which can be deleted and rebuilt. A deployment's build
goes in derived/deployments/<name>/. A manifest's data paths are relative to DATA_DIR.

These are found from where this file is, which is why `noise` only runs from the editable install.
Other modules read them as paths.NAME when they use them, never import them by value, so a test can
patch them. OUT_DIR is worked out from DATA_DIR once, here, so a test that moves the data patches both.
"""

from __future__ import annotations

import os

SURVEY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tools/survey
TOOLS_DIR = os.path.dirname(SURVEY_DIR)  # tools/
DEPLOYMENTS_DIR = os.path.join(SURVEY_DIR, "deployments")
FLEET_PATH = os.path.join(SURVEY_DIR, "registry", "fleet.csv")
ADSB_TOOL = os.path.join(TOOLS_DIR, "adsb")  # Run as `python -m adsb` by the ADS-B adapter, never imported

DATA_DIR = os.path.abspath(os.environ.get("NOISE_DATA") or os.path.join(os.path.dirname(TOOLS_DIR), "data"))
OUT_DIR = os.path.join(DATA_DIR, "derived", "deployments")

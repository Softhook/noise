"""NMT6, the tool's paths, and small helpers for times and numbers."""

from __future__ import annotations

import datetime as dt
import math
import os

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Every tool's data lives in one local folder, the repository's data/ (or NOISE_DATA): what was
# downloaded in raw/, what is worked out from it in derived/
DATA_DIR = os.path.abspath(os.environ.get("NOISE_DATA")
                           or os.path.join(os.path.dirname(os.path.dirname(TOOL_DIR)), "data"))
RAW_DIR = os.path.join(DATA_DIR, "raw", "opensky")
OUT_DIR = os.path.join(DATA_DIR, "derived", "opensky")
WEBTRAK_DIR = os.path.join(DATA_DIR, "derived", "webtrak", "lcy", "nmt106")

NMT6 = (51.50535, 0.11075)  # St Pauls Church, Thamesmead, from WebTrak's monitor list
EARTH_RADIUS_M = 6371000


def parse_time(text):
    """Unix seconds from an ISO 8601 time; one without a zone is taken as UTC."""
    t = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def number(value):
    """A float, or None for a missing value (None, NaN, or pandas' NA, which isn't a float)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f

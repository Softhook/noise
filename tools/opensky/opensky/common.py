"""NMT6, the tool's paths, and small helpers for times and numbers."""

from __future__ import annotations

import datetime as dt
import math
import os

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(TOOL_DIR, "data")
WEBTRAK_DIR = os.path.join(TOOL_DIR, "..", "webtrak", "data", "lcy", "nmt106")

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

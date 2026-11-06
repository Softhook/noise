"""Times, numbers and normalisation shared by the adapters and the core."""

from __future__ import annotations

import datetime as dt
import math
import re


def parse_time(text):
    """Unix seconds from an ISO 8601 time. One without a zone is refused: the plan forbids guessing."""
    text = text.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    t = dt.datetime.fromisoformat(text)
    if t.tzinfo is None:
        raise ValueError(f"time without a zone: {text!r}")
    return t.timestamp()


def iso(t):
    """UTC ISO time to the millisecond, as the common tables use."""
    if t is None:
        return ""
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def day_of(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d")


def number(value):
    """A float, or None for a missing value."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def registration(text):
    """Upper case, letters and digits only: WebTrak's GLCYN and the database's G-LCYN both become GLCYN."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def rounded(value, places=1):
    return None if value is None else round(value, places)

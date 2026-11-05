"""Small helpers shared by the analysis and the simulator: units, numbers and UTC times."""

from __future__ import annotations

import collections
import datetime as dt


FEET = 0.3048


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def rounded(value):
    return round(value, 3) if isinstance(value, float) else value


def overlaps(intervals, start, end):
    return any(a <= end and b >= start for a, b in intervals)


def most_common(values):
    values = [v for v in values if v not in (None, "")]
    return collections.Counter(values).most_common(1)[0][0] if values else None


def parse_utc(text):
    text = text.strip().replace("T", " ").replace("Z", "")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, pattern).replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    raise ValueError(f"unreadable time: {text!r}")


def format_utc(t):
    if t is None:
        return ""
    moment = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"

"""QNH and temperature through the survey, from a METAR archive or a simple CSV."""

from __future__ import annotations

import bisect
import csv
import re

from .common import parse_utc

WEATHER_MAX_AGE_S = 3 * 3600.0  # Ignore a report older than this


class Weather:
    """QNH and temperature by time, from a METAR archive or a simple CSV.

    Accepts a time column called `valid` or `time`, and either a `metar` column or `qnh_hpa`
    with an optional `temp_c`. QNH from a METAR has 0.5 hPa added when metar_qnh_rounded_down
    is set; a qnh_hpa column is taken as exact.
    """

    def __init__(self, entries=(), max_age=WEATHER_MAX_AGE_S):
        self.entries = sorted(entries)
        self.times = [e[0] for e in self.entries]
        self.max_age = max_age

    @classmethod
    def load(cls, path, max_age=WEATHER_MAX_AGE_S, metar_rounded_down=True):
        entries = []
        with open(path, newline="") as f:
            for row in csv.DictReader(line for line in f if not line.startswith("#")):
                when = row.get("valid") or row.get("time")
                if not when:
                    continue
                qnh, temp, from_metar = parse_weather_row(row)
                if qnh is not None:
                    if from_metar and metar_rounded_down:
                        qnh += 0.5
                    entries.append((parse_utc(when), qnh, temp))
        return cls(entries, max_age)

    def at(self, t):
        """The latest report no more than max_age old, as (qnh, temp), or (None, None)."""
        i = bisect.bisect_right(self.times, t) - 1
        if i < 0 or t - self.times[i] > self.max_age:
            return None, None
        return self.entries[i][1], self.entries[i][2]


def parse_weather_row(row):
    """Return (qnh, temp, qnh came from a METAR)."""
    metar = row.get("metar") or ""
    from_metar = False
    if row.get("qnh_hpa"):
        qnh = float(row["qnh_hpa"])
    else:
        match = re.search(r"\bQ(\d{4})\b", metar)
        qnh = float(match.group(1)) if match else None
        from_metar = qnh is not None
    temp = None
    if row.get("temp_c"):
        temp = float(row["temp_c"])
    else:
        match = re.search(r"\s(M?\d{2})/(?:M?\d{2})?\s", metar)
        if match:
            temp = float(match.group(1).replace("M", "-"))
    return qnh, temp, from_metar

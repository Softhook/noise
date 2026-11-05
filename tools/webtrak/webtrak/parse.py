"""Read WebTrak's 30 s data chunks.

A chunk is fetched from ``/WebTrak/<site>/data/<handle>.mobile``. It looks like this:

    <data endTime="2026-11-05 21:47:59" generated="..." handle="59797175" radarStatus="online"
          startTime="2026-11-05 21:47:30" type="data">radar,20261105214730,10369290,O,LHR,,EVA068,...
    noise,20261105214730,106,106,5,53.4
    event,20261105080230,106,106,1,71.04,20261105080253,82.38,67.47,84.42,31,20261105080301
    </data>

Field meanings come from WebTrak's own JavaScript (providers/DataSource.js) and were checked
against real data on 5 Nov 2026:

- Every time is local airport time (Europe/London), as YYYYMMDDHHMMSS.
- A handle is UTC seconds since 1970 divided by 30 (checked in GMT and in BST), so the chunk's
  handle gives its UTC offset without guessing at the clock change.
- ``noise``: time, monitor id, monitor id, flag, level in dB. One per second per monitor. The
  flag is 1 during a noise event and 5 otherwise. The peak 1 s level matches the event LAmax, and
  the levels' energy mean is close to the event Leq, so they look like 1 s LAeq or similar, but
  WebTrak doesn't say which. For about 40 s from 00:00 and 12:00 local time every monitor at once
  reports 20.0 dB with flag 9 (seen on 4 and 5 Nov 2026; perhaps an automatic calibration check).
  That is a placeholder, not a measurement, and the first second of it can carry flag 1 instead,
  so a level counts as valid only if its flag isn't 9 and it is above 20.0.
- ``event``: start, monitor id, monitor id, class, LAmax, LAmax time, SEL, Leq, EPNL, duration in
  s, end. SEL = Leq + 10 log10(duration). Class 1 looks like an aircraft-correlated event and 5 a
  non-aircraft one (an inference). An event is listed, complete, in one or two chunks around
  its time: sometimes the one where it starts, sometimes the one where it ends, or both. The
  radar for the minute after its LAmax may only arrive in later chunks.
- ``radar``: time, track id, direction (A arrival, D departure, O other), airport, ICAO type,
  callsign, icon type, longitude, latitude, height above the aerodrome in metres, ground speed in
  m/s, registration, squawk, origin, destination, scheduled time, tag group, altitude in metres.
  Metres and m/s were checked against an E190 departure: its reported speed matched the speed
  worked out from its positions, and altitude minus height is the aerodrome's 6 m elevation.
  WebTrak gives a callsign only for LCY's scheduled flights (5 of 122 tracks on 5 Nov 2026);
  other aircraft have just a registration, and some just a squawk code.
"""

from __future__ import annotations

import calendar
import dataclasses
import datetime as dt
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 and earlier
    ZoneInfo = None

WINDOW_S = 30
SITE_ZONE = "Europe/London"
INVALID_FLAG = "9"
NO_DATA_DB = 20.0

_ATTR = re.compile(r'(\w+)="([^"]*)"')
_HEADER = re.compile(r"<data\b([^>]*)>", re.S)
_ERROR = re.compile(r"<error\b([^>]*)/?>", re.S)


class NotAvailable(Exception):
    """WebTrak has no data for this handle yet, or never will."""


@dataclasses.dataclass
class Level:
    utc: float
    monitor: str
    flag: str
    level: float

    @property
    def valid(self):
        """False for the 20 dB placeholder WebTrak sends when a monitor has no measurement."""
        return self.flag != INVALID_FLAG and self.level > NO_DATA_DB


@dataclasses.dataclass
class Event:
    monitor: str
    start: float
    lmax_time: float
    end: float
    lmax: float
    sel: float
    leq: float
    epnl: float
    duration: float
    event_class: str
    offset_s: int = 0  # the UTC offset of the chunk it came from, for local times

    @property
    def key(self):
        return (self.monitor, round(self.start))


@dataclasses.dataclass
class Position:
    utc: float
    track: str
    direction: str
    airport: str
    aircraft_type: str
    callsign: str
    registration: str
    squawk: str
    lat: float
    lon: float
    height_m: float
    altitude_m: float
    speed_ms: float
    origin: str
    destination: str


@dataclasses.dataclass
class Chunk:
    handle: int
    start_utc: float
    offset_s: int
    radar_status: str
    levels: list
    events: list
    positions: list


def local_naive_seconds(text):
    """Seconds since 1970 for a local time string, treating it as if it were UTC."""
    digits = re.sub(r"\D", "", text)
    moment = dt.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
    return calendar.timegm(moment.timetuple())


def site_zone():
    if ZoneInfo is None:
        raise SystemExit("Python 3.9 or later is needed for local times")
    return ZoneInfo(SITE_ZONE)


def local_to_utc(text):
    """'YYYY-MM-DD HH:MM[:SS]' (or with a T) in airport local time, to UTC seconds."""
    text = text.strip().replace("T", " ")
    moment = dt.datetime.strptime(text, "%Y-%m-%d %H:%M" if text.count(":") == 1 else "%Y-%m-%d %H:%M:%S")
    return moment.replace(tzinfo=site_zone()).timestamp()


def handle_for_utc(seconds):
    return int(seconds // WINDOW_S)


def utc_for_handle(handle):
    return handle * WINDOW_S


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_chunk(text, handle=None):
    """Parse one chunk. Raises NotAvailable for WebTrak's error reply, an empty or a cut-off answer."""
    error = _ERROR.search(text)
    if error and "<data" not in text:
        attrs = dict(_ATTR.findall(error.group(1)))
        raise NotAvailable(attrs.get("faultDescription", "error reply"))
    header = _HEADER.search(text)
    if not header:
        raise NotAvailable("no <data> element")
    attrs = dict(_ATTR.findall(header.group(1)))
    start_text = attrs.get("startTime", "")
    if start_text.startswith("1970"):
        raise NotAvailable("empty chunk")
    try:
        if handle is None:
            handle = int(attrs["handle"])
        local_start = local_naive_seconds(start_text)
    except (KeyError, ValueError):
        raise NotAvailable(f"unreadable chunk header: {header.group(0)[:200]!r}") from None
    start_utc = utc_for_handle(handle)
    # UTC offset in whole quarter hours, from the chunk's local start time and its handle.
    offset = int(round((local_start - start_utc) / 900.0)) * 900

    body, closed, _ = text[header.end():].partition("</data>")
    if not body.strip():
        # Periods before WebTrak's data range come back like this, with radarStatus="offline".
        raise NotAvailable("empty chunk")
    if not closed:
        raise NotAvailable("reply cut off before </data>")
    chunk = Chunk(handle, start_utc, offset, attrs.get("radarStatus", ""), [], [], [])

    def utc(local_text):
        return local_naive_seconds(local_text) - offset

    for line in body.splitlines():
        parts = line.strip().split(",")
        kind = parts[0]
        try:
            if kind == "noise" and len(parts) >= 6:
                level = _number(parts[5])
                if level is not None:
                    chunk.levels.append(Level(utc(parts[1]), parts[3], parts[4], level))
            elif kind == "event" and len(parts) >= 12:
                chunk.events.append(Event(
                    monitor=parts[3], start=utc(parts[1]), lmax_time=utc(parts[6]), end=utc(parts[11]),
                    lmax=_number(parts[5]), sel=_number(parts[7]), leq=_number(parts[8]),
                    epnl=_number(parts[9]), duration=_number(parts[10]), event_class=parts[4],
                    offset_s=offset))
            elif kind == "radar" and len(parts) >= 19:
                lon, lat = _number(parts[8]), _number(parts[9])
                if lon is None or lat is None:
                    continue
                chunk.positions.append(Position(
                    utc=utc(parts[1]), track=parts[2], direction=parts[3], airport=parts[4],
                    aircraft_type=parts[5], callsign=parts[6] or parts[12],
                    registration=parts[12], squawk=parts[13], lat=lat, lon=lon,
                    height_m=_number(parts[10]), altitude_m=_number(parts[18]),
                    speed_ms=_number(parts[11]), origin=parts[14], destination=parts[15]))
        except ValueError:
            continue  # an unreadable time; skip the line rather than the chunk
    return chunk

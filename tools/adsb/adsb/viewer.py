"""Write viewer.html: the analysis results, embedded in a page that works offline."""

from __future__ import annotations

import datetime as dt
import json
import os

from .common import format_utc, rounded


VIEWER_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_template.html")


def viewer_track(rows, spacing_s=1.0):
    """Thin a flight's positions for drawing: [seconds from start, east m, north m, height above mic m]."""
    track, last = [], None
    for row in rows:
        if last is not None and row["t"] - last < spacing_s and row is not rows[-1]:
            continue
        above = row["height_above_mic_m"]
        track.append([
            round(row["t"] - rows[0]["t"], 1), round(row["east_m"]), round(row["north_m"]),
            None if above is None else round(above),
        ])
        last = row["t"]
    return track


def viewer_data(flights, tracks, summary, site, config):
    """Everything the viewer shows. Deliberately no latitudes or longitudes, so the garden isn't revealed."""
    return {
        "generated_utc": format_utc(dt.datetime.now(dt.timezone.utc).timestamp()),
        "simulated": bool(config.get("simulated")),
        "mic_amsl_m": round(site.mic_amsl, 2),
        "summary": summary,
        "flights": [{key: rounded(value) for key, value in flight.items()} for flight in flights],
        "tracks": {str(key): value for key, value in tracks.items()},
    }


def write_viewer(path, data):
    with open(VIEWER_TEMPLATE) as f:
        template = f.read()
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    with open(path, "w") as f:
        f.write(template.replace("__ADSB_DATA__", payload, 1))

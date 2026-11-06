"""Look up an aircraft in its country's official register, online.

A registration's nationality mark says which register holds it: G- the UK's (the CAA's G-INFO),
HB- Switzerland's (FOCA/BAZL). REGISTERS lists the ones that can be asked; add a country by
writing a function that takes a normalised registration (common.registration(), e.g. GLCYN) and
returns an entry (the fleet table's columns, fleet.FIELDS) or None if the register has no such
aircraft, and adding it to REGISTERS. Everything else (which registrations to check, the fleet
table) is fleet.py's.

Only what the register says about the aircraft is kept: type, model, engines, mass, noise
certificate. Never its owner or operator, since a private aircraft's owner is a person.

Requests are paced (PAUSE_S between them) and say who's asking (USER_AGENT), as WebTrak's client
does. Nothing here is run by the build: only `python3 -m survey fleet` makes requests.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request

USER_AGENT = "thamesmead-noise-survey/0.1 (personal, non-commercial noise research)"
PAUSE_S = 1.0
TIMEOUT_S = 30


class LookupFailed(Exception):
    """The register couldn't be asked, or gave an answer we don't understand. Unlike None (no such
    aircraft), this says nothing about the aircraft, so it's retried next time."""


class Http:
    """Requests to one register, at most one every PAUSE_S."""

    def __init__(self, pause_s=PAUSE_S):
        self.pause_s = pause_s
        self.last = 0.0

    def json(self, url, body=None):
        wait = self.last + self.pause_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise LookupFailed(f"{url}: {error}") from None
        finally:
            self.last = time.monotonic()


def today():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def epndb(text):
    """The number from a noise level as the registers print it ("Approach: 92.5 EPNdB"), or None."""
    got = re.search(r"(\d+(?:\.\d+)?)\s*EPNdB", text or "")
    return float(got.group(1)) if got else None


def kg(text):
    got = re.search(r"\d+", (text or "").replace(",", ""))
    return int(got.group(0)) if got else None


# --- UK: the CAA's G-INFO -------------------------------------------------------------------------
# The API behind https://www.caa.co.uk/aircraft-register/g-info/search-g-info/ (its page names it
# as data-apiendpoint). search -> AircraftID, then details and noise certificate by that id.

GINFO_API = "https://ginfoapi.caa.co.uk/api/aircraft/"


def uk(reg, http):
    mark = reg[1:]
    try:
        hits = [h for h in http.json(GINFO_API + "search", {"Registration": mark, "IncludeDeregistered": False})
                if h.get("Mark") == mark]
        if not hits:
            return None
        aircraft_id = hits[0]["AircraftID"]
        details = http.json(f"{GINFO_API}details/{aircraft_id}")
        a = details["AircraftDetails"]
        noise = details.get("NoiseSummaryDetails") or {}
        levels = {}
        if noise.get("NoiseCertificateNumber"):
            levels = http.json(f"{GINFO_API}noisecertificationdetails/{aircraft_id}").get("NoiseLevel") or {}
        status = (details.get("RegistrationDetails") or {}).get("Status") or ""
        return {
            "registration": reg, "mark": f"G-{mark}", "status": status.lower(),
            "icao_type": a.get("ICAOAircraftTypeDesignator") or "", "model": a.get("Type") or "",
            "marketing_name": a.get("PopularName") or "", "manufacturer": a.get("Manufacturer") or "",
            "serial_number": a.get("SerialNumber") or "", "year_built": a.get("YearBuild") or "",
            "icao24": ((a.get("ICAO24BitAircraftAddress") or {}).get("Hex") or "").upper(),
            "engines": "; ".join(f"{e.get('NumberOfEngines')} x {(e.get('Name') or '').strip()}" for e in a.get("Engines") or []),
            "mtow_kg": kg(a.get("Mtow") or a.get("MaximumTakeOffMass")),
            "noise_standard": f"ICAO Annex 16, Chapter {noise['NoiseChapter'].lstrip('0')}" if noise.get("NoiseChapter") else "",
            "approach_epndb": epndb(levels.get("ApproachLevel")),
            "lateral_epndb": epndb(levels.get("LateralLevel")),
            "flyover_epndb": epndb(levels.get("FlyoverLevel")),
            "register": "uk", "register_ref": str(aircraft_id), "checked_utc": today(), "note": "",
        }
    except (KeyError, TypeError, AttributeError) as error:
        raise LookupFailed(f"G-INFO's answer for G-{mark} isn't as expected: {error!r}") from None


# --- Switzerland: FOCA/BAZL ------------------------------------------------------------------------
# The API behind https://app02.bazl.admin.ch/web/bazl/en/#/lfr/search: a search by registration,
# whose answer has the type; then the aircraft's own record, with engines, mass and noise.

BAZL_API = "https://app02.bazl.admin.ch/web/bazl-backend/lfr"


def swiss_noise(text):
    """BAZL's noiseLevel, "Sideline: 85.4 EPNdB; Take Off: 77.7 EPNdB; Approach: 91.4 EPNdB", as
    {"lateral", "flyover", "approach"}: sideline is the lateral point, take-off the flyover one."""
    names = {"sideline": "lateral", "lateral": "lateral", "take off": "flyover", "flyover": "flyover", "approach": "approach"}
    out = {}
    for part in (text or "").split(";"):
        name, _, value = part.partition(":")
        if name.strip().lower() in names:
            out[names[name.strip().lower()]] = epndb(value)
    return out


def swiss(reg, http):
    mark = f"HB-{reg[2:]}"
    query = {"page_result_limit": 10, "current_page_number": 1, "sort_list": "registration", "language": "en",
             # Only aircraft on the register now: BAZL refuses the other statuses its page offers
             "queryProperties": {"registration": mark, "aircraftStatus": ["Registered"]}}
    try:
        hits = [h for h in http.json(BAZL_API, query) if h.get("registration") == mark]
        if not hits:
            return None
        lfr_id = hits[0]["lfrId"]
        record = http.json(f"{BAZL_API}/{lfr_id}")
        d = record.get("details") or {}
        noise = swiss_noise(d.get("noiseLevel"))
        return {
            "registration": reg, "mark": mark, "status": (record.get("status") or "").lower(),
            "icao_type": record.get("icaoCode") or "", "model": record.get("aircraftModelType") or "",
            "marketing_name": d.get("marketing") or "", "manufacturer": record.get("manufacturer") or "",
            "serial_number": d.get("serialNumber") or "", "year_built": d.get("yearOfManufacture") or "",
            "icao24": "",  # BAZL doesn't give it
            "engines": "; ".join(f"{e.get('count')} x {e.get('name')}" for e in d.get("engines") or []),
            "mtow_kg": d.get("mtom") or None,
            "noise_standard": d.get("noiseStandard") or "",
            "approach_epndb": noise.get("approach"), "lateral_epndb": noise.get("lateral"),
            "flyover_epndb": noise.get("flyover"),
            "register": "ch", "register_ref": str(lfr_id), "checked_utc": today(), "note": "",
        }
    except (KeyError, TypeError, AttributeError) as error:
        raise LookupFailed(f"BAZL's answer for {mark} isn't as expected: {error!r}") from None


# Nationality mark (as normalised registrations start) -> (code, as the fleet table's register
# column gives it; the register's name; its lookup). nationality() tries the longest marks first,
# so a two-letter mark wins over a one-letter one.
REGISTERS = {
    "HB": ("ch", "Switzerland (FOCA/BAZL)", swiss),
    "G": ("uk", "UK (CAA G-INFO)", uk),
}


def nationality(reg):
    """The nationality mark REGISTERS knows a registration by, or None if none can be asked."""
    for mark in sorted(REGISTERS, key=len, reverse=True):
        if reg.startswith(mark):
            return mark
    return None


def look_up(reg, http=None):
    """Ask reg's register about it: an entry, or None if it has no such aircraft. Raises KeyError
    if no register in REGISTERS covers it, LookupFailed if the register can't be asked."""
    mark = nationality(reg)
    if mark is None:
        raise KeyError(reg)
    return REGISTERS[mark][2](reg, http or Http())

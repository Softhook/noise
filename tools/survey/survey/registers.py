"""Look up an aircraft in its country's official register, online.

A registration's nationality mark says which register holds it. REGISTERS lists the ones that can
be asked, of two kinds:
- searched, one aircraft at a time: G- the UK's (the CAA's G-INFO), HB- Switzerland's (FOCA/BAZL);
- downloaded whole, as the file the register publishes: EI- Ireland's (the IAA's monthly Excel
  file), LX- Luxembourg's (the DAC's PDF, through data.public.lu). Each run downloads the newest
  file once, reads it in memory and keeps nothing of it but the entries asked for, since the
  files also give owners' names and addresses.

Add a country by writing a function that takes a normalised registration (common.registration(),
e.g. GLCYN) and an Http, and returns an entry (the fleet table's columns, fleet.FIELDS) or None if
the register has no such aircraft, and adding it to REGISTERS. Everything else (which
registrations to check, the fleet table) is fleet.py's.

A downloaded register gives the model (BD-500-1A10) but not the ICAO type designator (BCS1), so
MODEL_TYPES maps the models that fly near the survey to their designators. An entry whose model
isn't there keeps its model and an empty type, and so settles nothing until it's added.

Only what the register says about the aircraft is kept: type, model, engines, mass, noise
certificate. Never its owner or operator, since a private aircraft's owner is a person.

Requests are paced (PAUSE_S between them) and say who's asking (USER_AGENT), as WebTrak's client
does. Nothing here is run by the build: only `python3 -m survey fleet` makes requests.

Standard library only, except that Luxembourg's PDF is read with pdftotext (poppler: `brew install
poppler`); without it, Luxembourg's lookups fail and say why, and the others carry on.
"""

from __future__ import annotations

import datetime as dt
import html
import http.client
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from .common import registration

USER_AGENT = "thamesmead-noise-survey/0.1 (personal, non-commercial noise research)"
PAUSE_S = 1.0
TIMEOUT_S = 30


class LookupFailed(Exception):
    """The register couldn't be asked, or gave an answer we don't understand. Unlike None (no such
    aircraft), this says nothing about the aircraft, so it's retried next time."""


class Http:
    """Requests to the registers, at most one every PAUSE_S. files: what a downloaded register's
    read gave, by register, kept for the run so each file is downloaded once."""

    def __init__(self, pause_s=PAUSE_S):
        self.pause_s = pause_s
        self.last = 0.0
        self.files = {}

    def get(self, url, body=None, accept="application/json"):
        """The response's bytes."""
        wait = self.last + self.pause_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return response.read()
        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            raise LookupFailed(f"{url}: {error!r}") from None
        finally:
            self.last = time.monotonic()

    def json(self, url, body=None):
        try:
            return json.loads(self.get(url, body))
        except ValueError as error:
            raise LookupFailed(f"{url}: not JSON: {error}") from None

    def text(self, url):
        return self.get(url, accept="text/html").decode("utf-8", "replace")

    def bytes(self, url, attempts=2):
        """A whole file. Tried again once if it fails, as a large download can be cut short."""
        for attempt in range(attempts):
            try:
                return self.get(url, accept="*/*")
            except LookupFailed:
                if attempt == attempts - 1:
                    raise


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


# --- Downloaded registers -----------------------------------------------------------------------------

# A register's model (as Ireland's and Luxembourg's files give it) -> ICAO type designator, for
# the models that fly near the survey. First match wins. From the EASA type certificates (file 10
# for the ERJ 190, file 18 for the BD-500) and ICAO Doc 8643. A model not here gets no type.
MODEL_TYPES = [
    (r"^BD-500-1A10\b", "BCS1"),  # A220-100
    (r"^BD-500-1A11\b", "BCS3"),  # A220-300
    (r"^ERJ ?190-100", "E190"),
    (r"^ERJ ?190-200", "E195"),
    (r"^ERJ ?190-300", "E290"),  # E190-E2
    (r"^ERJ ?190-400", "E295"),  # E195-E2
    (r"^DHC-8-40[0-2]\b", "DH8D"),  # Dash 8-400
    (r"^ATR 72-212 ?A\b", "AT76"),
    (r"^A319-1\d\d$", "A319"),
    (r"^A320-2\d\dN$", "A20N"),
    (r"^A320-2\d\d$", "A320"),
    (r"^A321-2\d\dNX?$", "A21N"),
]


def icao_type(model):
    """The ICAO type designator MODEL_TYPES gives a model, or ""."""
    model = re.sub(r"\s+", " ", (model or "").strip().upper())
    return next((code for pattern, code in MODEL_TYPES if re.search(pattern, model)), "")


def file_entry(reg, mark, model, register, ref, note, **more):
    """An entry from a downloaded register's row: the fleet table's columns."""
    code = icao_type(model)
    return {"registration": reg, "mark": mark, "status": "registered", "icao_type": code, "model": model,
            "marketing_name": "", "manufacturer": "", "serial_number": "", "year_built": "", "icao24": "",
            "engines": "", "mtow_kg": None, "noise_standard": "", "approach_epndb": None, "lateral_epndb": None,
            "flyover_epndb": None, "register": register, "register_ref": ref, "checked_utc": today(),
            "note": note if code else f"{note}; model not in registers.MODEL_TYPES, so no type", **more}


def downloaded(reg, http, code, read):
    """reg's entry in a downloaded register, or None. read(http) -> {registration: entry}, called
    once a run per register (Http.files)."""
    files = getattr(http, "files", None)
    if files is None:
        files = http.files = {}
    if code not in files:
        try:
            files[code] = read(http)
        except LookupFailed as error:
            files[code] = error  # So the rest of the run doesn't download it again
    if isinstance(files[code], LookupFailed):
        raise files[code]
    return files[code].get(reg)


# Ireland: the IAA's "All registered aircraft" Excel file, issued each month at
# https://www.iaa.ie/commercial-aviation/aircraft-registration-2/latest-register-and-monthly-changes-1
# (a listing over several pages, with each file's date of issue).

IAA_LISTING = "https://www.iaa.ie/commercial-aviation/aircraft-registration-2/latest-register-and-monthly-changes-1"
IAA_PAGES = 10


def iaa_newest(http):
    """(date of issue, title, url) of the newest "all registered aircraft" file in the listing."""
    files = {}
    for page in range(IAA_PAGES):
        text = http.text(IAA_LISTING + (f"/{page}" if page else ""))
        found = 0
        for row in re.findall(r"<tr.*?</tr>", text, re.S):
            url = re.search(r'href="([^"]+\.xlsx[^"]*)"', row)
            issued = re.search(r"(\d\d)/(\d\d)/(\d{4})", row)
            if url and issued and "all-registered" in url.group(1):
                title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row)).strip()
                day, month, year = issued.groups()
                if url.group(1) not in files:
                    found += 1
                files[html.unescape(url.group(1))] = (f"{year}-{month}-{day}", title)
        if not found and page:
            break  # Past the last page
    if not files:
        raise LookupFailed(f"no register file found at {IAA_LISTING}")
    url, (issued, title) = max(files.items(), key=lambda f: f[1][0])
    return issued, title, url


def xlsx_rows(data):
    """The first sheet of an Excel file, as lists of cell text, by column. Standard library only."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(t.text or "" for t in si.iter(f"{ns}t"))
                      for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{ns}si")]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise LookupFailed(f"not a readable Excel file: {error}") from None
    rows = []
    for r in sheet.iter(f"{ns}row"):
        cells = {}
        for c in r.findall(f"{ns}c"):
            column = 0
            for letter in re.match(r"[A-Z]*", c.get("r", "")).group(0):
                column = column * 26 + ord(letter) - 64
            v, kind = c.find(f"{ns}v"), c.get("t")
            text = v.text if v is not None and v.text is not None else ""
            if kind == "s" and text:
                text = shared[int(text)]
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{ns}t"))
            cells[(column or len(cells) + 1) - 1] = text.strip()
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def iaa_entries(rows, as_at):
    """{registration: entry} from the IAA file's rows. Its header row starts "Registration Mark"."""
    header = next((i for i, r in enumerate(rows) if r and r[0].lower().startswith("registration mark")), None)
    if header is None:
        raise LookupFailed("the IAA file has no \"Registration Mark\" header row")
    names = [n.lower() for n in rows[header]]

    def col(row, *starts):
        for i, n in enumerate(names):
            if any(n.startswith(s) for s in starts) and i < len(row):
                return row[i]
        return ""

    out = {}
    for row in rows[header + 1:]:
        mark = col(row, "registration mark")
        if not mark.upper().startswith(("EI-", "EJ-")):  # EJ-: Ireland's register for business aircraft
            continue
        count, engine = col(row, "no. of engines"), " ".join(filter(None, [col(row, "engine manufacturer"), col(row, "engine model")]))
        reg = registration(mark)
        out[reg] = file_entry(
            reg, mark.upper(), col(row, "aircraft model"), "ie", as_at, f"IAA register as at {as_at}",
            manufacturer=col(row, "aircraft producer"), serial_number=col(row, "aircraft serial"),
            year_built=col(row, "year of manufacture"), mtow_kg=kg(col(row, "mtow")),
            engines=f"{count} x {engine}" if count and engine else engine)
    return out


def read_ireland(http):
    issued, title, url = iaa_newest(http)
    as_at = re.search(r"\d{1,2} \w+ \d{4}", title)
    return iaa_entries(xlsx_rows(http.bytes(url)), as_at.group(0) if as_at else issued)


def ireland(reg, http):
    return downloaded(reg, http, "ie", read_ireland)


# Luxembourg: the DAC's "Relevé luxembourgeois des immatriculations", a PDF published through
# data.public.lu's dataset, whose API lists its files.

LU_DATASET = "https://data.public.lu/api/1/datasets/releve-luxembourgeois-des-immatriculations/"


def lu_newest(http):
    """(date, url) of the dataset's newest PDF."""
    try:
        resources = [r for r in http.json(LU_DATASET)["resources"] if (r.get("format") or "").lower() == "pdf"]
        newest = max(resources, key=lambda r: r.get("last_modified") or "")
        return newest["last_modified"][:10], newest["url"]
    except (KeyError, TypeError, ValueError) as error:
        raise LookupFailed(f"data.public.lu's answer isn't as expected: {error!r}") from None


def pdf_text(data):
    """A PDF's text, laid out as on the page (pdftotext -layout), pages split by form feeds."""
    if not shutil.which("pdftotext"):
        raise LookupFailed("reading Luxembourg's register needs pdftotext (brew install poppler)")
    with tempfile.TemporaryDirectory() as d:
        path = f"{d}/register.pdf"
        with open(path, "wb") as f:
            f.write(data)
        done = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=120)
    if done.returncode:
        raise LookupFailed(f"pdftotext couldn't read the PDF: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout.decode("utf-8", "replace")


def lu_entries(text, as_at):
    """{registration: entry} from the relevé's text. Its columns are where each page's header row
    (Immat, Constructeur, Type d'aéronef, SN aéronef, Propriétaire) puts them; a model too long for
    its column carries on in the lines below, until a blank line."""
    out = {}
    for page in text.split("\f"):
        lines = page.splitlines()
        head = next((ln for ln in lines if ln.startswith("Immat") and "Constructeur" in ln), None)
        if head is None:
            continue
        at = {name: head.find(label) for name, label in
              [("maker", "Constructeur"), ("model", "Type d"), ("serial", "SN a"), ("owner", "Propri")]}
        if min(at.values()) < 0:
            raise LookupFailed(f"a page of Luxembourg's register has an unexpected header: {head!r}")
        current = None
        for line in lines:
            if not line.strip():
                current = None
                continue
            if re.match(r"LX-[A-Z0-9]+\b", line):
                mark = line.split()[0]
                current = {"mark": mark, "maker": line[at["maker"]:at["model"]].strip(),
                           "model": line[at["model"]:at["serial"]].strip(), "serial": line[at["serial"]:at["owner"]].split()}
                out[registration(mark)] = current
            elif current is not None:
                more = line[at["model"]:at["serial"]].strip()
                if more:
                    current["model"] += " " + more
    return {reg: file_entry(reg, r["mark"], r["model"], "lu", as_at, f"DAC relevé of {as_at}",
                            manufacturer=r["maker"], serial_number=r["serial"][0] if r["serial"] else "")
            for reg, r in out.items()}


def read_luxembourg(http):
    issued, url = lu_newest(http)
    return lu_entries(pdf_text(http.bytes(url)), issued)


def luxembourg(reg, http):
    return downloaded(reg, http, "lu", read_luxembourg)


# Nationality mark (as normalised registrations start) -> (code, as the fleet table's register
# column gives it; the register's name; its lookup). nationality() tries the longest marks first,
# so a two-letter mark wins over a one-letter one.
REGISTERS = {
    "HB": ("ch", "Switzerland (FOCA/BAZL)", swiss),
    "EI": ("ie", "Ireland (IAA, monthly file)", ireland),
    "EJ": ("ie", "Ireland (IAA, monthly file)", ireland),
    "LX": ("lu", "Luxembourg (DAC relevé)", luxembourg),
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

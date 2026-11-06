"""Read a deployment's manifest: its period, receptors and sources. See ARCHITECTURE.md, Manifest.

Paths in a manifest are relative to the manifest file. A receptor whose location is private (the
garden) gives `"config"`: the path to a git-ignored site.json (tools/adsb's format). If that file
isn't there, the receptor is left out and a warning given, so a manifest in git never needs the
garden's location in it.
"""

from __future__ import annotations

import glob
import json
import os

from .adapters import ADAPTERS
from .common import parse_time

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOYMENTS_DIR = os.path.join(TOOLS_DIR, "deployments")
OUT_DIR = os.path.join(TOOLS_DIR, "survey", "data")


class ManifestError(ValueError):
    pass


def _receptor(rid, spec, base, warnings):
    spec = dict(spec)
    if "config" in spec:
        path = os.path.normpath(os.path.join(base, spec.pop("config")))
        if not os.path.exists(path):
            warnings.append(f"receptor {rid}: {os.path.relpath(path)} not found, so it's left out")
            return None
        with open(path) as f:
            site = json.load(f)["site"]
        spec = {**site, **spec}
    for key in ("lat", "lon"):
        if not isinstance(spec.get(key), (int, float)):
            raise ManifestError(f"receptor {rid}: {key} must be a number")
    return {
        "id": rid,
        "name": str(spec.get("name") or rid),
        "label": str(spec.get("label") or spec.get("name") or rid),
        "lat": float(spec["lat"]),
        "lon": float(spec["lon"]),
        "ground_elevation_m": spec.get("ground_elevation_m"),
        "mic_height_m": spec.get("mic_height_m"),
        "public": spec.get("public") is True,
    }


def _source(name, spec, base):
    """A source's entry, with its adapter's paths made absolute."""
    spec = dict(spec)
    adapter = ADAPTERS.get(str(spec.get("adapter")))
    if adapter is None:
        raise ManifestError(f"source {name}: adapter must be one of {', '.join(ADAPTERS)}")
    for key in adapter.PATHS:
        if key in spec:
            spec[key] = os.path.normpath(os.path.join(base, spec[key]))
    return spec


def _pass_receptor(named, receptors, warnings):
    """The receptor whose closest approach dates each pass id (link.py). It's the manifest's
    `pass_receptor`, or else its first public receptor: a private one may be missing on another
    computer, and pass ids must come out the same wherever the build runs."""
    if named:
        if named in receptors:
            return named
        warnings.append(f"pass_receptor {named} isn't available, so pass ids are dated by another receptor")
    public = [rid for rid, r in receptors.items() if r["public"]]
    return (public or list(receptors))[0]


def load(path):
    """The manifest as a dict, with absolute paths, parsed times and the receptors that are available."""
    path = os.path.abspath(path)
    base = os.path.dirname(path)
    with open(path) as f:
        raw = json.load(f)
    warnings = []
    try:
        start, end = (parse_time(t) for t in raw["window_utc"])
    except (KeyError, ValueError, TypeError) as error:
        raise ManifestError(f"{path}: window_utc must be two UTC times: {error}") from None
    if end <= start:
        raise ManifestError(f"{path}: window_utc ends before it starts")
    receptors = {}
    for rid, spec in (raw.get("receptors") or {}).items():
        receptor = _receptor(rid, spec, base, warnings)
        if receptor:
            receptors[rid] = receptor
    if not receptors:
        raise ManifestError(f"{path}: no receptors available")
    pass_receptor = _pass_receptor(raw.get("pass_receptor"), receptors, warnings)
    sources = {name: _source(name, spec, base) for name, spec in (raw.get("sources") or {}).items()
               if spec is not None}  # A source set to null is turned off
    name = raw.get("deployment") or os.path.splitext(os.path.basename(path))[0]
    return {
        "deployment": name,
        "description": raw.get("description", ""),
        "path": path,
        "start": start,
        "end": end,
        "max_km": float(raw.get("max_km", 15)),
        "receptors": receptors,
        "pass_receptor": pass_receptor,
        "sources": sources,
        "out_dir": os.path.join(OUT_DIR, name),
        "warnings": warnings,
    }


def all_manifests(folder=None):
    return sorted(glob.glob(os.path.join(folder or DEPLOYMENTS_DIR, "*.json")))

"""One adapter per kind of source. Only an adapter may read its source's files or import its package.

An adapter is a module with:

    PATHS                                   keys of its manifest entry that are paths; manifest.load
                                            makes them absolute, relative to the manifest
    read(name, spec, context, warnings)     -> {table: rows}, for any of schema.SOURCE_TABLES; a
                                            table it doesn't fill can be left out. Rows may be any
                                            iterable: a generator for positions or levels keeps a
                                            long deployment's rows from all being held at once
    limits(spec, context)                   -> what the source can see (explain.py's limits)

name is the source's name in the manifest (what its rows' `source` column says), spec its manifest
entry, and context the deployment's Context. Problems that shouldn't stop the build are appended to
warnings.

To add a source of a new kind: write its module here, and add it to ADAPTERS. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import adsb, webtrak

ADAPTERS = {"adsb": adsb, "webtrak": webtrak}


@dataclass(frozen=True)
class Context:
    """What an adapter may know about the deployment."""
    start: float  # Unix seconds: the window to read
    end: float
    receptors: dict  # id -> receptor (manifest.load's)
    max_km: float  # How far from a receptor a source's tracks are kept, where the adapter limits them


def context(m):
    """The Context for a manifest from manifest.load."""
    return Context(m["start"], m["end"], m["receptors"], m["max_km"])


"""Each pass's registration and type, with where the type came from.

The type comes from, in order:
1. the fleet table (fleet.py), by the pass's registration: an official register's answer, or a
   person's (`manual`). type_source is `register:<code>` (register:uk, register:ch) or `manual`;
2. otherwise, the first type any of its flights gives, in source order (link.source_rank), so the
   ADS-B sources' (tar1090-db's) before WebTrak's. type_source is that source's name.

`disagree` lists every source whose type differs from the one chosen, and a transponder address
(hex) that differs from the register's, which would mean the registration was matched to the wrong
aircraft. Such passes are worth a look; the type is still the one chosen above.
"""

from __future__ import annotations

from . import fleet, link


def resolve(passes, flights, entries):
    """passes: the passes table; flights: the flights table; entries: fleet.read(). Rows for the
    identity table, one per pass, in pass order."""
    by_key = {(f["source"], f["source_id"]): f for f in flights}
    members = {}
    for p in passes:
        f = by_key.get((p["source"], p["source_id"]))
        if f:
            members.setdefault(p["pass_id"], []).append(f)
    rows = []
    for pass_id in sorted(members):
        fs = sorted(members[pass_id], key=lambda f: link.source_rank(f["source"]))
        reg = next((f["registration"] for f in fs if f["registration"]), "")
        entry = entries.get(reg) if reg else None
        given = [(f["source"], f["type"]) for f in fs if f["type"]]
        if fleet.known_type(entry):
            chosen = entry["icao_type"]
            source = fleet.MANUAL if entry.get("register") == fleet.MANUAL else f"register:{entry.get('register')}"
            model = entry.get("model") or ""
        elif given:
            chosen, source, model = given[0][1], given[0][0], ""
        else:
            chosen = source = model = ""
        disagree = [f"{s} {t}" for s, t in given if t != chosen]
        want_hex = (entry or {}).get("icao24", "").upper() if fleet.known_type(entry) else ""
        if want_hex:
            disagree += [f"{f['source']} hex {f['hex'].upper()}, register {want_hex}"
                         for f in fs if f.get("hex") and f["hex"].upper() != want_hex]
        rows.append({"pass_id": pass_id, "registration": reg, "type": chosen, "model": model,
                     "type_source": source, "disagree": "; ".join(disagree)})
    return rows

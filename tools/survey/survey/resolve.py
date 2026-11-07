"""Each pass's registration and type, with where the type came from.

The type comes from, in order:
1. the fleet table (fleet.py), by the pass's registration: an official register's answer, or a
   person's (`manual`). type_source is `register:<code>` (register:uk, register:ch) or `manual`;
2. otherwise, the first type any of its flights gives, in source order (common.source_rank), so the
   ADS-B sources' (tar1090-db's) before WebTrak's. type_source is that source's name.

`fleet` says why the fleet table didn't settle the type, when it didn't: `no registration`, `not in
the table` (never looked up, or no register can be asked online), `not found` (its register doesn't
have it) or `no type` (its register's entry gives none, such as a model registers.MODEL_TYPES lacks).

`disagree` lists every source whose type differs from the one chosen, and a transponder address
(hex) that differs from the register's, which would mean the registration was matched to the wrong
aircraft. Such passes are worth a look; the type is still the one chosen above.
"""

from __future__ import annotations

from . import fleet


def resolve(members, flights, entries):
    """members: link.members(); flights: the flights table; entries: fleet.read(). Rows for the
    identity table, one per pass with a flight, in pass order."""
    by_key = {(f["source"], f["source_id"]): f for f in flights}
    rows = []
    for pass_id, keys in sorted(members.items()):
        fs = [by_key[k] for k in keys if k in by_key]  # In source order, as members() gives them
        if fs:
            rows.append(_identity(pass_id, fs, entries))
    return rows


def _identity(pass_id, fs, entries):
    reg = next((f["registration"] for f in fs if f["registration"]), "")
    entry = entries.get(reg) if reg else None
    given = [(f["source"], f["type"]) for f in fs if f["type"]]
    if not reg:
        why = "no registration"
    elif entry is None:
        why = "not in the table"
    elif entry.get("status") == fleet.NOT_FOUND:
        why = "not found"
    else:
        why = "" if fleet.known_type(entry) else "no type"
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
    return {"pass_id": pass_id, "registration": reg, "type": chosen, "model": model,
            "type_source": source, "fleet": why, "disagree": "; ".join(disagree)}


def summary(rows):
    """build.json's types: how many passes have their type from a register, by hand, from a source
    only, or not at all, and how many have sources that disagree."""
    def count(test):
        return sum(1 for i in rows if test(i))

    return {
        "from a register": count(lambda i: i["type_source"].startswith("register:")),
        "set by hand": count(lambda i: i["type_source"] == fleet.MANUAL),
        "from a source only": count(lambda i: i["type_source"] and ":" not in i["type_source"]
                                    and i["type_source"] != fleet.MANUAL),
        "unknown": count(lambda i: not i["type"]),
        "sources disagree": count(lambda i: i["disagree"]),
    }

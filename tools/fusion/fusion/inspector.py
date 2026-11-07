#!/usr/bin/env python3
"""Look inside Fusion session folders without assuming their format, and without changing them.

This finds evidence for decoding the format; it isn't a decoder. Every result is a lead to
test against a controlled recording. See Documents/Fusion_Data_Format_Reverse_Engineering.md.

  noise fusion survey   SESSION [--out report.json]
  noise fusion strings  FILE [--min 4]
  noise fusion level    FILE --db 94.0 [--tol 0.5]
  noise fusion time     FILE --at 2026-11-05T14:30:00 [--window-hours 14]
  noise fusion compare  SESSION_A SESSION_B

Add --json before the command for machine-readable output. Files are only ever opened for reading.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import re
import statistics
import struct
import sys

CHUNK = 1024 * 1024
STRIDE_SAMPLE = 128 * 1024
STRIDE_MAX_LAG = 2048
SEARCH_LIMIT = 32 * 1024 * 1024  # whole-file value searches are slow in pure Python
HIGH_ENTROPY = 7.9

SIGNATURES = [
    (b"PK\x03\x04", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"\x78\x9c", "zlib (default level)"),
    (b"\x78\xda", "zlib (best compression)"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"RIFF", "RIFF (WAV?)"),
    (b"ID3", "MP3 with ID3 tag"),
    (b"\xff\xfb", "MP3 frame"),
    (b"\xff\xf3", "MP3 frame"),
    (b"SQLite format 3\x00", "SQLite"),
    (b"<?xml", "XML"),
    (b"\xef\xbb\xbf", "UTF-8 byte order mark"),
    (b"\xff\xfe", "UTF-16 LE byte order mark"),
    (b"\xfe\xff", "UTF-16 BE byte order mark"),
    (b"CAMPAIGN", "CAMPAIGN (reported for .cmg by FileExt; unverified)"),
]

# Name, struct code. The manual gives 2 bytes per stored indicator, so 16-bit values are tried with
# likely scales; floats are included in case that doesn't hold.
INT16_FORMATS = [("i16-le", "<h"), ("i16-be", ">h")]
INT16_SCALES = [10, 100, 256]
FLOAT_FORMATS = [("f32-le", "<f"), ("f32-be", ">f"), ("f64-le", "<d"), ("f64-be", ">d")]

FILETIME_EPOCH = dt.datetime(1601, 1, 1)
UNIX_EPOCH = dt.datetime(1970, 1, 1)
OLE_EPOCH = dt.datetime(1899, 12, 30)


def read_limited(path, limit=SEARCH_LIMIT):
    """Returns the start of a file, and whether any of it was left out."""
    with open(path, "rb") as handle:
        data = handle.read(limit)
    return data, os.path.getsize(path) > len(data)


def walk_files(root):
    """Yields relative paths of regular files, sorted, without following links."""
    for folder, subfolders, names in os.walk(root, followlinks=False):
        subfolders.sort()
        for name in sorted(names):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and not os.path.islink(path):
                yield os.path.relpath(path, root)


def digest_and_entropy(path):
    sha = hashlib.sha256()
    counts = [0] * 256
    total = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            sha.update(chunk)
            total += len(chunk)
            for value, count in collections.Counter(chunk).items():
                counts[value] += count
    entropy = -sum(c / total * math.log2(c / total) for c in counts if c) if total else 0.0
    return sha.hexdigest(), round(entropy, 3), total


def signature_of(head):
    return next((name for magic, name in SIGNATURES if head.startswith(magic)), None)


def find_stride(data, max_lag=STRIDE_MAX_LAG):
    """Finds a likely record length: the shortest lag at which bytes keep repeating.

    Returns None when no lag stands out from the rest, which is also what compressed data gives.
    """
    size = len(data)
    if size < 64:
        return None
    scores = {}
    for lag in range(1, min(max_lag, size // 4) + 1):
        length = size - lag
        difference = int.from_bytes(data[:length], "little") ^ int.from_bytes(data[lag:], "little")
        scores[lag] = difference.to_bytes(length, "little").count(0) / length
    baseline = statistics.median(scores.values())
    best = max(scores.values())
    if best - baseline < 0.05:
        return None
    threshold = baseline + 0.9 * (best - baseline)
    lag = min(lag for lag, score in scores.items() if score >= threshold)
    return {"bytes": lag, "match": round(scores[lag], 3), "baseline": round(baseline, 3)}


def stride_sample(path, size):
    """Samples from the middle of the file, to stay clear of any header."""
    with open(path, "rb") as handle:
        handle.seek(max(0, (size - STRIDE_SAMPLE) // 2))
        return handle.read(STRIDE_SAMPLE)


def find_strings(data, minimum=4):
    found = []
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, data):
        found.append({"offset": match.start(), "encoding": "ascii", "text": match.group().decode("ascii")})
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}" % minimum, data):
        found.append({"offset": match.start(), "encoding": "utf-16-le", "text": match.group().decode("utf-16-le")})
    return sorted(found, key=lambda item: item["offset"])


def survey(root):
    files = []
    for relative in walk_files(root):
        path = os.path.join(root, relative)
        sha, entropy, size = digest_and_entropy(path)
        with open(path, "rb") as handle:
            head = handle.read(64)
        strings, truncated = read_limited(path)
        entry = {
            "path": relative,
            "size": size,
            "sha256": sha,
            "entropy": entropy,
            "signature": signature_of(head),
            "head": head[:32].hex(" "),
            "strings": len(find_strings(strings)),
            "strings_searched_all": not truncated,
            "stride": find_stride(stride_sample(path, size)),
        }
        files.append(entry)

    warnings = []
    if any(item["path"].lower().endswith(".lock") for item in files):
        warnings.append("Lock file present: this copy has been open in dBTrait, or still is. Use a fresh copy.")
    for item in files:
        if item["entropy"] >= HIGH_ENTROPY and item["size"] >= 4096 and item["signature"] is None:
            warnings.append(
                f"{item['path']}: entropy {item['entropy']} looks compressed or encrypted "
                "(or noisy audio samples). Check before searching it for values."
            )
    if not files:
        warnings.append("No files found.")
    return {"root": os.path.abspath(root), "files": files, "warnings": warnings}


def summarise_hits(offsets):
    """Describes how regularly hits are spaced. A steady gap suggests a value in repeating records."""
    gaps = collections.Counter(b - a for a, b in zip(offsets, offsets[1:]))
    gap, gap_count = gaps.most_common(1)[0] if gaps else (None, 0)
    return {
        "hits": len(offsets),
        "first_offsets": offsets[:8],
        "common_gap": gap,
        "gap_share": round(gap_count / (len(offsets) - 1), 3) if len(offsets) > 1 else 0.0,
    }


def rank(results):
    """Most regular first, so that chance matches sink to the bottom."""
    return sorted(results, key=lambda item: (item["gap_share"] * min(item["hits"], 50), item["hits"]), reverse=True)


def values_at(data, code):
    """Yields (offset, value) for a format at every byte alignment."""
    width = struct.calcsize(code)
    for start in range(width):
        count = (len(data) - start) // width
        if count <= 0:
            continue
        values = struct.unpack_from(f"{code[0]}{count}{code[1]}", data, start)
        for index, value in enumerate(values):
            yield start + index * width, value


def find_level(data, db, tol):
    """Searches for a known level, such as a 94 dB calibrator tone, in the likely encodings."""
    results = []
    for name, code in INT16_FORMATS:
        for scale in INT16_SCALES:
            low, high = (db - tol) * scale, (db + tol) * scale
            offsets = sorted(offset for offset, value in values_at(data, code) if low <= value <= high)
            if offsets:
                chance = len(data) * (high - low + 1) / 65536
                results.append({"encoding": f"{name} x{scale}", "chance_hits": round(chance, 1), **summarise_hits(offsets)})
    for name, code in FLOAT_FORMATS:
        offsets = sorted(offset for offset, value in values_at(data, code) if db - tol <= value <= db + tol)
        if offsets:
            results.append({"encoding": name, "chance_hits": 0.0, **summarise_hits(offsets)})
    return rank(results)


def find_time(data, at, window_hours):
    """Searches for a known time in common encodings.

    The window is wide enough by default to cover any time zone, and each hit shows the time it
    decodes to, so comparing that with the written log reveals local time or UTC.
    """
    window = dt.timedelta(hours=window_hours)
    low, high = at - window, at + window
    seconds = lambda moment, epoch: (moment - epoch).total_seconds()
    numeric = [
        ("unix-s u32-le", "<I", UNIX_EPOCH, 1),
        ("unix-s u32-be", ">I", UNIX_EPOCH, 1),
        ("unix-s u64-le", "<Q", UNIX_EPOCH, 1),
        ("unix-ms u64-le", "<Q", UNIX_EPOCH, 1000),
        ("filetime u64-le", "<Q", FILETIME_EPOCH, 10_000_000),
    ]
    results = []
    for name, code, epoch, per_second in numeric:
        lowest, highest = seconds(low, epoch) * per_second, seconds(high, epoch) * per_second
        hits = sorted((offset, value) for offset, value in values_at(data, code) if lowest <= value <= highest)
        if hits:
            chance = 0.0
            if code[1] == "I":
                chance = len(data) * (highest - lowest) / 2**32
            decoded = epoch + dt.timedelta(seconds=hits[0][1] / per_second)
            results.append(
                {"encoding": name, "chance_hits": round(chance, 1), "first_decoded": decoded.isoformat(), **summarise_hits([h[0] for h in hits])}
            )

    lowest, highest = seconds(low, OLE_EPOCH) / 86400, seconds(high, OLE_EPOCH) / 86400
    hits = sorted((offset, value) for offset, value in values_at(data, "<d") if lowest <= value <= highest)
    if hits:
        decoded = OLE_EPOCH + dt.timedelta(days=hits[0][1])
        results.append({"encoding": "ole-date f64-le", "chance_hits": 0.0, "first_decoded": decoded.isoformat(), **summarise_hits([h[0] for h in hits])})

    systemtime = struct.pack("<HH", at.year, at.month)
    hits = [m.start() for m in re.finditer(re.escape(systemtime), data)]
    if hits:
        results.append({"encoding": "year,month u16-le (SYSTEMTIME?)", "chance_hits": 0.0, "first_decoded": None, **summarise_hits(hits)})

    for text in (at.strftime("%Y-%m-%d"), at.strftime("%Y%m%d"), at.strftime("%d/%m/%Y"), at.strftime("%Y/%m/%d")):
        for encoding in ("ascii", "utf-16-le"):
            hits = [m.start() for m in re.finditer(re.escape(text.encode(encoding)), data)]
            if hits:
                results.append({"encoding": f"text {text} {encoding}", "chance_hits": 0.0, "first_decoded": None, **summarise_hits(hits)})
    return rank(results)


def difference_regions(first, second, limit=20):
    """Lists the byte ranges that differ between two files, as far as both go."""
    regions = []
    start = None
    length = min(len(first), len(second))
    for offset in range(length):
        if first[offset] != second[offset]:
            if start is None:
                start = offset
        elif start is not None:
            regions.append([start, offset - start])
            start = None
    if start is not None:
        regions.append([start, length - start])
    return regions[:limit], len(regions)


def compare(root_a, root_b):
    files_a, files_b = set(walk_files(root_a)), set(walk_files(root_b))
    changed = []
    same = 0
    for relative in sorted(files_a & files_b):
        first, first_cut = read_limited(os.path.join(root_a, relative))
        second, second_cut = read_limited(os.path.join(root_b, relative))
        if first == second and not first_cut and not second_cut:
            same += 1
            continue
        regions, total = difference_regions(first, second)
        changed.append(
            {
                "path": relative,
                "size_a": os.path.getsize(os.path.join(root_a, relative)),
                "size_b": os.path.getsize(os.path.join(root_b, relative)),
                "regions": regions,
                "region_count": total,
                "compared_all": not (first_cut or second_cut),
            }
        )
    return {"only_a": sorted(files_a - files_b), "only_b": sorted(files_b - files_a), "identical": same, "changed": changed}


def print_survey(report):
    print(report["root"])
    for item in report["files"]:
        stride = f"stride {item['stride']['bytes']}" if item["stride"] else "no stride"
        signature = item["signature"] or "no known signature"
        print(f"  {item['path']}\n    {item['size']} bytes, entropy {item['entropy']}, {signature}, {stride}, {item['strings']} strings")
        print(f"    {item['head']}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")


def print_hits(results):
    if not results:
        print("No matches.")
    for item in results:
        decoded = f", first decodes to {item['first_decoded']}" if item.get("first_decoded") else ""
        print(
            f"{item['encoding']}: {item['hits']} hits (about {item['chance_hits']} by chance), "
            f"common gap {item['common_gap']} ({item['gap_share']:.0%}), first at {item['first_offsets']}{decoded}"
        )


def print_compare(report):
    print(f"{report['identical']} identical")
    for path in report["only_a"]:
        print(f"only in A: {path}")
    for path in report["only_b"]:
        print(f"only in B: {path}")
    for item in report["changed"]:
        print(f"changed: {item['path']} ({item['size_a']} -> {item['size_b']} bytes), {item['region_count']} regions")
        print(f"  [offset, length]: {item['regions']}")
        if not item["compared_all"]:
            print(f"  only the first {SEARCH_LIMIT} bytes were compared")


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="noise fusion", description="Inspect Fusion session folders, read-only.")
    parser.add_argument("--json", action="store_true", help="print JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("survey", help="list files with sizes, checksums, entropy and record lengths")
    command.add_argument("session")
    command.add_argument("--out", help="also save the report as JSON, outside the session folder")

    command = commands.add_parser("strings", help="list ASCII and UTF-16 text in a file")
    command.add_argument("file")
    command.add_argument("--min", type=int, default=4)

    command = commands.add_parser("level", help="search a file for a known level")
    command.add_argument("file")
    command.add_argument("--db", type=float, required=True)
    command.add_argument("--tol", type=float, default=0.5)

    command = commands.add_parser("time", help="search a file for a known time")
    command.add_argument("file")
    command.add_argument("--at", type=dt.datetime.fromisoformat, required=True)
    command.add_argument("--window-hours", type=float, default=14)

    command = commands.add_parser("compare", help="compare two session folders")
    command.add_argument("session_a")
    command.add_argument("session_b")
    return parser.parse_args(argv)


def is_inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return os.path.commonpath([path, folder]) == folder


def main(argv=None):
    args = parse_args(argv)
    note = None
    if args.command == "survey":
        if args.out and is_inside(args.out, args.session):
            sys.exit("--out must be outside the session folder, which this tool never changes.")
        report, show = survey(args.session), print_survey
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
    elif args.command == "compare":
        report, show = compare(args.session_a, args.session_b), print_compare
    else:
        data, truncated = read_limited(args.file)
        if truncated:
            note = f"Only the first {SEARCH_LIMIT} bytes were searched."
        if args.command == "strings":
            report = find_strings(data, args.min)
            show = lambda found: [print(f"{s['offset']:>10}  {s['encoding']:<9}  {s['text']}") for s in found]
        elif args.command == "level":
            report, show = find_level(data, args.db, args.tol), print_hits
        else:
            report, show = find_time(data, args.at, args.window_hours), print_hits

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        show(report)
    if note:
        print(note, file=sys.stderr)


if __name__ == "__main__":
    main()

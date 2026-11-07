"""Tests for fusion.inspector, using made-up files. They don't show anything about the real format.

Run with `make test`, or from tools/fusion with: python3 -m unittest discover tests
"""

import datetime as dt
import hashlib
import os
import random
import struct
import tempfile
import unittest

from fusion import inspector as fi

START = dt.datetime(2026, 11, 5, 14, 30, 0)
UNIX_START = int((START - dt.datetime(1970, 1, 1)).total_seconds())
RECORD = 8
RECORDS = 500
OFFSET_OF_LEVEL = 4


def records(level_tenths=940):
    """Records of a Unix time, a level in tenths of a dB and a constant, with a little level noise."""
    noise = random.Random(1)
    return b"".join(
        struct.pack("<IhH", UNIX_START + i, level_tenths + noise.randint(-2, 2), 7) for i in range(RECORDS)
    )


def write_session(root, bid=None, extra=None):
    os.makedirs(os.path.join(root, "Settings"))
    files = {
        "TEST.cmg": b"CAMPAIGN\x00" + "Leq".encode("utf-16-le") + b"\x00\x00" + b"\x01" * 40,
        "TEST_1.bid": records() if bid is None else bid,
        os.path.join("Settings", "config.xml"): b'<?xml version="1.0"?><config/>',
    }
    files.update(extra or {})
    for relative, content in files.items():
        with open(os.path.join(root, relative), "wb") as handle:
            handle.write(content)


def snapshot(root):
    state = {}
    for relative in fi.walk_files(root):
        path = os.path.join(root, relative)
        with open(path, "rb") as handle:
            state[relative] = (hashlib.sha256(handle.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return state


class SessionCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = folder.name
        self.session = os.path.join(self.root, "session")
        os.makedirs(self.session)
        write_session(self.session)

    def test_survey_lists_files_with_signatures_and_record_length(self):
        files = {item["path"]: item for item in fi.survey(self.session)["files"]}
        self.assertEqual(set(files), {"TEST.cmg", "TEST_1.bid", os.path.join("Settings", "config.xml")})
        self.assertEqual(files["TEST.cmg"]["signature"], "CAMPAIGN (reported for .cmg by FileExt; unverified)")
        self.assertEqual(files["TEST_1.bid"]["stride"]["bytes"], RECORD)
        self.assertEqual(files["TEST_1.bid"]["size"], RECORD * RECORDS)
        with open(os.path.join(self.session, "TEST_1.bid"), "rb") as handle:
            self.assertEqual(files["TEST_1.bid"]["sha256"], hashlib.sha256(handle.read()).hexdigest())

    def test_nothing_changes_the_session(self):
        before = snapshot(self.session)
        bid = os.path.join(self.session, "TEST_1.bid")
        fi.main(["survey", self.session, "--out", os.path.join(self.root, "report.json")])
        fi.main(["strings", bid])
        fi.main(["level", bid, "--db", "94"])
        fi.main(["time", bid, "--at", START.isoformat()])
        fi.main(["compare", self.session, self.session])
        self.assertEqual(snapshot(self.session), before)

    def test_report_cannot_be_written_into_the_session(self):
        with self.assertRaises(SystemExit):
            fi.main(["survey", self.session, "--out", os.path.join(self.session, "report.json")])
        self.assertNotIn("report.json", os.listdir(self.session))

    def test_lock_file_gives_a_warning(self):
        with open(os.path.join(self.session, "TEST.cmg.lock"), "wb"):
            pass
        self.assertTrue(any("Lock file" in w for w in fi.survey(self.session)["warnings"]))

    def test_compare_finds_added_files_and_changed_bytes(self):
        other = os.path.join(self.root, "other")
        os.makedirs(other)
        changed = bytearray(records())
        changed[100:102] = b"\xff\xff"
        write_session(other, bytes(changed), {"Extra.bid": b"new"})
        report = fi.compare(self.session, other)
        self.assertEqual(report["only_b"], ["Extra.bid"])
        self.assertEqual(report["identical"], 2)
        self.assertEqual(report["changed"][0]["path"], "TEST_1.bid")
        self.assertEqual(report["changed"][0]["regions"], [[100, 2]])


class SearchCase(unittest.TestCase):
    def test_level_search_ranks_true_encoding_first_with_its_spacing(self):
        best = fi.find_level(records(), 94.0, 0.5)[0]
        self.assertEqual(best["encoding"], "i16-le x10")
        self.assertEqual(best["hits"], RECORDS)
        self.assertEqual(best["common_gap"], RECORD)
        self.assertEqual(best["first_offsets"][0], OFFSET_OF_LEVEL)

    def test_float_levels_are_found(self):
        data = b"".join(struct.pack(">f", 94.0) + b"\x00\x00" for _ in range(50))
        self.assertEqual(fi.find_level(data, 94.0, 0.1)[0]["encoding"], "f32-be")

    def test_absent_level_finds_nothing_regular(self):
        results = fi.find_level(bytes(8000), 94.0, 0.5)
        self.assertEqual(results, [])

    def test_time_search_decodes_unix_time(self):
        best = fi.find_time(records(), START, 14)[0]
        self.assertEqual(best["encoding"], "unix-s u32-le")
        self.assertEqual(best["hits"], RECORDS)
        self.assertEqual(best["common_gap"], RECORD)
        self.assertEqual(best["first_decoded"], START.isoformat())

    def test_time_search_decodes_filetime_and_ole(self):
        filetime = int((START - fi.FILETIME_EPOCH).total_seconds()) * 10_000_000
        result = fi.find_time(b"\x00\x01\x02" + struct.pack("<Q", filetime) + b"\x03", START, 14)
        self.assertEqual(result[0]["encoding"], "filetime u64-le")
        self.assertEqual(result[0]["first_offsets"], [3])
        self.assertEqual(result[0]["first_decoded"], START.isoformat())

        days = (START - fi.OLE_EPOCH).total_seconds() / 86400
        result = fi.find_time(struct.pack("<d", days), START, 14)
        self.assertIn("ole-date f64-le", [item["encoding"] for item in result])

    def test_time_search_finds_utc_offset_by_decoding_it(self):
        one_hour_off = struct.pack("<I", UNIX_START - 3600) * 20
        best = fi.find_time(one_hour_off, START, 14)[0]
        self.assertEqual(best["first_decoded"], (START - dt.timedelta(hours=1)).isoformat())


class ShapeCase(unittest.TestCase):
    def test_random_bytes_have_high_entropy_and_no_stride(self):
        data = random.Random(2).randbytes(STRIDE_BYTES)
        self.assertIsNone(fi.find_stride(data))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "noise.bid")
            with open(path, "wb") as handle:
                handle.write(data)
            warnings = fi.survey(folder)["warnings"]
        self.assertTrue(any("compressed or encrypted" in w for w in warnings))

    def test_strings_finds_both_encodings(self):
        found = fi.find_strings(b"\x00\x01Leq slow\xff" + "Spectrum".encode("utf-16-le") + b"\xff")
        self.assertEqual([(s["encoding"], s["text"]) for s in found], [("ascii", "Leq slow"), ("utf-16-le", "Spectrum")])

    def test_empty_folder_and_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("No files found.", fi.survey(folder)["warnings"])
            open(os.path.join(folder, "empty.bid"), "wb").close()
            item = fi.survey(folder)["files"][0]
        self.assertEqual((item["size"], item["entropy"], item["stride"]), (0, 0.0, None))


STRIDE_BYTES = 64 * 1024

if __name__ == "__main__":
    unittest.main()

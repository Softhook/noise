"""Tests for adsb metars, without the network."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import urllib.parse
from unittest import mock

from adsb import metars
from adsb.common import parse_utc
from adsb.weather import Weather

CSV = (
    "station,valid,metar\n"
    "EGLC,2026-10-27 23:50,EGLC 272350Z AUTO 20011KT 9999 OVC030 17/13 Q1005\n"
    "EGLC,2026-10-28 00:20,EGLC 280020Z AUTO 20011KT 9999 OVC030 17/13 Q1006\n"
    "EGLC,2026-10-28 00:35,EGLC 280035Z NIL\n"
)


class Metars(unittest.TestCase):
    def test_url_asks_for_a_day_either_side_in_utc(self):
        url = metars.metar_url("EGLC", parse_utc("2026-10-28"), parse_utc("2026-11-01"))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual([query[k][0] for k in ("year1", "month1", "day1")], ["2026", "10", "27"])
        self.assertEqual([query[k][0] for k in ("year2", "month2", "day2")], ["2026", "11", "2"])
        self.assertEqual((query["station"], query["tz"], query["report_type"]), (["EGLC"], ["Etc/UTC"], ["3", "4"]))

    def test_check_counts_reports_with_a_qnh(self):
        self.assertEqual(metars.check(CSV), 2)
        for bad in ("", "<html>Too many requests</html>", "station,valid\nEGLC,2026-10-28 00:20\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                metars.check(bad)

    def test_main_writes_a_file_the_analysis_reads(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = CSV.encode()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", return_value=response), \
                mock.patch("sys.stdout", io.StringIO()):
            out = os.path.join(tmp, "eglc.csv")
            self.assertEqual(metars.main(["--from", "2026-10-28", "--to", "2026-10-29", "--out", out]), 0)
            weather = Weather.load(out)
        self.assertEqual(weather.at(parse_utc("2026-10-28 00:30"))[0], 1006.5)  # Rounded-down QNH, plus 0.5

    def test_main_refuses_a_response_without_reports(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"station,valid,metar\n"
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", return_value=response), \
                mock.patch("sys.stderr", io.StringIO()):
            out = os.path.join(tmp, "eglc.csv")
            self.assertEqual(metars.main(["--from", "2026-10-28", "--to", "2026-10-29", "--out", out]), 1)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()

"""The noise command, and that every tool agrees where the data is. No network.

Run with `make test`, or from tools/noise with: python -m unittest discover tests
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from noise import cli  # noqa: E402

# Each tool works out the data folder itself, so they stay independent; this is what they say
WHERE = {
    "survey": ("survey", "from survey import paths; print(paths.DATA_DIR)"),
    "webtrak": ("webtrak", "from webtrak import __main__ as m; print(os.path.dirname(os.path.dirname(m.DEFAULT_RAW)))"),
    "opensky": ("opensky", "from opensky import common; print(common.DATA_DIR)"),
}


def data_dirs(env):
    found = {}
    for name, (tool, code) in WHERE.items():
        out = subprocess.run([sys.executable, "-c", "import os; " + code], cwd=os.path.join(TOOLS, tool),
                             env=env, capture_output=True, text=True, check=True)
        found[name] = out.stdout.strip()
    make = subprocess.run(["make", "-s", "-C", REPO, "print-data"], env=env, capture_output=True, text=True, check=True)
    found["Makefile"] = make.stdout.strip()
    return found


class DataFolder(unittest.TestCase):
    def test_every_tool_and_the_makefile_agree_on_the_data_folder(self):
        env = {k: v for k, v in os.environ.items() if k != "NOISE_DATA"}
        self.assertEqual(set(data_dirs(env).values()), {os.path.join(REPO, "data")})

    def test_and_all_follow_noise_data(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            self.assertEqual(set(data_dirs({**os.environ, "NOISE_DATA": elsewhere}).values()), {elsewhere})


class Command(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_help_and_unknown_commands(self):
        code, out, _ = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("build [DEPLOYMENT ...]", out)
        code, _, err = self.run_cli(["nonsense"])
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_survey_commands_and_tools_go_to_their_packages(self):
        calls = []

        class Module:
            def __init__(self, name):
                self.name = name

            def main(self, argv):
                calls.append((self.name, argv))
                return 0

        with mock.patch.object(cli.importlib, "import_module", side_effect=Module):
            for argv in (["build", "2026-11-05"], ["serve"], ["sql", "2026-11-05"], ["webtrak", "range"], ["fusion", "strings", "f"],
                         ["adsb", "status"], ["opensky", "logs"]):
                self.assertEqual(self.run_cli(argv)[0], 0)
        self.assertEqual(calls, [
            ("survey.__main__", ["build", "2026-11-05"]), ("survey.__main__", ["serve"]),
            ("survey.__main__", ["sql", "2026-11-05"]),
            ("webtrak.__main__", ["range"]), ("fusion.inspector", ["strings", "f"]),
            ("adsb.__main__", ["status"]), ("opensky.__main__", ["logs"])])

    def test_a_copy_outside_the_repository_refuses_to_run(self):
        with mock.patch.object(cli, "REPO", tempfile.gettempdir()):
            code, _, err = self.run_cli(["build"])
        self.assertEqual(code, 2)
        self.assertIn("make setup", err)


if __name__ == "__main__":
    unittest.main()

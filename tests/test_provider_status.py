"""`media doctor` provider-status reporting.

Kept separate from the normalization tests because it exercises the CLI surface
and the VERIFIED_PROVIDERS list, not a provider response mapping.

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from media_tool import cli  # noqa: E402
from media_tool.config import KNOWN_PROVIDERS, VERIFIED_PROVIDERS  # noqa: E402


class ProviderStatusReportingTests(unittest.TestCase):
    """`media doctor` must not drift from the documented verification status."""

    def test_doctor_status_matches_the_verified_provider_list(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main(["doctor"])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertEqual(set(report["providers"]), set(KNOWN_PROVIDERS))
        for name, entry in report["providers"].items():
            expected = name in VERIFIED_PROVIDERS
            self.assertEqual(entry["verified"], expected, name)
            self.assertEqual(
                entry["status"],
                "IMPLEMENTED+VERIFIED" if expected else "IMPLEMENTED+UNVERIFIED",
            )


if __name__ == "__main__":
    unittest.main()

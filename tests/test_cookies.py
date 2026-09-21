"""Optional Netscape cookies login-state tests.

Covers the contract of `[cookies] file`:
  * unset / empty / commented-out  -> fully anonymous, no `--cookies` anywhere;
  * configured + valid file        -> every yt-dlp call gets `--cookies <path>`
    (metadata, subtitles, audio download);
  * configured + broken file       -> a clear error, never silent pretend;
  * `media doctor`                 -> local-only checks, never fails, never
    prints cookie contents;
  * logs                           -> cookie values/paths are redacted.

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from media_tool import cli  # noqa: E402
from media_tool.config import Config  # noqa: E402
from media_tool.urls import identify  # noqa: E402
from media_tool.util import ConfigurationError  # noqa: E402
from media_tool.ytdlp import YtDlp  # noqa: E402

FAKE_COOKIE_VALUE = "session=LEAKPROOF_cookie_value_9f3a"

COOKIE_FILE_CONTENT = (
    "# Netscape HTTP Cookie File\n"
    ".example.com\tTRUE\t/\tFALSE\t0\tsession\tLEAKPROOF_cookie_value_9f3a\n"
)


def _write_config(tmp: Path, cookies_file: str | None = None, *, empty: bool = False) -> None:
    lines = ["[cookies]"]
    if cookies_file is None:
        if empty:
            lines.append("file =")
    else:
        lines.append(f"file = {cookies_file}")
    (tmp / "config.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cookie_path(tmp: Path, mode: int = 0o600) -> Path:
    path = tmp / "cookies.txt"
    path.write_text(COOKIE_FILE_CONTENT, encoding="utf-8")
    path.chmod(mode)
    return path


class RunRecorder:
    """Replaces media_tool.ytdlp.run: records args, returns a stub process."""

    def __init__(self, *, stdout: str = "{}", returncode: int = 0, stderr: str = ""):
        self.calls: list[list[str]] = []
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, cmd, *, timeout=1800, check=True, quiet=False):
        self.calls.append(list(cmd))
        return type(
            "Proc", (), {"stdout": self.stdout, "stderr": self.stderr, "returncode": self.returncode}
        )()


def _patched_ytdlp(tmp: Path) -> tuple[YtDlp, RunRecorder, unittest.mock._patch]:
    recorder = RunRecorder()
    patcher = unittest.mock.patch("media_tool.ytdlp.run", recorder)
    patcher.start()
    return YtDlp(Config(root=tmp)), recorder, patcher


class CookieConfigTests(unittest.TestCase):
    """`[cookies] file` is the single source of truth for login state."""

    def test_no_section_means_anonymous(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(Config(root=Path(tmp)).cookies_file)

    def test_section_without_file_option_means_anonymous(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _write_config(path)
            self.assertIsNone(Config(root=path).cookies_file)

    def test_empty_value_means_anonymous(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _write_config(path, empty=True)
            self.assertIsNone(Config(root=path).cookies_file)

    def test_stray_cookies_file_without_config_stays_anonymous(self):
        # Pins the removal of any implicit fallback: dropping a cookies.txt at
        # the project root must NOT activate login state by itself.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _cookie_path(path)
            self.assertIsNone(Config(root=path).cookies_file)

    def test_configured_path_is_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path)
            _write_config(path, str(target))
            self.assertEqual(Config(root=path).cookies_file, target)


class YtDlpCookieInjectionTests(unittest.TestCase):
    """The unified `_base_args` layer feeds `--cookies` to every yt-dlp call."""

    def test_anonymous_base_args_have_no_cookie_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _write_config(path)
            ytdlp, _, patcher = _patched_ytdlp(path)
            self.addCleanup(patcher.stop)
            self.assertNotIn("--cookies", ytdlp._base_args())

    def test_configured_base_args_carry_cookie_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path)
            _write_config(path, str(target))
            ytdlp, _, patcher = _patched_ytdlp(path)
            self.addCleanup(patcher.stop)
            args = ytdlp._base_args()
            self.assertEqual(args[args.index("--cookies") + 1], str(target))

    def test_anonymous_invocations_have_no_cookie_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _write_config(path)
            ytdlp, recorder, patcher = _patched_ytdlp(path)
            self.addCleanup(patcher.stop)
            ytdlp.probe("https://example.com/v", timeout=5)
            self.assertEqual(len(recorder.calls), 1)
            self.assertNotIn("--cookies", recorder.calls[0])

    def test_all_network_paths_carry_cookies(self):
        # metadata (probe), subtitles and audio download must each receive
        # --cookies — no path may silently miss the login state.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path)
            _write_config(path, str(target))
            ytdlp, recorder, patcher = _patched_ytdlp(path)
            self.addCleanup(patcher.stop)

            ytdlp.probe("https://example.com/v", timeout=5)
            with tempfile.TemporaryDirectory() as work:
                ytdlp.download_subtitles("https://example.com/v", Path(work), timeout=5)
            audio = path / "audio.mp3"
            audio.write_bytes(b"ID3")
            ytdlp.download_audio("https://example.com/v", audio, timeout=5)

            self.assertEqual(len(recorder.calls), 3)
            for args in recorder.calls:
                self.assertEqual(args[args.index("--cookies") + 1], str(target), args)


class BrokenCookieConfigTests(unittest.TestCase):
    """A configured-but-broken cookie file fails loudly, never silently."""

    def test_missing_file_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            missing = path / "nope.txt"
            _write_config(path, str(missing))
            ytdlp = YtDlp(Config(root=path))
            with self.assertRaises(ConfigurationError) as ctx:
                ytdlp._base_args()
            message = str(ctx.exception)
            self.assertIn("cookies file not found", message)
            self.assertIn(str(missing), message)

    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = path / "cookies-dir"
            target.mkdir()
            _write_config(path, str(target))
            ytdlp = YtDlp(Config(root=path))
            with self.assertRaises(ConfigurationError) as ctx:
                ytdlp._base_args()
            self.assertIn("not a regular file", str(ctx.exception))

    def test_unreadable_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = path / "locked.txt"
            target.write_text(COOKIE_FILE_CONTENT, encoding="utf-8")
            target.chmod(0o000)
            _write_config(path, str(target))
            ytdlp = YtDlp(Config(root=path))
            with self.assertRaises(ConfigurationError) as ctx:
                ytdlp._base_args()
            self.assertIn("not readable", str(ctx.exception))

    def test_missing_file_also_fails_probe(self):
        # The guard lives in _base_args, so real entry points fail the same way.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            _write_config(path, str(path / "missing.txt"))
            ytdlp = YtDlp(Config(root=path))
            with self.assertRaises(ConfigurationError):
                ytdlp.probe("https://example.com/v", timeout=5)


class DoctorCookieTests(unittest.TestCase):
    """`media doctor` reports cookie state locally, never failing on it."""

    def _doctor(self, tmp: Path) -> dict:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), unittest.mock.patch(
            "media_tool.cli.Config", lambda: Config(root=tmp)
        ):
            code = cli.main(["doctor"])
        self.assertEqual(code, 0)  # cookie warnings/problems never fail doctor
        return json.loads(buffer.getvalue())

    def test_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._doctor(Path(tmp))["cookies"]
            self.assertFalse(report["configured"])
            self.assertEqual(report["status"], "not_configured")
            self.assertIsNone(report["file"])
            self.assertIsNone(report["message"])

    def test_configured_and_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path, mode=0o600)
            _write_config(path, str(target))
            report = self._doctor(path)["cookies"]
            self.assertTrue(report["configured"])
            self.assertEqual(report["status"], "configured")
            self.assertEqual(report["file"], str(target))
            self.assertIsNone(report["message"])
            self.assertEqual(report["warnings"], [])

    def test_configured_but_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            missing = path / "missing.txt"
            _write_config(path, str(missing))
            report = self._doctor(path)["cookies"]
            self.assertTrue(report["configured"])
            self.assertEqual(report["status"], "problem")
            self.assertIn("not found", report["message"])

    def test_permission_warning_but_still_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path, mode=0o644)
            _write_config(path, str(target))
            report = self._doctor(path)["cookies"]
            self.assertEqual(report["status"], "configured")
            self.assertTrue(any("chmod 600" in w for w in report["warnings"]))

    def test_doctor_never_prints_cookie_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path)
            _write_config(path, str(target))
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), unittest.mock.patch(
                "media_tool.cli.Config", lambda: Config(root=tmp)
            ):
                cli.main(["doctor"])
            self.assertNotIn(FAKE_COOKIE_VALUE, buffer.getvalue())


class LogLeakTests(unittest.TestCase):
    """Cookie values and paths never reach the command log."""

    def test_command_logline_redacts_cookie_value(self):
        from media_tool.util import _command_logline

        cmd = ["yt-dlp", "--no-progress", "--cookies", FAKE_COOKIE_VALUE, "--dump-single-json", "https://x"]
        line = _command_logline(cmd)
        self.assertNotIn(FAKE_COOKIE_VALUE, line)
        self.assertIn("--cookies", line)
        self.assertIn("<redacted>", line)

    def test_real_run_logging_redacts_cookie_value(self):
        import tempfile

        from media_tool import util

        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "cookies.txt")
            captured: list[str] = []
            with unittest.mock.patch("media_tool.util.log", side_effect=captured.append):
                util.run(["echo", "--cookies", target])
            self.assertTrue(captured)
            for line in captured:
                self.assertNotIn(target, line)
                self.assertIn("<redacted>", line)

    def test_probe_log_line_never_exposes_cookie_path(self):
        # Whatever the arg layout, the log line `util.run` would print for a
        # real probe contains neither the cookie path nor any cookie content.
        from media_tool.util import _command_logline

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            target = _cookie_path(path)
            _write_config(path, str(target))
            ytdlp = YtDlp(Config(root=path))
            line = _command_logline(ytdlp._base_args() + ["--dump-single-json", "https://x"])
            self.assertNotIn(str(target), line)
            self.assertNotIn(FAKE_COOKIE_VALUE, line)


if __name__ == "__main__":
    unittest.main()

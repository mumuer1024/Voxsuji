"""yt-dlp wrapper: metadata, subtitles and audio."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config, cookies_file_problem
from .util import CommandError, ConfigurationError, log, run


class YtDlp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.bin = config.ytdlp_bin

    def available(self) -> bool:
        return bool(shutil.which(self.bin) or Path(self.bin).is_file())

    def _base_args(self) -> list[str]:
        args = [self.bin, "--no-progress", "--no-warnings", "--ignore-config", "--no-playlist"]
        cookies = self.config.cookies_file
        if cookies:
            problem = cookies_file_problem(cookies)
            if problem:
                # A configured-but-broken cookie file must fail loudly, never
                # silently pretend login state is in use.
                raise ConfigurationError(
                    f"{problem} — fix [cookies] file in config.ini, "
                    "or remove the setting to run anonymously"
                )
            args += ["--cookies", str(cookies)]
        # Route yt-dlp through an explicit proxy only when one is configured.
        proxy = self.config.get("YTDLP_PROXY")
        if proxy:
            args += ["--proxy", proxy]
        return args

    # -- metadata ---------------------------------------------------------
    def probe(self, url: str, *, timeout: float = 300) -> dict:
        proc = run(self._base_args() + ["--dump-single-json", "--skip-download", url], timeout=timeout)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise CommandError(f"yt-dlp did not return JSON metadata for {url}: {exc}") from exc

    # -- subtitles --------------------------------------------------------
    def download_subtitles(self, url: str, workdir: Path, *, timeout: float = 600) -> dict:
        """Download all available subtitles; returns yt-dlp's info dict."""
        outtmpl = str(workdir / "sub")
        args = self._base_args() + [
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "all",
            "--sub-format",
            "json3/vtt/srt/best",
            "--convert-subs",
            "vtt",
            "-o",
            outtmpl,
            "--print-json",
            url,
        ]
        proc = run(args, timeout=timeout, check=False)
        info = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    info = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if info is None and proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-8:]
            log("yt-dlp subtitle pass failed: " + " | ".join(tail))
        return info or {}

    # -- audio ------------------------------------------------------------
    def download_audio(self, url: str, out_path: Path, *, timeout: float = 3600) -> Path:
        """Download the best audio stream and transcode it to ASR-ready mp3.

        yt-dlp appends the final container extension, so `out_path` must already
        carry the `.mp3` suffix and is what the caller gets back.
        """
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args = self._base_args() + [
            "-f",
            "bestaudio/best",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "64K",
            "--postprocessor-args",
            "ffmpeg:-ac 1 -ar 16000",
            "-o",
            str(out_path),
            url,
        ]
        run(args, timeout=timeout)
        if not out_path.is_file() or out_path.stat().st_size == 0:
            # Fall back to whatever mp3 yt-dlp may have produced alongside it.
            candidates = sorted(out_path.parent.glob("audio*.mp3"))
            if len(candidates) == 1:
                candidates[0].replace(out_path)
            else:
                raise CommandError(
                    f"audio download produced no file at {out_path} "
                    f"(found: {[p.name for p in out_path.parent.glob('*')]})"
                )
        return out_path


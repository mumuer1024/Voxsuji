# media

Turn an online video URL into **structured, cacheable text**: a transcript
(platform subtitles first, cloud ASR only as a fallback), written out as
JSON, Markdown and SRT.

```
URL → yt-dlp metadata → existing subtitles when available
    → otherwise audio extraction → temporary S3-compatible object upload
    → cloud ASR → normalized transcript → JSON / Markdown / SRT
```

## What it is

- A small CLI that produces a transcript from a video URL.
- Subtitle-first: if the platform already has a usable subtitle track, it is
  used and no paid ASR call is made.
- ASR fallback: when there are no usable subtitles, the audio is transcribed
  by one of three cloud speech-recognition providers (Aliyun Bailian,
  Volcengine, Tencent Cloud) that you configure yourself.
- Cached on the local filesystem, so re-runs are free.

## What it is not

- Not a video downloader UI.
- Not a website-specific client.
- Not a comments or danmaku tool.
- Not an LLM summarization service — it only produces transcripts. Feed the
  transcript to any LLM you prefer.
- Not a hosted service. It runs entirely on your machine.

## Requirements

- Python 3.10 or newer (developed on 3.13).
- `ffmpeg` and `ffprobe` on `PATH` (used to extract and normalize audio).
- `yt-dlp` (installed automatically into the project virtualenv by the
  launcher, or install it yourself).
- Network access to the video platform and to the ASR/storage services.
- **One configured ASR provider** — needed only for the ASR fallback path
  (videos without usable subtitles).
- **An S3-compatible object storage bucket** — also only for the ASR fallback
  path. ASR providers fetch the audio by public URL, so the tool uploads the
  audio to a temporary object in your own bucket, verifies it is anonymously
  readable, then deletes it right after transcription.

If a video already has usable subtitles, neither an ASR provider nor storage
is required.

## Installation

Clone the repository and run the launcher. It creates a project-local
virtualenv and installs `yt-dlp` on first use — nothing is installed
system-wide.

```bash
git clone <this-repo> && cd media
sudo apt-get install -y --no-install-recommends ffmpeg ffprobe   # or your OS equivalent
./bin/media doctor
```

Put the launcher on your `PATH` if you like:

```bash
ln -s "$(pwd)/bin/media" /usr/local/bin/media
```

## Configuration

Configuration is a merge of environment variables, a git-ignored `.env` file
at the project root, and non-secret settings in `config.ini` (see
`config.example.ini`).

```bash
cp .env.example .env && chmod 600 .env && $EDITOR .env
cp config.example.ini config.ini && $EDITOR config.ini
./bin/media doctor    # shows what is configured; never prints secrets
```

### ASR providers

You only need to configure the provider you actually use. An unconfigured
provider does not affect the others.

| provider | variables | default provider |
| --- | --- | --- |
| `aliyun` | `DASHSCOPE_API_KEY` (+ optional `DASHSCOPE_BASE_URL`) | yes |
| `volcengine` | `VOLC_API_KEY`, or `VOLC_APP_ID` + `VOLC_ACCESS_TOKEN` (+ optional `VOLC_RESOURCE_ID`) | no |
| `tencent` | `TENCENT_SECRET_ID`, `TENCENT_SECRET_KEY` (+ optional `TENCENT_REGION`, `TENCENT_TOKEN`) | no |

`default_provider` is set in `config.ini` (`[asr] default_provider`), and any
provider can be chosen per run with `--provider`. Missing credentials for the
chosen provider fail explicitly (exit code 3) — there is no silent fallback to
another provider.

Provider APIs, models, pricing, quotas and availability may change over time.
Configuration is best-effort and documented as verified at the project release
date. See `docs/PROVIDERS.md` for details.

### Storage (S3-compatible object storage)

The ASR fallback needs a bucket that is **publicly readable** (the ASR
provider fetches the audio by URL). You provide your own bucket and
credentials — media does not host or manage object storage.

```text
STORAGE_ENDPOINT=https://s3.example.com
STORAGE_REGION=example-region
STORAGE_BUCKET=your-bucket
STORAGE_ACCESS_KEY=your-access-key
STORAGE_SECRET_KEY=your-secret-key
```

What media does with your bucket:

1. uploads the audio to a temporary object with a random key
   (`asr-tmp/<random>.mp3`);
2. verifies the object is anonymously readable (so the ASR provider can fetch
   it);
3. deletes the object in a `finally` block as soon as transcription finishes
   (or fails).

The temporary object is only alive for the duration of one run. Costs for
storage, network and ASR usage are yours.

### Optional: cookies for authenticated yt-dlp sources

Some sources serve more (or any) data to a logged-in session. You can supply
a **Netscape-format cookies.txt**; media passes it to **every** yt-dlp call
via `--cookies`.

```ini
[cookies]
file = /path/to/cookies.txt
```

- Leave `file` unset or commented out to run anonymously — no error, no
  behaviour change.
- Export the cookies file yourself from a browser where you are logged in;
  media never logs you in and never refreshes cookies.
- Protect the file (`chmod 600`) and never commit it. Media reads it in
  memory, never prints or logs its contents, and never rewrites it.
- `media doctor` reports the path plus local file checks only.

## Usage

```bash
media transcript <URL>                    # subtitles if available, else ASR
media transcript <URL> --provider aliyun  # explicit provider
media transcript <URL> --language zh      # language hint for ASR
media transcript <URL> --force-asr        # ignore platform subtitles
media transcript <URL> --refresh          # ignore the cache
media doctor                              # dependency + configuration status
```

Add `--json` for the machine-readable JSON summary on stdout.

### Output contract

stdout is always a single compact JSON summary — transcripts are never dumped
in full, so a long video cannot flood a terminal or agent context. Read the
files for the actual text:

```json
{
  "ok": true, "cached": false,
  "source_url": "...", "platform": "youtube", "video_id": "...",
  "title": "...", "duration": 212.3,
  "transcript_source": "subtitle", "provider": null, "model": null,
  "language": null, "segment_count": 19, "char_count": 1632,
  "word_timestamps": false,
  "files": {"json": "...", "markdown": "...", "srt": "..."}
}
```

On failure: `{"ok": false, "error": {"type": ..., "message": ...}}`.

Exit codes: `0` success · `1` command/pipeline failure · `2` usage ·
`3` missing configuration.

## Behavior

- **Subtitle first.** If yt-dlp reports usable subtitle tracks for the
  requested languages, media downloads and parses them — no ASR call.
- **ASR fallback.** Otherwise media extracts the audio (best available
  stream), converts it to mono 16 kHz mp3 with ffmpeg, uploads it to your
  bucket, and runs the chosen provider.
- `transcript_source` in the summary is `subtitle` or `asr`, so you know which
  path produced the text.
- Transcripts are cached and treated as stable; use `--refresh` to re-fetch.

## Outputs

```
cache/<platform>/<video_id>/
├── transcript.json    normalized transcript (authoritative)
├── transcript.md      readable full text
├── transcript.srt     optional subtitles
├── meta.json          title / uploader / duration
└── raw/asr_<provider>.json   raw provider response, for debugging
```

By default everything lives in the project root (`cache/`, `.env`,
`config.ini`). Set `MEDIA_DATA_DIR` to relocate the data directory.

## Cost

- The subtitle path normally costs nothing beyond network.
- The ASR fallback calls your own provider account and your own bucket:
  provider, storage and network costs are yours. This tool never sends you a
  bill and never charges anything itself.
- Use `--force-asr` only when you really want ASR — it spends a paid call even
  when free subtitles exist.

## Supported sources

Media extraction is provided through `yt-dlp`. Source compatibility therefore
depends on yt-dlp and may change over time.

- YouTube is the primary verified source.
- Other yt-dlp-supported sources work on a best-effort basis.

## Cache

`cache/<platform>/<video_id>/` mirrors what was fetched. Subtitle/transcript
files are cached indefinitely; use `--refresh` to re-fetch. Raw provider
responses are kept beside the transcript for debugging and are never required
for correctness.

## Prompt examples

The `prompts/` directory contains LLM-neutral transcript post-processing
templates (`full-summary`, `structured-notes`, `lecture-notes`,
`transcript-cleanup`). They are plain-text examples only — media never runs
them. Feed the generated transcript and one of these templates to any LLM you
prefer.

## Maintenance scope

This is a personal open-source project with best-effort maintenance — no SLA.
Provider and platform APIs may change, and website-specific workarounds are
out of scope. If a provider stops working, please open an issue rather than
expecting a quick fix.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The test suite is fully offline: parsing, normalization, SigV4 signing,
poll timing, cache round-trips and cleanup ordering, all with fakes. It never
touches the network or real credentials.

## License

MIT — see `LICENSE`.

---
name: voxsuji-transcript
description: >
  Turn an online video URL into a transcript with the Voxsuji CLI, then read
  the generated files and answer, summarize, quote, or take notes. Use when
  the user gives a video URL (YouTube or any yt-dlp-supported site) and asks
  for its spoken content, a transcript, a summary, video notes, or subtitles;
  or asks to run Voxsuji, or to use a specific ASR provider (aliyun,
  volcengine, tencent) on a video.
---

# voxsuji-transcript

Voxsuji turns a video URL into structured text (JSON / Markdown / SRT). It does
**not** summarize and does **not** call an LLM — reading the files and
summarizing is your job.

## Prerequisites

- `voxsuji` available: on `PATH`, or `./bin/voxsuji` at the project root.
- Python 3.10+ and `ffmpeg`.
- ASR fallback only: provider credentials and S3-compatible storage in `.env`
  (real environment variables also work and take precedence).
- Unsure about the setup? Run `voxsuji doctor` first. It prints JSON and never
  a secret value.

## Run

```bash
voxsuji transcript <URL>                        # subtitle-first; ASR only if needed
voxsuji transcript <URL> --json                 # quiet mode: suppress progress logs
voxsuji transcript <URL> --provider aliyun      # explicit ASR provider
voxsuji transcript <URL> --language zh          # language hint for ASR
voxsuji transcript <URL> --refresh              # ignore the cache and process again
voxsuji transcript <URL> --force-asr --refresh  # paid ASR; only when asked
```

`stdout` is always one compact JSON summary; the full transcript goes to files.
`--json` only suppresses human progress output, it does not change the summary.

## Read the result

1. Parse the JSON summary. `ok: true` means success.
2. Read `files.markdown` for the readable transcript; `files.json` has
   structured segments with timestamps; `files.srt` exists when timings allow.
3. For a long transcript, read it incrementally (offset/limit) or grep it.
   Never load the whole file at once.
4. `cached: true` — nothing was fetched; the same files were reused.
5. `transcript_source` is `subtitle` (free) or `asr` (paid). Set the user's
   expectations about cost and accuracy accordingly.

Failures print `{"ok": false, "error": {"type": "...", "message": "..."}}`.
Exit codes: `0` ok · `1` failure · `2` usage · `3` missing configuration.

- Exit 3 / `error.type == "unconfigured"`: the message names the missing
  variables. Report them to the user; never silently switch providers.
- Exit 1: report `error.message`; do not retry in a loop.
- Exit 2: fix the command.

## Never do this

- Do not ask the user to paste API keys, tokens, or cookies into the chat.
  Name the environment variable they need to fill in instead.
- Do not use `--force-asr` unless the user explicitly asks for ASR: it spends
  a paid call even when free subtitles exist.
- Do not promise comments or danmaku: they are out of scope for the public
  Voxsuji CLI.
- Do not modify the Voxsuji project or commit anything unless the user asks.
- Do not summarize inside the tool. The transcript text is already in the
  files; reason over it yourself.

## Install this skill

Copy this folder into your agent's skills directory, keeping the folder name:

- dsh: `~/.dsh/skills/voxsuji-transcript/`
- Claude Code: `~/.claude/skills/voxsuji-transcript/`
- Other agents: wherever `SKILL.md`-style skills are loaded.

## If a transcript MCP tool already exists

Some environments wrap the CLI as an MCP server so the agent needs no shell
permission. If your tool list already contains such a transcript tool, prefer
it and follow its instructions; otherwise use the CLI above.

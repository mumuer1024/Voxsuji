# Voxsuji Human–AI Collaboration Guide

> For users who don't write code. Give your AI assistant a video link and a sentence of what you want; the AI uses Voxsuji to turn the video into a transcript, then summarizes, organizes, or takes notes for you.
>
> [中文版](HUMAN-AI-GUIDE.md)

## Remember three things

1. **Voxsuji does exactly one thing**: turn an online video into a transcript (JSON / Markdown / SRT).
2. **Summarizing, translating and note-taking are your AI assistant's job** — Voxsuji does not call any LLM.
3. **The transcript is saved to files**; the AI only receives a small summary and file paths, so hours of video never blow up the AI's context.

## 1. What it can do

Good for:

- a long interview / podcast / course — have the AI explain the key points in minutes;
- turning a lecture into structured notes;
- getting a subtitle file (SRT) for a video;
- videos without subtitles — use speech recognition (ASR) to turn audio into text.

It does **not** do: comments / danmaku scraping, download management, or built-in AI summarization.

## 2. How it works

```text
You: give the AI a video link + what you want
 ↓
AI: runs voxsuji, gets transcript files
 ↓
AI: reads the transcript (in chunks for long ones)
 ↓
AI: summarizes / organizes / answers your questions
```

Inside Voxsuji:

```text
Look for platform subtitles → use them if available (free, fast)
                           → otherwise: extract audio → temp-upload to object storage → cloud ASR
Finally outputs JSON / Markdown / SRT
```

## 3. First-time setup: let the AI install it

### 3.1 What you need

- a computer with internet access (Linux / macOS, or WSL on Windows);
- Python 3.10 or newer;
- `ffmpeg`;
- a video URL (YouTube or another yt-dlp-supported site).

### 3.2 Send this to your AI assistant

```text
Install and check this open-source project: https://github.com/mumuer1024/Voxsuji

Steps:
1. git clone it locally;
2. install ffmpeg;
3. run ./bin/voxsuji doctor and show me the output as-is;
4. if doctor reports missing configuration, tell me what is missing and do not fill in any secrets yourself.
```

Note: your tool may ask you to approve each command — that's normal. On first run, Voxsuji creates a project-local virtualenv and does not touch the system Python.

### 3.3 Check the result

Have the AI run `./bin/voxsuji doctor`. It prints JSON telling you: whether dependencies are ready, which ASR provider is the default, and which providers and object storage are configured. It never prints any secret.

## 4. Everyday use (three ways)

### Way 1: let the AI handle everything (recommended)

```text
Use voxsuji to transcribe this video: <video URL>

Prefer platform subtitles; use my configured ASR only if there are none.
When done, read the generated Markdown transcript and summarize the main points in 10 bullets.
```

The AI will: run the command → read the JSON summary → open the transcript file → read it in chunks → summarize. You never need to copy-paste the full text.

### Way 2: transcribe first, then have the AI read it

```bash
voxsuji transcript <video URL>
```

When it finishes, it tells you where the files are (usually `cache/<platform>/<video ID>/`). Then send the path to the AI:

```text
Read <path>/transcript.md and turn it into structured notes.
```

### Way 3: you need a subtitle file

`transcript.srt` can be used directly as subtitles; `transcript.json` is timestamped structured data suitable for programs.

## 5. No subtitles: ASR (optional)

The default is "subtitles first": ASR is only called when no usable subtitles exist. Enabling ASR requires two things:

1. **a cloud speech-recognition service**: Alibaba Cloud Bailian, Volcengine, or Tencent Cloud — pick one;
2. **an S3-compatible object storage**: the ASR service needs to fetch the temporary audio from a public URL.

Ask the AI to set it up:

```text
Configure Voxsuji's ASR for me; I plan to use <Bailian / Volcengine / Tencent>.

Please tell me:
1. which environment variables to set (names only — do not print real values);
2. what the object storage must satisfy;
3. run doctor once configured.

I will fill in the secrets into .env myself.
```

**Cost:** subtitles usually cost nothing; ASR is billed to your own provider account; `--force-asr` skips free subtitles and forces ASR — avoid unless necessary.

**Privacy:** with ASR, the audio is temporarily uploaded to your own publicly readable bucket and deleted automatically after transcription. During that window, anyone with the link could technically access the temporary object.

## 6. Long videos and caching

- The transcript is in a file. Tell the AI "read it in chunks if it's long" so it does not load everything into context at once.
- Running the same video again reuses the cache (`"cached": true`) — no download, no ASR call.
- Re-process: `--refresh`; force ASR again: `--force-asr --refresh` (costs money).

## 7. FAQ

**Why don't I see the full text?**
By design. stdout only returns a compact JSON summary (with file paths) to avoid flooding the screen or the AI's context. The full text is in the files.

**"Missing configuration" / exit code 3?**
The ASR provider or object storage you selected is not configured; the error names the missing variable. Let the AI read the error; don't paste secrets into chat.

**The video plays in my browser but Voxsuji can't fetch it?**
Some sites restrict anonymous access. Prepare a Netscape-format `cookies.txt`, configure `[cookies] file`, and `chmod 600`. Never commit it to Git.

**Can it grab comments or danmaku?**
No. The public Voxsuji only produces transcripts and subtitles — comments and danmaku are out of scope.

**Does Voxsuji summarize for me?**
No. It never calls an LLM. Ask your AI assistant, or use the templates in `prompts/`.

**Where is data stored?**
By default under the project's `cache/`; set `VOXSUJI_DATA_DIR` to move it elsewhere.

**Local video files?**
The current version only accepts online video URLs.

**Which ASR should I pick?**
Configure only the one you actually use — the three adapters are independent. If unsure, start with the default (Alibaba Cloud Bailian), or ask your AI.

## 8. Security and privacy checklist

- API keys / secrets go only in `.env` (`chmod 600`) — never paste them into chat, never commit them.
- `cookies.txt` likewise `chmod 600`; never commit it.
- Temporary audio in object storage is publicly readable during ASR and deleted afterwards; don't use it for sensitive content.
- When your AI tool reads the transcript, the content enters its context — mind your privacy.

## 9. Advanced (optional): wrap Voxsuji as an MCP tool

If your AI client supports MCP (Model Context Protocol), you can write a thin MCP server: on a transcription request, run `voxsuji transcript <URL> --json` and return the JSON summary plus file paths to the AI.

**Benefit:** the AI does not need terminal permission on every call, and it gets structured results — handy for treating Voxsuji as an always-available tool.

**Note:** the public Voxsuji does not ship an MCP server. This is an optional DIY integration, not a project feature; ignore this section if you don't need it.

## 10. Prompt cheat sheet (copy-paste)

Install & check:

```text
Install and check https://github.com/mumuer1024/Voxsuji, then run doctor and tell me what's missing.
```

Transcribe & summarize:

```text
Use voxsuji to transcribe <URL>, subtitles first. When done, read the Markdown transcript and summarize it in 10 bullets.
```

Transcribe only:

```text
Use voxsuji to transcribe <URL> and just give me the output file paths; don't summarize yet.
```

Structured notes:

```text
Read <path>/transcript.md and organize it into notes with "background / key points / action items".
```

Subtitles only:

```text
Use voxsuji to transcribe <URL> and give me the path to transcript.srt.
```

Troubleshooting:

```text
voxsuji failed with: <error>. Use the doctor output and .env configuration to help me find the cause; don't print secrets.
```

Long video, chunked:

```text
<path>/transcript.md is long — read it in chunks. First give me the overall structure, then summarize section by section.
```

## Related docs

- [README](../README.md) — project overview and full commands
- [CONFIGURATION.md](CONFIGURATION.md) — configuration reference
- [PROVIDERS.md](PROVIDERS.md) — ASR provider setup
- [Companion skill](../skills/voxsuji-transcript/SKILL.md) — instructions for AI agents
- [中文版](HUMAN-AI-GUIDE.md) — Chinese version of this guide

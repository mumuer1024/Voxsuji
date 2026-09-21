# Configuration

`media` reads configuration from three places, in increasing precedence:

1. `config.ini` — non-secret settings (see `config.example.ini`).
2. `.env` — secrets (git-ignored, see `.env.example`).
3. real environment variables — always win over both of the above.

By default both files are read from the project root. Set `MEDIA_DATA_DIR`
to point the data directory elsewhere (it relocates `.env`, `config.ini` and
`cache/` together):

```bash
export MEDIA_DATA_DIR=/path/to/data
```

## `config.ini`

Copy `config.example.ini` to `config.ini` and edit.

| section | option | meaning |
| --- | --- | --- |
| `[asr]` | `default_provider` | provider used when `--provider` is not given (`aliyun`, `volcengine`, `tencent`) |
| `[asr]` | `poll_interval`, `poll_timeout` | async task polling tuning |
| `[subtitles]` | `preferred_languages` | comma-separated language preference order |
| `[tools]` | `ytdlp`, `ffmpeg`, `ffprobe` | override binaries (defaults: found on `PATH`) |
| `[provider.<name>]` | `model` | model / resource id override per provider |
| `[network]` | `http_timeout`, `upload_timeout` | HTTP and upload timeouts (seconds) |
| `[storage]` | `endpoint`, `region`, `bucket`, `path_style`, `public_base_url` | non-secret S3-compatible storage settings |
| `[cookies]` | `file` | optional Netscape cookies file passed to yt-dlp |

## Secrets (`.env`)

Copy `.env.example` to `.env` (`chmod 600`) and fill in the values. Secret
values never appear in logs or in `media doctor` output.

## Storage addressing

The tool implements AWS Signature V4 for S3-compatible object storage and
supports both addressing styles:

- **virtual-hosted** (default): the endpoint is the bucket host
  (`https://<bucket>.example.com`), `path_style = false`.
- **path-style**: the endpoint is the region host (`https://s3.example.com`),
  `path_style = true`; objects are addressed as `/<bucket>/<key>`.

`STORAGE_PUBLIC_BASE_URL` (config `[storage] public_base_url`) overrides the
public URL handed to the ASR provider when the bucket host differs from the
endpoint used for signing. The public base URL must be anonymously readable.

The bucket must be publicly readable for the ASR provider to fetch the
temporary audio object. Objects are uploaded under `asr-tmp/<random>.mp3` and
deleted immediately after transcription (including failure paths).

## Cookies

Optional, and entirely the user's responsibility: export a Netscape-format
`cookies.txt` from a browser where you are logged in, set `[cookies] file`,
and keep the file `chmod 600`. It is read in memory, never printed or logged,
and never rewritten. Leave `file` unset to run anonymously.

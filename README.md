# Voxsuji

把在线视频变成结构化、可缓存的文字稿。

**优先使用现成字幕；没有可用字幕时，再调用云端 ASR。**

输出 JSON、Markdown 和 SRT，既适合直接阅读，也适合交给 AI Agent 或其他工具继续处理。

**Voxsuji** 由 *vox*（声音）与受中文“速记”启发的 *suji* 组合而来：声音进来，文字出去。

[English](#english) | [简体中文](#中文)

```text
URL
 ↓
yt-dlp 获取视频信息
 ↓
发现可用字幕？ ── Yes → 解析字幕
 ↓ No
提取音频
 ↓
临时上传至 S3-compatible 对象存储
 ↓
云端 ASR
 ↓
统一格式化
 ↓
JSON / Markdown / SRT
```

---

# 中文

## 关于名字

**Voxsuji** 由 *vox*（声音）与受中文“速记”启发的 *suji* 组合而来：把声音快速、忠实地记录成文字。`suji` 是品牌化的写法，不是“速记”的标准拼音，也不是来自日语。

## Voxsuji 是什么？

`voxsuji` 是一个小型 CLI 工具，用来把在线视频 URL 转换成完整文字稿。

它的原则很简单：

- **字幕优先**：平台已经提供可用字幕时，直接使用字幕，不产生 ASR 调用。
- **ASR fallback**：没有可用字幕时，自动提取音频并调用你配置的云端语音识别服务。
- **本地缓存**：已经处理过的视频会保存在本地，再次运行通常直接使用缓存。
- **结构化输出**：同时生成适合程序处理的 JSON、适合人和 AI 阅读的 Markdown，以及 SRT 字幕文件。
- **不绑定 LLM**：Voxsuji 只负责把视频可靠地变成文字。总结、整理、问答等后续工作可以交给你喜欢的任意 AI。

目前支持三种 ASR provider：

| Provider | 标识 |
| --- | --- |
| 阿里云百炼 | `aliyun` |
| 火山引擎 | `volcengine` |
| 腾讯云 | `tencent` |

你只需要配置自己实际使用的一家。

---

## 它不是什么？

Voxsuji 不是视频下载器 UI，也不是特定视频网站客户端。

它不负责评论、弹幕，不内置 LLM 总结服务，也没有账号系统或托管服务。

视频提取能力来自 `yt-dlp`。YouTube 是主要验证来源，其他 `yt-dlp` 支持的网站按 best-effort 工作。

---

## 快速开始

### 1. 准备环境

需要：

- Python 3.10 或更高版本（开发环境使用 Python 3.13）
- `ffmpeg` / `ffprobe`
- 网络能够访问你需要处理的视频来源、ASR 服务和对象存储

`yt-dlp` 会由项目 launcher 自动安装到项目自己的虚拟环境中。

以 Debian / Ubuntu 为例：

```bash
git clone https://github.com/mumuer1024/Voxsuji.git
cd voxsuji

sudo apt-get install -y ffmpeg
./bin/voxsuji doctor
```

第一次运行时，`bin/voxsuji` 会自动创建项目内的 `.venv` 并安装 `yt-dlp`，不会修改系统 Python 环境。

如果希望直接使用 `voxsuji` 命令，可以建立软链接：

```bash
ln -s "$(pwd)/bin/voxsuji" /usr/local/bin/voxsuji
```

---

## 最简单的使用方法

拿到一个视频 URL 后：

```bash
voxsuji transcript <URL>
```

就这样。

Voxsuji 会：

1. 获取视频信息；
2. 尝试寻找可用的平台字幕；
3. 有字幕时直接生成文字稿；
4. 没有字幕时，使用你配置的 ASR provider 转录；
5. 把结果写入本地缓存目录。

正常情况下，你最常用的文件是：

```text
transcript.md
```

想让 AI 帮你看视频时，通常直接把这个 Markdown 文字稿交给 AI 就够了。

### 常用命令

```bash
voxsuji transcript <URL>                    # 字幕优先，无字幕时自动 ASR
voxsuji transcript <URL> --provider aliyun  # 指定 ASR provider
voxsuji transcript <URL> --language zh      # ASR 语言提示
voxsuji transcript <URL> --force-asr        # 忽略现有字幕，强制 ASR
voxsuji transcript <URL> --refresh          # 忽略已有缓存，重新获取
voxsuji doctor                              # 检查依赖和配置
```

需要机器可读的 stdout 摘要时：

```bash
voxsuji transcript <URL> --json
```

> 说明：当前版本只接受在线视频 URL。命令行接口未提供本地文件转写或独立的渲染子命令。

---

## 配置

复制示例配置：

```bash
cp .env.example .env
chmod 600 .env

cp config.example.ini config.ini
```

然后编辑 `.env` 和 `config.ini`。

检查结果：

```bash
voxsuji doctor
```

`doctor` 会告诉你哪些 provider、storage 和 cookies 已经配置，但不会打印 secret。

### ASR

默认 provider 在 `config.ini` 中设置：

```ini
[asr]
default_provider = aliyun
```

也可以每次运行时指定：

```bash
voxsuji transcript <URL> --provider volcengine
```

三家 provider 相互独立，没有配置的 provider 不影响其他 provider。

#### 阿里云百炼

```text
DASHSCOPE_API_KEY=...
```

可选：

```text
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
```

#### 火山引擎

```text
VOLC_API_KEY=...
```

或使用对应的 App ID / Access Token 配置方式。

#### 腾讯云

```text
TENCENT_SECRET_ID=...
TENCENT_SECRET_KEY=...
```

完整变量和 provider 配置见 `docs/PROVIDERS.md`。

Provider 的 API、模型、价格、配额和可用性都可能随时间变化；项目中的配置以对应版本发布时的验证结果为准。

---

## S3-compatible 对象存储

**如果视频本身已经有可用字幕，这一部分完全不需要配置。**

只有进入 ASR fallback 时，Voxsuji 才需要临时存放音频。

这是因为云端 ASR 服务需要通过一个公网 URL 获取待识别音频。Voxsuji 会把处理后的音频暂时上传到你自己的 S3-compatible bucket：

```text
STORAGE_ENDPOINT=https://s3.example.com
STORAGE_REGION=example-region
STORAGE_BUCKET=your-bucket
STORAGE_ACCESS_KEY=your-access-key
STORAGE_SECRET_KEY=your-secret-key
```

运行过程中，Voxsuji 会创建一个随机临时对象：

```text
asr-tmp/<random>.mp3
```

然后验证该对象可以被匿名读取，提交给 ASR，并在转录完成或失败后通过 cleanup 流程删除。

因此临时音频通常只存在于一次任务的处理期间。

对象存储、网络和 ASR 产生的费用由你自己的服务商账户承担。

### ☁️ 没有 S3？可以看看雨云

如果你还没有可用的 S3-compatible 对象存储，可以考虑雨云提供的对象存储服务。

通过我的推广链接注册，新用户目前可以获得 **首月 5 折优惠券**：

**雨云推广链接：**  
`https://www.rainyun.com/NjkwNzM4_`

> **推广说明：** 上面是作者的推广链接。通过该链接注册、消费可能会给我带来积分或销售提成，但不会因此提高你的实际购买价格。活动内容可能调整，请以雨云当前规则为准。
>
> 雨云只是一个可选的 S3-compatible 服务商。Voxsuji 不依赖雨云，也没有针对特定对象存储厂商的专用实现；你可以使用任何符合配置要求的 S3-compatible object storage。

---

## PS：有些网站可能需要登录态

如果你在浏览器里明明可以正常看到某个视频或字幕，但 `voxsuji` / `yt-dlp` 获取不到内容，有可能是网站对未登录访问做了限制。

这时可以自行准备一个 Netscape 格式的 `cookies.txt`：

```ini
[cookies]
file = /path/to/cookies.txt
```

Voxsuji 会把这个文件交给 `yt-dlp` 使用。

它不会帮你登录账号，也不会自动刷新 Cookie。

请妥善保护 `cookies.txt`，不要把它提交到 Git。建议限制文件权限：

```bash
chmod 600 /path/to/cookies.txt
```

---

## 和 AI Agent 一起使用

Voxsuji 很适合交给 Claude Code、Codex、Cursor 或其他能够执行命令和读取文件的 AI Agent。

它有意**不会把完整文字稿输出到 stdout**。

命令执行完成后，stdout 只返回一个很小的 JSON summary，其中包含生成文件的位置。这样几个小时的视频不会突然把 Agent 的 context 塞满。

推荐的 Agent 工作方式是：

```text
用户给出视频 URL
        ↓
Agent 运行 voxsuji transcript <URL>
        ↓
读取 stdout JSON summary
        ↓
找到 files.markdown
        ↓
读取 transcript.md（长文本建议分段 / 增量读取）
        ↓
根据用户需求总结 / 整理 / 分析 / 保存
```

你可以直接对 Agent 说：

> 使用这个项目的 `voxsuji` CLI 获取这个视频的完整文字稿。优先使用平台现有字幕，没有字幕时允许使用已配置的 ASR。完成后读取生成的 Markdown transcript，并为我总结主要内容。不要修改 voxsuji 项目本身。

如果视频很长，建议让 Agent 按需分段读取 Markdown，而不是一次把整份 transcript 塞进上下文。

`prompts/` 目录另外提供了一些 LLM-neutral 的后处理模板：

```text
full-summary.md
structured-notes.md
lecture-notes.md
transcript-cleanup.md
```

这些只是普通文本 Prompt，Voxsuji 不会自动执行它们。

Voxsuji 本身不会调用任何 LLM API，你可以自由选择 ChatGPT、Claude、Gemini、DeepSeek、本地模型或其他工具处理生成的 transcript。

---

## 输出

默认缓存结构：

```text
cache/<platform>/<video_id>/
├── transcript.json
├── transcript.md
├── transcript.srt
├── meta.json
└── raw/
    └── asr_<provider>.json
```

其中：

- `transcript.json`：标准化后的完整结构，是权威数据源；
- `transcript.md`：适合直接阅读或交给 AI；
- `transcript.srt`：字幕格式；
- `meta.json`：视频标题、上传者、时长等信息；
- `raw/asr_<provider>.json`：ASR provider 原始响应，主要用于调试。

默认数据位于项目目录。

可以通过：

```text
VOXSUJI_DATA_DIR=/your/data/path
```

改变数据目录。

---

## stdout 契约

成功时 stdout 始终是单个紧凑 JSON summary，例如：

```json
{
  "ok": true,
  "cached": false,
  "source_url": "...",
  "platform": "youtube",
  "video_id": "...",
  "title": "...",
  "duration": 212.3,
  "transcript_source": "subtitle",
  "provider": null,
  "model": null,
  "language": null,
  "segment_count": 19,
  "char_count": 1632,
  "word_timestamps": false,
  "files": {
    "json": "...",
    "markdown": "...",
    "srt": "..."
  }
}
```

失败时：

```json
{"ok": false, "error": {"type": "...", "message": "..."}}
```

退出码：

| Code | 含义 |
| ---: | --- |
| `0` | 成功 |
| `1` | 命令 / pipeline 失败 |
| `2` | 参数使用错误 |
| `3` | 缺少必要配置 |

---

## 缓存

处理结果默认缓存在：

```text
cache/<platform>/<video_id>/
```

已有 transcript 会直接复用。

如果需要重新获取：

```bash
voxsuji transcript <URL> --refresh
```

如果明确希望忽略平台字幕并重新调用 ASR：

```bash
voxsuji transcript <URL> --force-asr --refresh
```

注意：ASR 调用可能产生费用。

---

## 成本

Voxsuji 本身不收费。

使用平台已有字幕时，通常不会产生 ASR API 成本。

进入 ASR fallback 后，会使用你自己的：

- ASR provider；
- S3-compatible object storage；
- 网络资源。

对应费用由服务商直接向你的账户收取。

除非确实需要，否则不要随便使用 `--force-asr` —— 它会跳过原本免费的字幕路径。

---

## 支持的网站

视频提取由 `yt-dlp` 提供，因此实际网站兼容性取决于 `yt-dlp`，并可能随网站和 `yt-dlp` 更新而变化。

YouTube 是主要验证来源。

其他 `yt-dlp` 支持的视频来源按 best-effort 工作；本项目不维护针对单一网站的专用抓取或绕过逻辑。

---

## 测试

测试套件完全离线，不访问真实网络，也不需要真实 API credential：

```bash
python3 -m unittest discover -s tests -v
```

当前测试覆盖包括字幕解析、transcript normalization、S3 SigV4、provider response normalization、polling、cache、cleanup 和 cookies 等核心行为。

---

# English

**Voxsuji** turns an online video URL into **structured, cacheable text**.

The name **Voxsuji** combines *vox* (“voice”) with a playful rendering inspired by the Chinese word **速记** — shorthand / rapid transcription. It is a product name, not a standard romanization of 速记, and it is not derived from Japanese.

It uses existing platform subtitles whenever possible and falls back to cloud ASR only when necessary.

Outputs are written as JSON, Markdown and SRT, making them useful both for direct reading and for downstream AI/agent workflows.

```text
URL → yt-dlp metadata → existing subtitles when available
    → otherwise audio extraction
    → temporary S3-compatible object upload
    → cloud ASR
    → normalized transcript
    → JSON / Markdown / SRT
```

## What it is

`voxsuji` is a small CLI for producing transcripts from online videos.

It is:

- **Subtitle-first** — existing usable subtitles avoid a paid ASR call.
- **ASR-capable** — when subtitles are unavailable, audio is transcribed using a cloud ASR provider you configure.
- **Cacheable** — completed transcripts are stored locally and reused.
- **Structured** — JSON, Markdown and SRT are generated from one normalized transcript.
- **LLM-neutral** — Voxsuji produces text; summarization and analysis are left to whatever model or agent you prefer.

Supported ASR adapters:

| Provider | Name |
| --- | --- |
| Alibaba Cloud Bailian | `aliyun` |
| Volcengine | `volcengine` |
| Tencent Cloud | `tencent` |

Only the provider you actually use needs to be configured.

## What it is not

Voxsuji is not a video-downloader UI, a website-specific client, a comments or danmaku tool, an LLM summarization service, or a hosted service.

Video extraction is provided through `yt-dlp`.

YouTube is the primary verified source. Other sources supported by `yt-dlp` work on a best-effort basis.

---

## Requirements

- Python 3.10+ (developed on 3.13)
- `ffmpeg` and `ffprobe`
- network access to the source video and configured services
- one ASR provider for ASR fallback
- S3-compatible object storage for ASR fallback

If usable subtitles already exist, neither ASR nor object storage is required.

---

## Installation

```bash
git clone https://github.com/mumuer1024/Voxsuji.git
cd voxsuji

sudo apt-get install -y ffmpeg
./bin/voxsuji doctor
```

The launcher creates a project-local virtual environment and installs `yt-dlp` automatically on first use.

Optional:

```bash
ln -s "$(pwd)/bin/voxsuji" /usr/local/bin/voxsuji
```

---

## Quick start

```bash
voxsuji transcript <URL>
```

Voxsuji first looks for usable subtitles. If none are available, it extracts the audio and uses your configured ASR provider.

Common commands:

```bash
voxsuji transcript <URL>
voxsuji transcript <URL> --provider aliyun
voxsuji transcript <URL> --language zh
voxsuji transcript <URL> --force-asr
voxsuji transcript <URL> --refresh
voxsuji doctor
```

Use `--json` when you explicitly want the machine-readable summary on stdout.

> Note: the current CLI accepts online video URLs only. It does not (yet) offer local-file input or a separate render subcommand.

---

## Configuration

```bash
cp .env.example .env
chmod 600 .env

cp config.example.ini config.ini
./bin/voxsuji doctor
```

`doctor` reports configuration and dependency status without printing secrets.

### ASR providers

The default provider is configured in `config.ini`:

```ini
[asr]
default_provider = aliyun
```

A provider can also be selected per run:

```bash
voxsuji transcript <URL> --provider tencent
```

Missing credentials for the selected provider fail explicitly. Voxsuji does not silently switch to another provider.

See `docs/PROVIDERS.md` for provider-specific configuration.

Provider APIs, models, pricing, quotas and availability may change over time. Configuration is maintained on a best-effort basis and reflects what was verified around the corresponding project release.

---

## S3-compatible object storage

Object storage is only required for the ASR fallback path.

Cloud ASR providers need a URL from which they can fetch the audio. Voxsuji therefore temporarily uploads the normalized audio to your own S3-compatible bucket.

Example:

```text
STORAGE_ENDPOINT=https://s3.example.com
STORAGE_REGION=example-region
STORAGE_BUCKET=your-bucket
STORAGE_ACCESS_KEY=your-access-key
STORAGE_SECRET_KEY=your-secret-key
```

For each ASR run, Voxsuji:

1. uploads the audio under a random temporary key;
2. verifies that the object is publicly readable;
3. submits its URL to the ASR provider;
4. deletes the temporary object during cleanup, whether transcription succeeds or fails.

You provide and manage the bucket yourself.

Storage, network and ASR costs belong to your own provider accounts.

### ☁️ Need an S3-compatible provider?

If you do not already have S3-compatible object storage, RainYun is one option.

New users registering through my referral link currently receive a **50% discount coupon for their first month**:

`https://www.rainyun.com/NjkwNzM4_`

> **Disclosure:** This is an affiliate/referral link. Registrations or purchases made through it may earn me points or sales commission, without increasing your purchase price. Promotion terms may change; please refer to RainYun's current terms.
>
> RainYun is entirely optional. Voxsuji does not depend on RainYun or contain vendor-specific integration. Any compatible S3 object storage can be used.

---

## PS: authenticated sources

Some websites expose different content to authenticated and anonymous users.

If content or subtitles are available in your browser but not through `voxsuji` / `yt-dlp`, you can optionally provide a Netscape-format `cookies.txt`:

```ini
[cookies]
file = /path/to/cookies.txt
```

Voxsuji passes the file to `yt-dlp`. It does not log you in or refresh your cookies.

Keep the file private and never commit it to Git.

---

## Using Voxsuji with AI agents

Voxsuji is designed to work well with coding agents and other tools that can execute commands and read files.

Full transcripts are intentionally **not printed to stdout**. Instead, the CLI returns a compact JSON summary containing paths to the generated files.

A recommended agent workflow is:

```text
video URL
   ↓
voxsuji transcript <URL>
   ↓
read stdout JSON summary
   ↓
open files.markdown
   ↓
read transcript.md (prefer incremental reads for long transcripts)
   ↓
summarize / analyze / organize as requested
```

For example, you can tell an agent:

> Use the `voxsuji` CLI in this project to obtain a complete transcript of this video. Prefer existing platform subtitles and use the configured ASR fallback only when necessary. Then read the generated Markdown transcript and summarize the main content. Do not modify the voxsuji project itself.

For long transcripts, agents should preferably read the Markdown incrementally rather than loading the entire file into context at once.

The `prompts/` directory also contains LLM-neutral post-processing examples:

```text
full-summary.md
structured-notes.md
lecture-notes.md
transcript-cleanup.md
```

They are plain prompt templates only. Voxsuji never calls an LLM API itself.

---

## Outputs

```text
cache/<platform>/<video_id>/
├── transcript.json
├── transcript.md
├── transcript.srt
├── meta.json
└── raw/
    └── asr_<provider>.json
```

`transcript.json` is the normalized authoritative representation.

`transcript.md` is intended for direct reading and AI workflows.

`transcript.srt` can be used as a subtitle file.

Raw provider responses are retained locally for debugging.

Set `VOXSUJI_DATA_DIR` to relocate the data directory.

---

## Output contract

stdout contains one compact JSON summary rather than the full transcript:

```json
{
  "ok": true,
  "cached": false,
  "source_url": "...",
  "platform": "youtube",
  "video_id": "...",
  "title": "...",
  "duration": 212.3,
  "transcript_source": "subtitle",
  "provider": null,
  "model": null,
  "language": null,
  "segment_count": 19,
  "char_count": 1632,
  "word_timestamps": false,
  "files": {
    "json": "...",
    "markdown": "...",
    "srt": "..."
  }
}
```

On failure:

```json
{"ok": false, "error": {"type": "...", "message": "..."}}
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| `0` | success |
| `1` | command / pipeline failure |
| `2` | usage error |
| `3` | missing configuration |

---

## Cache

Completed transcripts are reused from:

```text
cache/<platform>/<video_id>/
```

Use:

```bash
voxsuji transcript <URL> --refresh
```

to fetch/process the source again.

To explicitly ignore platform subtitles and run ASR again:

```bash
voxsuji transcript <URL> --force-asr --refresh
```

This may incur ASR costs.

---

## Cost

Voxsuji itself does not charge anything.

The subtitle path normally incurs no ASR API cost.

When ASR fallback is used, your own ASR, storage and network accounts may incur charges.

---

## Supported sources

Source extraction is handled by `yt-dlp`, so compatibility depends on `yt-dlp` and may change over time.

YouTube is the primary verified source.

Other `yt-dlp`-supported sources are best-effort. Website-specific scraping and bypass logic are intentionally out of scope.

---

## Tests

The test suite is fully offline and does not require real credentials:

```bash
python3 -m unittest discover -s tests -v
```

---

## Maintenance

This is a personal open-source project maintained on a best-effort basis.

Provider and platform APIs may change over time. Issue reports and pull requests are welcome.

There is no SLA and no guarantee of website-specific compatibility.

---

## License

[MIT License](LICENSE)

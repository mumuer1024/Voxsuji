# ASR providers

Three cloud speech-recognition providers are supported as ASR fallback. You
only need to configure the one you use; unconfigured providers do not affect
the others. Choose per run with `--provider`, or set `default_provider` in
`config.ini`.

All three adapters perform the same flow: submit an audio URL (the temporary
public object in your bucket) → poll the async task → download and normalize
the result into the shared transcript schema.

> Provider APIs, models, pricing, quotas and availability may change.
> Configuration is best-effort and documented as verified at the project
> release date. All costs are billed to your own provider account.

## Aliyun Bailian (DashScope)

- Model: `qwen-audio-3.0-asr-flash-filetrans` (file transcription, async).
- Credentials: `DASHSCOPE_API_KEY` in `.env`.
- Endpoint: official default `https://dashscope.aliyuncs.com/api/v1`;
  override with `DASHSCOPE_BASE_URL` if you use a regional/workspace endpoint.
- Submit: `POST {base}/services/audio/asr/transcription` with
  `X-DashScope-Async: enable`; poll `GET {base}/tasks/{task_id}`.

## Volcengine

- Model / resource id: `volc.seedasr.auc` (default; override with
  `VOLC_RESOURCE_ID` or `[provider.volcengine] model`).
- Credentials: either `VOLC_API_KEY` (new console, sent as `X-Api-Key`) or
  `VOLC_APP_ID` + `VOLC_ACCESS_TOKEN` (legacy console, sent as
  `X-Api-App-Key` + `X-Api-Access-Key`). Fill in exactly one style.
- Endpoint: `https://openspeech.bytedance.com/api/v3/auc/bigmodel/...`.
- Note: entitlement is per model — an account that has not opened a given
  model is rejected with HTTP 403.

## Tencent Cloud

- Model: `16k_zh` (录音文件识别 / `CreateRecTask`).
- Credentials: `TENCENT_SECRET_ID` + `TENCENT_SECRET_KEY` in `.env`
  (optionally `TENCENT_TOKEN` for temporary STS credentials).
- Region: default `ap-beijing`, override with `TENCENT_REGION`.
- Endpoint: `https://asr.tencentcloudapi.com` (TC3-HMAC-SHA256 signed).

## Choosing a provider

- `media doctor` reports which providers are configured and which adapters
  are marked verified, without printing any secret value.
- A selected provider without credentials fails explicitly with exit code 3
  and names the missing variables. There is no silent fallback to another
  provider.

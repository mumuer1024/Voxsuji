"""Unit tests for parsing / normalization that need no network or credentials.

Run with:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from voxsuji import formatters, storage, subtitles, urls  # noqa: E402
from voxsuji.models import Segment, Transcript, VideoMeta, Word  # noqa: E402
from voxsuji.s3 import S3Client  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class UrlIdentificationTests(unittest.TestCase):
    def test_youtube_watch(self):
        ref = urls.identify("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s")
        self.assertEqual((ref.platform, ref.video_id), ("youtube", "dQw4w9WgXcQ"))

    def test_youtube_shortlink_and_shorts(self):
        self.assertEqual(urls.identify("https://youtu.be/dQw4w9WgXcQ").video_id, "dQw4w9WgXcQ")
        self.assertEqual(
            urls.identify("https://www.youtube.com/shorts/dQw4w9WgXcQ").video_id, "dQw4w9WgXcQ"
        )

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            urls.identify("https://www.youtube.com/@channel")
        with self.assertRaises(ValueError):
            urls.identify("   ")


class SubtitleParsingTests(unittest.TestCase):
    def test_vtt(self):
        segments = subtitles.parse_vtt((FIXTURES / "sample.vtt").read_text(encoding="utf-8"))
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].start, 1.2, places=3)
        self.assertAlmostEqual(segments[0].end, 3.36, places=3)
        self.assertEqual(segments[0].text, "第一句字幕")
        self.assertEqual(segments[1].text, "second line")

    def test_srt_uses_same_timing_parser(self):
        segments = subtitles.parse_srt((FIXTURES / "sample.srt").read_text(encoding="utf-8"))
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[1].start, 3.36, places=3)

    def test_json3_word_offsets(self):
        import json

        data = json.loads((FIXTURES / "sample.json3").read_text(encoding="utf-8"))
        segments = subtitles.parse_json3(data)
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].start, 1.2, places=3)
        self.assertEqual(segments[0].words[1].text, "字幕")
        self.assertAlmostEqual(segments[0].words[1].start, 1.7, places=3)


class FormatterTests(unittest.TestCase):
    def _transcript(self) -> Transcript:
        return Transcript(
            source_url="https://example.com/v",
            platform="youtube",
            video=VideoMeta(id="abc", title="T", uploader="u", duration=10.0),
            transcript_source="asr",
            provider="aliyun",
            model="m",
            duration=10.0,
            segments=[
                Segment(start=1.5, end=3.0, text="hello", speaker="S1", words=[Word(1.5, 2.0, "he")]),
                Segment(start=3.0, end=4.25, text="world"),
            ],
        )

    def test_markdown_contains_metadata_and_text(self):
        md = formatters.to_markdown(self._transcript())
        self.assertIn("# T", md)
        self.assertIn("| provider | aliyun |", md)
        self.assertIn("[00:00:01.500] S1: hello", md)

    def test_srt_numbering_and_timing(self):
        srt = formatters.to_srt(self._transcript())
        self.assertIn("1\n00:00:01,500 --> 00:00:03,000", srt)
        self.assertIn("2\n00:00:03,000 --> 00:00:04,250", srt)

    def test_srt_empty_without_segments(self):
        transcript = self._transcript()
        transcript.segments = []
        self.assertEqual(formatters.to_srt(transcript), "")


class Sha256SigningTests(unittest.TestCase):
    def test_default_addressing_uses_endpoint_as_given(self):
        client = S3Client(
            endpoint="https://mybucket.s3.example.com",
            bucket="mybucket",
            access_key="test-access-key",
            secret_key="test-secret",
            region="example-region",
        )
        self.assertEqual(client.public_url("x/y.mp3"), "https://mybucket.s3.example.com/x/y.mp3")
        self.assertEqual(client._object_path("x/y.mp3"), "/x/y.mp3")

    def test_virtual_hosted_when_endpoint_has_no_bucket(self):
        client = S3Client(
            endpoint="https://s3.example.com",
            bucket="examplebucket",
            access_key="test-access-key",
            secret_key="test-secret",
            region="example-region",
        )
        # The endpoint is used verbatim; callers point it at the bucket host.
        self.assertEqual(
            client.public_url("a b/c.txt"), "https://s3.example.com/a%20b/c.txt"
        )

    def test_path_style_url(self):
        client = S3Client(
            endpoint="https://s3.example.com",
            bucket="mybucket",
            access_key="test-access-key",
            secret_key="test-secret",
            region="example-region",
            path_style=True,
        )
        self.assertEqual(client.public_url("x/y.mp3"), "https://s3.example.com/mybucket/x/y.mp3")
        self.assertEqual(client._object_path("x/y.mp3"), "/mybucket/x/y.mp3")


class ProviderNormalizationTests(unittest.TestCase):
    """Mapping tests against frozen copies of the real provider payload shapes."""

    def test_aliyun_real_response_shape(self):
        import json

        from voxsuji.config import Config
        from voxsuji.providers.aliyun import AliyunProvider

        raw = json.loads((FIXTURES / "aliyun_transcription.json").read_text(encoding="utf-8"))
        provider = AliyunProvider(Config())
        result = provider._normalize_from_raw(raw, model="m", task_id="t")
        self.assertGreaterEqual(len(result.segments), 1)
        first = result.segments[0]
        self.assertAlmostEqual(first.start, first.start)  # numeric seconds
        self.assertGreater(first.end, first.start)
        self.assertTrue(first.text)
        self.assertIsNotNone(first.words)
        self.assertAlmostEqual(result.duration, 212.309, places=3)

    def test_tencent_real_response_shape(self):
        """Fixture is a trimmed copy of a real DescribeTaskStatus response."""
        import json

        from voxsuji.config import Config
        from voxsuji.providers.tencent import TencentProvider

        data = json.loads((FIXTURES / "tencent_result.json").read_text(encoding="utf-8"))
        provider = TencentProvider(Config())
        result = provider._normalize(data, model="16k_zh", task_id="1")

        self.assertEqual(len(result.segments), 2)
        self.assertAlmostEqual(result.duration, 152.362688, places=3)
        first = result.segments[0]
        self.assertAlmostEqual(first.start, 0.0, places=3)
        self.assertAlmostEqual(first.end, 60.48, places=3)
        self.assertTrue(first.text.endswith("。"), first.text[-20:])
        self.assertIsNotNone(first.words)
        # word offsets are relative to the sentence start, so the first word of
        # the second sentence must land at that sentence's StartMs, not 2x it.
        second = result.segments[1]
        self.assertAlmostEqual(second.start, 60.48, places=3)
        self.assertAlmostEqual(second.words[0].start, second.start, places=3)
        self.assertLess(second.words[-1].end, second.end + 1.0)
        # SpeakerId 0 means "diarization not requested", not a real speaker.
        self.assertIsNone(first.speaker)

    def test_tencent_annotated_offset_holds_for_a_one_speaker_id(self):
        from voxsuji.config import Config
        from voxsuji.providers.tencent import TencentProvider

        data = {
            "AudioDuration": 3.0,
            "ResultDetail": [
                {
                    "FinalSentence": "你好世界。",
                    "StartMs": 1000,
                    "EndMs": 3000,
                    "SpeakerId": 1,
                    "Words": [
                        {"Word": "你好", "OffsetStartMs": 0, "OffsetEndMs": 500},
                        {"Word": "世界", "OffsetStartMs": 500, "OffsetEndMs": 1200},
                    ],
                }
            ],
        }
        segment = TencentProvider(Config())._normalize(data, model="16k_zh", task_id="1").segments[0]
        self.assertEqual(segment.speaker, "1")
        self.assertAlmostEqual(segment.words[0].start, 1.0, places=3)
        self.assertAlmostEqual(segment.words[1].start, 1.5, places=3)

    def test_tencent_requests_punctuated_sentence_segmentation(self):
        """ResTextFormat=3 is the documented 字幕/按标点分段 shape, not a paid tier."""
        import os

        from voxsuji.config import Config
        from voxsuji.providers import tencent as tencent_module

        self.enterContext(
            unittest.mock.patch.dict(
                os.environ,
                {"TENCENT_SECRET_ID": "AKIDmasked", "TENCENT_SECRET_KEY": "masked", "TENCENT_TOKEN": ""},
                clear=False,
            )
        )
        provider = tencent_module.TencentProvider(Config())
        sent: dict = {}

        def fake_call(action, body):
            sent["action"] = action
            sent["body"] = body
            return {"Data": {"TaskId": 1}}

        with unittest.mock.patch.object(provider, "_call", side_effect=fake_call), unittest.mock.patch.object(
            provider, "_normalize", return_value="normalized"
        ):
            # Stop right after CreateRecTask by making the poll see success.
            with unittest.mock.patch.object(
                tencent_module, "_poll", return_value={"Status": 2, "AudioDuration": 1.0}
            ):
                provider.transcribe("https://example.invalid/a.mp3")
        self.assertEqual(sent["action"], "CreateRecTask")
        self.assertEqual(sent["body"]["ResTextFormat"], 3)
        self.assertEqual(sent["body"]["EngineModelType"], "16k_zh")
        self.assertEqual(sent["body"]["ChannelNum"], 1)
        self.assertEqual(sent["body"]["SourceType"], 0)
        self.assertEqual(sent["body"]["SpeakerDiarization"], 0)

    def test_volcengine_real_response_shape(self):
        """Fixture is a trimmed copy of a real volc.seedasr.auc query response."""
        import json

        from voxsuji.config import Config
        from voxsuji.providers.volcengine import VolcengineProvider

        body = json.loads((FIXTURES / "volcengine_query.json").read_text(encoding="utf-8"))
        result = VolcengineProvider(Config())._normalize(body, task_id="t")

        self.assertEqual(len(result.segments), 2)
        self.assertAlmostEqual(result.duration, 152.496, places=3)
        first = result.segments[0]
        self.assertAlmostEqual(first.start, 0.26, places=3)
        self.assertAlmostEqual(first.end, 2.1, places=3)
        self.assertTrue(first.text)
        self.assertIsNotNone(first.words)
        # No language / speaker fields were requested or returned.
        self.assertIsNone(result.language)
        self.assertIsNone(first.speaker)

    def test_volcengine_drops_the_negative_timing_sentinel(self):
        """The service marks untimed whitespace separators with -1 ms."""
        from voxsuji.config import Config
        from voxsuji.providers.volcengine import VolcengineProvider

        body = {
            "audio_info": {"duration": 2100},
            "result": {
                "text": "up 主",
                "utterances": [
                    {
                        "start_time": 260,
                        "end_time": 2100,
                        "text": "up 主",
                        "words": [
                            {"start_time": 260, "end_time": 500, "text": "up"},
                            {"start_time": -1, "end_time": -1, "text": " "},
                            {"start_time": 940, "end_time": 1020, "text": "主"},
                        ],
                    },
                    {"start_time": -1, "end_time": -1, "text": " ", "words": [
                        {"start_time": -1, "end_time": -1, "text": " "}]},
                ],
            },
        }
        result = VolcengineProvider(Config())._normalize(body, task_id="t")
        words = result.segments[0].words
        self.assertEqual([w.text for w in words], ["up", "主"])
        self.assertTrue(all(w.start >= 0 and w.end >= 0 for w in words))
        # An utterance with no usable words must not invent a word list.
        self.assertIsNone(result.segments[1].words)
        self.assertTrue(all(s.start >= 0 and s.end >= 0 for s in result.segments))


class VolcengineAuthTests(unittest.TestCase):
    """Header contract: `.env` names must actually reach the request."""

    def _provider(self):
        import os
        import unittest.mock

        from voxsuji.config import Config
        from voxsuji.providers.volcengine import VolcengineProvider

        env = {
            "VOLC_APP_ID": "app-id-value",
            "VOLC_ACCESS_TOKEN": "access-token-value",
            "VOLC_API_KEY": "",
            "VOLC_RESOURCE_ID": "volc.seedasr.auc",
        }
        # Config.get() reads os.environ lazily, so the patch must outlive this
        # call: keep it alive for the whole test via the context stack.
        self.enterContext(unittest.mock.patch.dict(os.environ, env, clear=False))
        return VolcengineProvider(Config())

    def test_resource_id_env_override_is_honoured(self):
        self.assertEqual(self._provider().resource_id, "volc.seedasr.auc")

    def test_submit_headers_carry_sequence_and_query_headers_do_not(self):
        provider = self._provider()
        submit = provider._headers("task-1", submit=True)
        query = provider._headers("task-1", submit=False)
        self.assertEqual(submit["X-Api-App-Key"], "app-id-value")
        self.assertEqual(submit["X-Api-Access-Key"], "access-token-value")
        self.assertEqual(submit["X-Api-Sequence"], "-1")
        self.assertNotIn("X-Api-Sequence", query)
        for headers in (submit, query):
            self.assertEqual(headers["X-Api-Resource-Id"], "volc.seedasr.auc")
            self.assertEqual(headers["X-Api-Request-Id"], "task-1")


class ProviderErrorEnvelopeTests(unittest.TestCase):
    """Error envelopes observed against the live services (identifiers masked).

    Both providers were reached for real during verification; these tests pin the
    shape of what they return when the account is not entitled to the service, so
    a future refactor cannot silently downgrade the diagnostic message.
    """

    def test_http_error_body_is_surfaced_to_the_caller(self):
        import io
        import urllib.error

        from voxsuji.providers.base import ProviderError, _http_json_ex

        # Observed verbatim from the live Volcengine endpoint (HTTP 403).
        body = (
            b'{"header":{"reqid":"<masked>","code":45000030,'
            b'"message":"[resource_id=volc.seedasr.auc] requested resource not granted"}}'
        )
        error = urllib.error.HTTPError(
            "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
            403,
            "Forbidden",
            {},
            io.BytesIO(body),
        )
        with unittest.mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as ctx:
                _http_json_ex(
                    "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
                    data=b"{}",
                    method="POST",
                )
        message = str(ctx.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("45000030", message)
        self.assertIn("not granted", message)

    def test_tencent_error_envelope_raises_provider_error(self):
        import os

        from voxsuji.config import Config
        from voxsuji.providers import tencent as tencent_module
        from voxsuji.providers.base import ProviderError

        self.enterContext(
            unittest.mock.patch.dict(
                os.environ,
                {"TENCENT_SECRET_ID": "AKIDmasked", "TENCENT_SECRET_KEY": "masked", "TENCENT_TOKEN": ""},
                clear=False,
            )
        )
        provider = tencent_module.TencentProvider(Config())
        envelope = {
            "Response": {
                "Error": {
                    "Code": "FailedOperation.UserNotRegistered",
                    "Message": "User is unopened! [appid: <masked>] [biz: ASR_OffLine]",
                },
                "RequestId": "<masked>",
            }
        }
        with unittest.mock.patch.object(tencent_module, "_http_json", return_value=(200, envelope)):
            with self.assertRaises(ProviderError) as ctx:
                provider._call("CreateRecTask", {})
        message = str(ctx.exception)
        self.assertIn("FailedOperation.UserNotRegistered", message)
        self.assertIn("ASR_OffLine", message)


class PollBehaviourTests(unittest.TestCase):
    def test_poll_times_out_with_a_diagnostic_error(self):
        from voxsuji.providers.base import ProviderError, _poll

        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return "pending", {"status": "RUNNING"}

        with self.assertRaises(ProviderError) as ctx:
            _poll(0.05, 0.01, fetch, describe="unit-test task")
        self.assertIn("did not finish within", str(ctx.exception))
        self.assertIn("RUNNING", str(ctx.exception))
        self.assertGreater(calls["n"], 1)

    def test_poll_stops_at_failure(self):
        from voxsuji.providers.base import ProviderError, _poll

        with self.assertRaises(ProviderError) as ctx:
            _poll(5, 0.01, lambda: ("failed", {"status": "FAILED", "err": "boom"}), describe="t")
        self.assertIn("boom", str(ctx.exception))

    def test_poll_returns_on_done(self):
        from voxsuji.providers.base import _poll

        self.assertEqual(_poll(5, 0.01, lambda: ("done", {"status": "SUCCEEDED"}), describe="t")["status"], "SUCCEEDED")


class CleanupOrderingTests(unittest.TestCase):
    def test_temporary_object_is_deleted_when_asr_fails(self):
        """The upload's `finally` must delete the object even if ASR blows up."""
        import tempfile
        from pathlib import Path

        from voxsuji.config import Config
        from voxsuji.transcript import _run_asr

        class FakeYtDlp:
            def __init__(self, *_, **__):
                pass

            def download_audio(self, url, out_path):
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(b"ID3fake-mp3-bytes")
                return Path(out_path)

        class FakeClient:
            def __init__(self):
                self.deleted: list[str] = []

            def put_file(self, key, path, content_type):
                self.deleted.append("")  # marker for upload
                return f"https://example.invalid/{key}"

            def delete(self, key):
                self.deleted.append(key)

        client = FakeClient()
        provider_calls = {"n": 0}

        class FailingProvider:
            name = "aliyun"

            def missing_config(self):
                return []

            def configured_model(self):
                return "m"

            def transcribe(self, url, *, language=None, audio_path=None):
                provider_calls["n"] += 1
                raise RuntimeError("provider exploded")

        config = Config()
        with unittest.mock.patch("voxsuji.transcript.YtDlp", FakeYtDlp), unittest.mock.patch(
            "voxsuji.transcript.storage.build_client", return_value=client
        ), unittest.mock.patch(
            "voxsuji.transcript.storage.verify_public_read",
            return_value={"status": 200, "content_type": "audio/mpeg", "content_length": "14"},
        ), unittest.mock.patch(
            "voxsuji.transcript.get_provider", return_value=FailingProvider()
        ):
            with self.assertRaises(RuntimeError):
                _run_asr(  # type: ignore[arg-type]
                    urls.identify("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                    config,
                    VideoMeta(id="x"),
                    "aliyun",
                    None,
                    quiet=True,
                )
        self.assertEqual(provider_calls["n"], 1)
        self.assertEqual(len(client.deleted), 2, "expected upload + delete")
        self.assertTrue(client.deleted[1].startswith("asr-tmp/"), client.deleted[1])


class CacheRoundTripTests(unittest.TestCase):
    """A cache hit must report the same facts as the original fetch."""

    def test_words_survive_cache_write_and_read(self):
        import tempfile
        from pathlib import Path

        from voxsuji.cache import Cache, store_transcript
        from voxsuji.transcript import _from_payload

        ref = urls.identify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        transcript = Transcript(
            source_url=ref.canonical_url,
            platform="youtube",
            video=VideoMeta(id=ref.video_id, title="t", duration=10.0),
            transcript_source="asr",
            provider="aliyun",
            model="m",
            duration=10.0,
            segments=[
                Segment(
                    start=0.0,
                    end=1.0,
                    text="你好",
                    words=[Word(start=0.0, end=0.5, text="你"), Word(start=0.5, end=1.0, text="好")],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            store_transcript(cache, ref, transcript)
            payload = cache.read_transcript(ref)
            self.assertTrue(payload["segments"][0]["words"])

            restored = _from_payload(payload)
            self.assertTrue(restored.segments[0].words)
            self.assertEqual(restored.segments[0].words[1].text, "好")
            self.assertTrue(restored.summary()["word_timestamps"])

    def test_existing_files_finds_raw_sidecar(self):
        import tempfile
        from pathlib import Path

        from voxsuji.cache import Cache
        from voxsuji.transcript import _existing_files

        ref = urls.identify("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp))
            raw = cache.raw_path(ref, "asr_aliyun.json")
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text("{}", encoding="utf-8")
            files = _existing_files(cache, ref)
            self.assertIn("raw", files)
            self.assertTrue(files["raw"].endswith("asr_aliyun.json"))


class ConfigPlaceholderTests(unittest.TestCase):
    def test_placeholders_are_not_credentials(self):
        from voxsuji.config import _is_real

        self.assertFalse(_is_real(None))
        self.assertFalse(_is_real(""))
        self.assertFalse(_is_real("CHANGE_ME"))
        self.assertTrue(_is_real("sk-real-looking-value"))


class StorageGuardTests(unittest.TestCase):
    def test_verify_public_read_rejects_non_audio(self):
        # A data URL cannot be fetched by urlopen, so this exercises the error path.
        with self.assertRaises(storage.StorageError):
            storage.verify_public_read("https://10.255.255.1/nope.mp3", timeout=0.5)


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path

from app.core.tts_guidance import (
    EMOTION_NAMES,
    build_voice_instruction,
    edge_prosody,
    emotion_text_to_vector,
)
from app.services.line_service import LineService


class FakeProviderRepository:
    def __init__(self, provider_type: str):
        self.provider = SimpleNamespace(provider_type=provider_type)

    def get_by_id(self, provider_id):
        return self.provider


class TTSGuidanceTest(unittest.TestCase):
    def test_every_emotion_candidate_has_a_nonzero_vector(self):
        for emotion in EMOTION_NAMES:
            with self.subTest(emotion=emotion):
                self.assertTrue(any(emotion_text_to_vector(emotion, "中等")))

    def test_strength_scales_emotion_vector_and_edge_prosody(self):
        weak_vector = emotion_text_to_vector("紧张", "微弱")
        strong_vector = emotion_text_to_vector("紧张", "强烈")
        self.assertGreater(sum(strong_vector), sum(weak_vector))

        weak_edge = edge_prosody("紧张", "微弱", None)
        strong_edge = edge_prosody("紧张", "强烈", None)
        self.assertNotEqual(weak_edge["rate"], strong_edge["rate"])
        self.assertNotEqual(weak_edge["pitch"], strong_edge["pitch"])

    def test_explicit_edge_guidance_overrides_approximate_emotion_profile(self):
        result = edge_prosody("平静", "中等", "语速放慢，用轻声反问")
        self.assertEqual(result["rate"], "-12%")
        self.assertEqual(result["volume"], "-10%")

    def test_voice_instruction_preserves_explicit_strong_delivery(self):
        instruction = build_voice_instruction("委屈", "较强", "句尾收住")
        self.assertIn("本句语气委屈", instruction)
        self.assertIn("关键转折", instruction)
        self.assertIn("本句具体要求：句尾收住", instruction)

    def test_subtle_native_direction_avoids_categorical_emotion_triggers(self):
        for strength in ("微弱", "稍弱", None):
            instruction = build_voice_instruction("害怕", strength, "向对方确认，句尾短收")
            self.assertNotIn("害怕", instruction)
            self.assertNotIn("情绪强度", instruction)
            self.assertIn("日常交谈", instruction)
            self.assertIn("句尾短收", instruction)

    def test_edge_neutral_and_emotion_strength_do_not_change_loudness(self):
        self.assertEqual(edge_prosody(None, None, None), {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
        for strength in ("微弱", "稍弱", "中等", "较强", "强烈"):
            self.assertEqual(edge_prosody("生气", strength, None)["volume"], "+0%")

    def test_negative_edge_notes_never_enable_the_forbidden_effect(self):
        for note in ("不要大声，不要提高音调，不要加快", "别用耳语，不必放慢", "避免低沉，正常语速", "不要表现得害怕"):
            self.assertEqual(edge_prosody(None, None, note), {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
        self.assertEqual(edge_prosody("平静", "微弱", "不要大声，但稍慢回应")["rate"], "-6%")

    def test_actual_qwen_request_uses_new_direction_with_original_text(self):
        provider = SimpleNamespace(provider_type="cloud", model="qwen-audio-3.0-tts-plus", status=1,
                                   custom_params={}, api_base_url="https://example.com/api/v1", api_key=None)
        repo = Mock(); repo.get_by_id.return_value = provider
        service = LineService(None, None, repo)
        response = Mock(status_code=200, headers={"content-type": "audio/mpeg"}, content=b"x" * 128)
        with tempfile.TemporaryDirectory() as directory, patch("app.core.tts_engine.requests.post", return_value=response) as post:
            service.generate_audio(None, 1, "你怎么知道？", None, [0.0] * 8,
                                   str(Path(directory) / "take.mp3"),
                                   voice=SimpleNamespace(description="qwen_voice:longanlingxin"),
                                   emotion_name="疑惑", strength_name="稍弱", production_note="向对方确认，句尾短收")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["input"]["text"], "你怎么知道？")
        self.assertIn("日常交谈", payload["input"]["instruction"])
        self.assertIn("句尾短收", payload["input"]["instruction"])
        self.assertNotIn("疑惑", payload["input"]["instruction"])
        self.assertNotIn("emotion_vector", payload)

    def test_actual_cosyvoice_request_neutralizes_subtle_emotion(self):
        provider = SimpleNamespace(provider_type="cloud", model="cosyvoice-v3-flash", status=1,
                                   custom_params={}, api_base_url="https://example.com/api/v1", api_key=None)
        repo = Mock(); repo.get_by_id.return_value = provider
        service = LineService(None, None, repo)
        with tempfile.TemporaryDirectory() as directory, patch("dashscope.audio.tts_v2.SpeechSynthesizer") as synth:
            synth.return_value.call.return_value = b"x" * 128
            service.generate_audio(None, 1, "谁？", None, [0.0] * 8, str(Path(directory) / "take.mp3"),
                                   voice=SimpleNamespace(description="cosyvoice_voice:longanyang"),
                                   emotion_name="害怕", strength_name="微弱", production_note="不要大声，句尾短收")
        self.assertEqual(synth.call_args.kwargs["instruction"], "你说话的情感是neutral。")
        self.assertNotIn("volume", synth.call_args.kwargs)
        self.assertNotIn("speech_rate", synth.call_args.kwargs)

    def test_edge_provider_keeps_guidance_even_when_auto_route_prefers_cloud(self):
        service = LineService(None, None, FakeProviderRepository("edge"))
        service.generate_edge_audio = Mock(return_value=b"audio")
        role = SimpleNamespace(name="配角", tts_route="auto", role_importance="supporting", edge_voice=None)
        voice = SimpleNamespace(description="edge_voice:zh-CN-XiaoxiaoNeural")

        result = service.generate_audio(
            None,
            1,
            "你怎么知道我在这儿？",
            None,
            [0.0] * 8,
            "/tmp/unused.wav",
            role=role,
            voice=voice,
            line_type="dialogue",
            track="voice",
            emotion_name="紧张",
            strength_name="较强",
            production_note="轻声反问",
        )

        self.assertEqual(result, b"audio")
        kwargs = service.generate_edge_audio.call_args.kwargs
        self.assertEqual(kwargs["emotion_name"], "紧张")
        self.assertEqual(kwargs["strength_name"], "较强")
        self.assertEqual(kwargs["production_note"], "轻声反问")
        self.assertIn("关键转折", kwargs["instruction"])


if __name__ == "__main__":
    unittest.main()

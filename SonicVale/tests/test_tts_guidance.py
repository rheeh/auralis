import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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
        self.assertEqual(result["rate"], "-20%")
        self.assertEqual(result["volume"], "-25%")

    def test_voice_instruction_names_emotional_strength(self):
        instruction = build_voice_instruction("委屈", "较强", "句尾收住")
        self.assertIn("情绪：委屈", instruction)
        self.assertIn("情绪强度：较强", instruction)
        self.assertIn("声音指导：句尾收住", instruction)

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
        self.assertIn("情绪强度：较强", kwargs["instruction"])


if __name__ == "__main__":
    unittest.main()

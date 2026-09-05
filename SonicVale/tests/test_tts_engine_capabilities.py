import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app.core.tts_engine import ConfigurableCloudTTSEngine


class ConfigurableCloudTTSEngineCapabilityTests(unittest.TestCase):
    def test_qwen_voice_identifier_survives_user_display_name_change(self):
        from app.services.line_service import LineService
        voice = SimpleNamespace(name="我的男主角", description="系统音色,Qwen3-TTS,qwen_voice:Moon")
        self.assertEqual(LineService.resolve_cosyvoice_voice(voice), "Moon")
        voice.description = "预置,cosyvoice_voice:longanyang"
        self.assertEqual(LineService.resolve_cosyvoice_voice(voice), "longanyang")

    def make_engine(self, model, params=None):
        return ConfigurableCloudTTSEngine(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="test-key",
            model=model,
            custom_params=params or {"driver": "dashscope_cosyvoice"},
        )

    def test_cosyvoice_v1_uses_mapped_mode_without_instruction(self):
        engine = self.make_engine("cosyvoice-v1")
        self.assertEqual(engine._cosyvoice_instruction_mode(), "mapped")
        self.assertIsNone(engine._prepare_cosyvoice_instruction("开心而急促"))

    def test_cosyvoice_v3_flash_builds_supported_structured_instruction(self):
        engine = self.make_engine("cosyvoice-v3-flash")
        self.assertEqual(engine._cosyvoice_instruction_mode(), "structured")
        self.assertEqual(
            engine._prepare_cosyvoice_instruction("语速偏快，开心而兴奋"),
            "你说话的情感是happy。",
        )

    def test_cosyvoice_structured_mode_understands_richer_emotion_aliases(self):
        engine = self.make_engine("cosyvoice-v3-flash")
        self.assertEqual(
            engine._prepare_cosyvoice_instruction("情绪：委屈。情绪强度：较强"),
            "你说话的情感是sad。",
        )

    def test_existing_structured_fear_instruction_is_not_lost(self):
        engine = self.make_engine("cosyvoice-v3-flash")
        self.assertEqual(engine._prepare_cosyvoice_instruction("你说话的情感是fearful。"), "你说话的情感是fearful。")

    def test_non_instruct_system_voice_is_mapped_even_with_provider_override(self):
        engine = self.make_engine("cosyvoice-v3-flash", {"instruction_mode": "structured"})
        self.assertEqual(engine._cosyvoice_instruction_mode("longsanshu_v3"), "mapped")
        self.assertIsNone(engine._prepare_cosyvoice_instruction("克制紧张，耳语", "longsanshu_v3"))
        self.assertEqual(engine._cosyvoice_instruction_mode("longanhuan_v3"), "mapped")

    def test_cosyvoice_plus_clone_does_not_accept_free_instructions(self):
        engine = self.make_engine("cosyvoice-v3-plus")
        self.assertEqual(engine._cosyvoice_instruction_mode("cosyvoice-v3-plus-myvoice-123"), "mapped")
        self.assertEqual(engine._cosyvoice_instruction_mode("longanyang"), "structured")

    def test_cosyvoice_flash_clone_uses_native_direction(self):
        engine = self.make_engine("cosyvoice-v3-flash")
        self.assertEqual(engine._cosyvoice_instruction_mode("cosyvoice-v3-flash-myvoice-123"), "native")

    def test_native_instruction_obeys_cjk_weighted_length_limit(self):
        engine = self.make_engine("cosyvoice-v3.5-flash")
        self.assertEqual(engine._prepare_cosyvoice_instruction("轻" * 70), "轻" * 50)

    def test_prosody_keeps_fractional_multiplier_and_avoids_extreme_shifts(self):
        kwargs = {"speech_rate": 0.88, "pitch_rate": 1.0}
        ConfigurableCloudTTSEngine._apply_prosody_controls(kwargs, "克制，稍慢，声音低沉")
        self.assertEqual(kwargs["speech_rate"], 0.88)
        self.assertEqual(kwargs["pitch_rate"], 0.97)
        ConfigurableCloudTTSEngine._validate_cosyvoice_prosody(kwargs)

    def test_percent_prosody_is_rejected_before_network_request(self):
        with self.assertRaisesRegex(ValueError, "倍率"):
            ConfigurableCloudTTSEngine._validate_cosyvoice_prosody({"speech_rate": -20})

    def test_sdk_request_for_mapped_voice_drops_instructions_and_uses_valid_rate(self):
        engine = self.make_engine("cosyvoice-v3-flash", {"instruction_mode": "structured", "instruction": "你说话的情感是happy。"})
        with tempfile.TemporaryDirectory() as directory, patch("dashscope.audio.tts_v2.SpeechSynthesizer") as synthesizer:
            synthesizer.return_value.call.return_value = b"x" * 128
            engine.synthesize("不要开门。", str(Path(directory) / "take.mp3"), voice_name="longsanshu_v3", instruction="放慢、低声、克制")
        self.assertNotIn("instruction", synthesizer.call_args.kwargs)
        self.assertEqual(synthesizer.call_args.kwargs["speech_rate"], 0.94)

    def test_mapped_prosody_uses_emotional_strength(self):
        kwargs = {}
        ConfigurableCloudTTSEngine._apply_prosody_controls(
            kwargs,
            "情绪：愤怒。情绪强度：强烈。声音指导：大声",
        )
        self.assertEqual(kwargs["volume"], 65)

    def test_cosyvoice_v35_keeps_native_instruction(self):
        engine = self.make_engine("cosyvoice-v3.5-flash")
        self.assertEqual(engine._cosyvoice_instruction_mode(), "native")
        self.assertEqual(
            engine._prepare_cosyvoice_instruction("温柔克制地说，句尾轻轻收住。"),
            "温柔克制地说，句尾轻轻收住。",
        )

    def test_http_template_can_render_instruction(self):
        engine = ConfigurableCloudTTSEngine(
            "https://example.com/v1/audio/speech",
            model="gpt-4o-mini-tts",
            custom_params={
                "driver": "http",
                "payload": {
                    "model": "{{model}}",
                    "input": "{{text}}",
                    "voice": "{{voice}}",
                    "instructions": "{{instruction}}",
                },
            },
        )
        payload = engine._build_payload(
            "测试台词", "alloy", None, None, None, "低声且克制", engine._resolve_request_url(),
        )
        self.assertEqual(payload["instructions"], "低声且克制")

    def test_qwen_instruct_uses_plural_input_field_automatically(self):
        engine = self.make_engine("qwen3-tts-instruct-flash-2026-01-26", {"driver": "http", "language_type": "Chinese"})
        payload = engine._build_payload("别开门。", "Moon", None, None, None, "低声克制", engine._resolve_request_url())
        self.assertEqual(payload["input"]["instructions"], "低声克制")
        self.assertNotIn("instruction", payload["input"])
        self.assertEqual(payload["input"]["text"], "别开门。")

    def test_qwen_audio_http_endpoint_and_singular_instruction(self):
        engine = self.make_engine("qwen-audio-3.0-tts-plus", {"driver": "dashscope_cosyvoice", "language_type": "Chinese", "language_hints": ["zh"], "sample_rate": 24000})
        self.assertEqual(engine._driver(), "http")
        self.assertEqual(engine._resolve_request_url(), "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer")
        payload = engine._build_payload("别开门。", "longanlufeng", None, None, None, "低声克制", engine._resolve_request_url())
        self.assertEqual(payload["input"], {"text": "别开门。", "voice": "longanlufeng", "format": "mp3", "language_hints": ["zh"], "sample_rate": 24000, "instruction": "低声克制"})

    def test_qwen_audio_rejects_cross_model_voice_before_request(self):
        engine = self.make_engine("qwen-audio-3.0-tts-plus", {"driver": "http"})
        for voice in ("Moon", "longanfengyue", "qwen-audio-3.0-tts-flash-other"):
            with self.subTest(voice=voice), patch("app.core.tts_engine.requests.post") as request:
                with self.assertRaisesRegex(ValueError, "不属于"):
                    engine.synthesize("别开门。", "/tmp/unused.mp3", voice_name=voice)
                request.assert_not_called()

    def test_qwen_audio_workspace_endpoint_and_neutral_take(self):
        engine = ConfigurableCloudTTSEngine("https://sample.cn-beijing.maas.aliyuncs.com/api/v1", model="qwen-audio-3.0-tts-flash")
        self.assertEqual(engine._resolve_request_url(), "https://sample.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer")
        payload = engine._build_payload("别开门。", None, None, None, None, "", engine._resolve_request_url())
        self.assertEqual(payload["input"]["voice"], "longanfengyue")
        self.assertNotIn("instruction", payload["input"])

    def test_qwen_audio_explicit_instruction_disable(self):
        engine = self.make_engine("qwen-audio-3.0-tts-plus", {"supports_instruction": False})
        payload = engine._build_payload("别开门。", "qwen-audio-3.0-tts-plus-example", None, None, None, "低声克制", engine._resolve_request_url())
        self.assertNotIn("instruction", payload["input"])

    def test_qwen_base_model_does_not_receive_acting_instructions(self):
        engine = self.make_engine("qwen3-tts-flash", {"driver": "http"})
        payload = engine._build_payload("别开门。", "Moon", None, None, None, "低声克制", engine._resolve_request_url())
        self.assertNotIn("instructions", payload["input"])

    def test_explicit_disable_wins_for_qwen_instruct(self):
        engine = self.make_engine("qwen3-tts-instruct-flash", {"driver": "http", "supports_instruction": False})
        payload = engine._build_payload("别开门。", "Moon", None, None, None, "低声克制", engine._resolve_request_url())
        self.assertNotIn("instructions", payload["input"])

    def test_instruction_field_supports_nested_provider_payload(self):
        engine = ConfigurableCloudTTSEngine(
            "https://example.com/tts",
            model="vendor-instruct-tts",
            custom_params={"driver": "http", "instruction_field": "options.style_instruction"},
        )
        payload = engine._build_payload(
            "测试台词", "speaker-a", None, None, None, "悲伤而缓慢", engine._resolve_request_url(),
        )
        self.assertEqual(payload["options"]["style_instruction"], "悲伤而缓慢")


if __name__ == "__main__":
    unittest.main()

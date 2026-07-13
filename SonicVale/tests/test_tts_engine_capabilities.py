import unittest

from app.core.tts_engine import ConfigurableCloudTTSEngine


class ConfigurableCloudTTSEngineCapabilityTests(unittest.TestCase):
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

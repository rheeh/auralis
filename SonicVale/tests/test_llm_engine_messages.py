import unittest
from types import SimpleNamespace

from app.core.llm_engine import LLMEngine


class FakeAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


def make_engine(*outcomes) -> tuple[LLMEngine, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    engine = LLMEngine.__new__(LLMEngine)
    engine.model_name = "test-model"
    engine.custom_params = {"temperature": 0}
    engine.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return engine, completions


class LLMEngineMessageTest(unittest.TestCase):
    def test_system_and_user_are_sent_as_separate_messages(self):
        engine, completions = make_engine("完成")

        result = engine.generate_text("本轮输入", system_prompt="固定规则", retries=1)

        self.assertEqual(result, "完成")
        self.assertEqual(completions.calls[0]["messages"], [
            {"role": "system", "content": "固定规则"},
            {"role": "user", "content": "本轮输入"},
        ])

    def test_json_schema_is_declared_through_response_format(self):
        schema = {
            "type": "object",
            "properties": {"reply": {"type": "string"}},
            "required": ["reply"],
            "additionalProperties": False,
        }
        engine, completions = make_engine('{"reply":"完成"}')

        result = engine.generate_json(
            "工具结果",
            system_prompt="只返回 JSON",
            json_schema=schema,
            schema_name="assistant_reply",
        )

        self.assertEqual(result, '{"reply":"完成"}')
        response_format = completions.calls[0]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["schema"], schema)
        self.assertNotIn("JSON Schema", completions.calls[0]["messages"][1]["content"])

    def test_structured_output_falls_back_for_compatible_providers(self):
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        engine, completions = make_engine(
            FakeAPIError("json_schema is not supported", 400),
            FakeAPIError("unknown response_format", 400),
            '{"ok":true}',
        )

        result = engine.generate_json(
            "执行检查",
            system_prompt="只返回 JSON",
            json_schema=schema,
            schema_name="status",
        )

        self.assertEqual(result, '{"ok":true}')
        self.assertEqual(len(completions.calls), 3)
        self.assertEqual(completions.calls[0]["response_format"]["type"], "json_schema")
        self.assertEqual(completions.calls[1]["response_format"]["type"], "json_object")
        self.assertNotIn("response_format", completions.calls[2])
        self.assertIn("JSON Schema", completions.calls[2]["messages"][1]["content"])

    def test_auth_failure_does_not_trigger_compatibility_fallback(self):
        engine, completions = make_engine(FakeAPIError("unauthorized", 401))

        with self.assertRaises(FakeAPIError):
            engine.generate_json(
                "执行检查",
                system_prompt="只返回 JSON",
                json_schema={"type": "object"},
            )

        self.assertEqual(len(completions.calls), 1)


if __name__ == "__main__":
    unittest.main()

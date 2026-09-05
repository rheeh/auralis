import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APIConnectionError, OpenAI, RateLimitError

from app.core.llm_engine import LLMEngine


class FakeAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int, *, code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.body = body


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

    def test_permanent_client_and_quota_errors_raise_original_error_once(self):
        errors = [
            FakeAPIError("unauthorized", 401),
            FakeAPIError("Access denied, account in arrearage", 400, code="Arrearage"),
            FakeAPIError("request not allowed", 400, body={"error": {"code": "AllocationQuota.FreeTierOnly"}}),
            FakeAPIError("quota depleted", 429, code="insufficient_quota"),
            FakeAPIError("model not found", 404),
            FakeAPIError("invalid temperature", 422),
            ValueError("local response processing failed"),
        ]
        for error in errors:
            with self.subTest(error=str(error)), patch("app.core.llm_engine.time.sleep") as sleep:
                engine, completions = make_engine(error)
                with self.assertRaises(type(error)) as raised:
                    engine.generate_text("测试输入")
                self.assertIs(raised.exception, error)
                self.assertEqual(len(completions.calls), 1)
                self.assertEqual(completions.calls[0]["model"], "test-model")
                self.assertEqual(engine.custom_params, {"temperature": 0})
                sleep.assert_not_called()

    def test_retryable_failures_retry_same_request_then_succeed(self):
        errors = [
            FakeAPIError("rate limit exceeded, try again later", 429),
            FakeAPIError("temporarily unavailable", 503),
            TimeoutError("connection timed out"),
            APIConnectionError(request=httpx.Request("POST", "https://example.test/v1/chat/completions")),
        ]
        for error in errors:
            with self.subTest(error=str(error)), patch("app.core.llm_engine.time.sleep") as sleep:
                engine, completions = make_engine(error, "成功")
                self.assertEqual(engine.generate_text("测试输入", system_prompt="固定规则"), "成功")
                self.assertEqual(len(completions.calls), 2)
                self.assertEqual(completions.calls[0], completions.calls[1])
                sleep.assert_called_once()

    def test_recoverable_failures_stop_at_attempt_limit_and_preserve_last_error(self):
        errors = [FakeAPIError(f"temporary service error {index}", 502) for index in range(3)]
        engine, completions = make_engine(*errors)
        with patch("app.core.llm_engine.time.sleep") as sleep:
            with self.assertRaises(FakeAPIError) as raised:
                engine.generate_text("测试输入", retries=3)
        self.assertIs(raised.exception, errors[-1])
        self.assertEqual(len(completions.calls), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_quota_and_unrelated_validation_failures_never_trigger_format_fallback(self):
        errors = [
            FakeAPIError("response_format not allowed while account is in arrearage", 400, code="Arrearage"),
            FakeAPIError("response_format is not allowed", 400, body={"code": "AllocationQuota.FreeTierOnly"}),
            FakeAPIError("invalid parameter: temperature", 400),
            FakeAPIError("model access not allowed", 400),
            FakeAPIError("json_schema could not be processed", 400),
        ]
        for error in errors:
            with self.subTest(error=str(error)), patch("app.core.llm_engine.time.sleep") as sleep:
                engine, completions = make_engine(error)
                with self.assertRaises(FakeAPIError) as raised:
                    engine.generate_json("执行检查", system_prompt="只返回 JSON", json_schema={"type": "object"})
                self.assertIs(raised.exception, error)
                self.assertEqual(len(completions.calls), 1)
                self.assertEqual(completions.calls[0]["response_format"]["type"], "json_schema")
                sleep.assert_not_called()

    def test_sdk_cannot_multiply_quota_failure_requests(self):
        # Real SDK against an in-memory transport: no network or user key.
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(429, json={"error": {
                "message": "Free tier exhausted; response_format not allowed",
                "type": "insufficient_quota", "code": "AllocationQuota.FreeTierOnly",
            }})

        transport = httpx.MockTransport(respond)
        with httpx.Client(transport=transport) as http_client:
            with patch("app.core.llm_engine.OpenAI", side_effect=lambda **kwargs: OpenAI(**kwargs, http_client=http_client)):
                engine = LLMEngine("unit-test-placeholder", "https://example.test/v1", "test-model", "{}")
            with self.assertRaises(RateLimitError):
                engine.generate_json("执行检查", system_prompt="只返回 JSON", json_schema={"type": "object"})
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()

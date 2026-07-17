import unittest
from types import SimpleNamespace

from pydantic import BaseModel

from app.services.workflow_llm_service import WorkflowLLMError, WorkflowLLMService
from app.workflows.drama.schemas import DramaScript, RoleDraftList, SourceAnalysis


class ExampleResponse(BaseModel):
    title: str
    items: list[str]


class FakeEngine:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return self.responses.pop(0)


def make_service(engine: FakeEngine) -> WorkflowLLMService:
    service = WorkflowLLMService.__new__(WorkflowLLMService)
    service.make_engine = lambda project: engine
    return service


class WorkflowLLMServiceTest(unittest.TestCase):
    def test_retries_when_provider_returns_empty_array_for_object_schema(self):
        engine = FakeEngine('[]', '{"title":"解析结果","items":["场景一"]}')
        service = make_service(engine)

        result = service.call_json(
            SimpleNamespace(),
            "解析小说",
            system_prompt="只返回结构化结果",
            response_model=ExampleResponse,
            schema_name="example_response",
        )

        self.assertEqual(result, {"title": "解析结果", "items": ["场景一"]})
        self.assertEqual(len(engine.calls), 2)
        self.assertIn("上一轮返回的数据结构不合格", engine.calls[1][0])
        self.assertIn("上一轮错误输出：[]", engine.calls[1][0])

    def test_accepts_single_object_wrapped_by_compatible_provider(self):
        engine = FakeEngine('[{"title":"解析结果","items":[]}]')
        service = make_service(engine)

        result = service.call_json(
            SimpleNamespace(),
            "解析小说",
            system_prompt="只返回结构化结果",
            response_model=ExampleResponse,
        )

        self.assertEqual(result["title"], "解析结果")
        self.assertEqual(len(engine.calls), 1)

    def test_returns_friendly_error_after_two_invalid_structures(self):
        engine = FakeEngine('[]', '[]')
        service = make_service(engine)

        with self.assertRaises(WorkflowLLMError) as raised:
            service.call_json(
                SimpleNamespace(),
                "解析小说",
                system_prompt="只返回结构化结果",
                response_model=ExampleResponse,
            )

        self.assertEqual(raised.exception.code, "LLM_INVALID_RESPONSE")
        self.assertNotIn("validation error", str(raised.exception).lower())

    def test_retries_empty_source_analysis_instead_of_accepting_defaults(self):
        engine = FakeEngine(
            '{}',
            '{"title":"夜班便利店","characters":[{"name":"陈默"}],'
            '"scenePlan":[{"title":"深夜便利店"}],'
            '"contentMap":[{"source":"卷帘门落下",'
            '"category":"环境动作","audioStrategy":"sfx"}]}',
        )
        service = make_service(engine)

        result = service.call_json(
            SimpleNamespace(),
            "解析小说",
            system_prompt="只返回结构化结果",
            response_model=SourceAnalysis,
        )

        self.assertEqual(result["characters"][0]["name"], "陈默")
        self.assertEqual(len(engine.calls), 2)

    def test_retries_insufficient_information_role_response(self):
        engine = FakeEngine(
            '{"status":"insufficient_information","characters":[]}',
            '{"roles":[{"draft_id":"role-chenmo","name":"陈默",'
            '"identity":"便利店店员","voice_type":"青年男声，克制沉稳"}]}',
        )
        service = make_service(engine)

        result = service.call_json(
            SimpleNamespace(),
            "生成角色草稿",
            system_prompt="只返回结构化结果",
            response_model=RoleDraftList,
        )

        self.assertEqual(result["roles"][0]["name"], "陈默")
        self.assertEqual(len(engine.calls), 2)

    def test_retries_script_that_uses_parallel_dialogue_array(self):
        engine = FakeEngine(
            '{"title":"深夜便利店","characters":[{"name":"陈默"}],'
            '"scenes":[{"title":"便利店","lines":[],"dialogues":'
            '[{"character":"陈默","text":"下班了。"}]}]}',
            '{"title":"深夜便利店","characters":[{"name":"陈默"}],'
            '"scenes":[{"title":"便利店","lines":'
            '[{"type":"dialogue","speaker":"陈默","text":"下班了。"}]}]}',
        )
        service = make_service(engine)

        result = service.call_json(
            SimpleNamespace(),
            "生成广播剧台本",
            system_prompt="所有内容写入 scenes[].lines",
            response_model=DramaScript,
        )

        self.assertEqual(result["scenes"][0]["lines"][0]["speaker"], "陈默")
        self.assertEqual(len(engine.calls), 2)


if __name__ == "__main__":
    unittest.main()

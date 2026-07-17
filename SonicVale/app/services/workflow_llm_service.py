from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.llm_engine import LLMEngine
from app.models.po import ProjectPO
from app.repositories.llm_provider_repository import LLMProviderRepository


class WorkflowLLMError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class WorkflowLLMService:
    def __init__(self, db: Session):
        self.provider_repository = LLMProviderRepository(db)

    def make_engine(self, project: ProjectPO) -> LLMEngine:
        if not project.llm_provider_id or not project.llm_model:
            raise WorkflowLLMError("LLM_PROVIDER_NOT_CONFIGURED", "请先为项目配置 LLM provider 和模型")
        provider = self.provider_repository.get_by_id(project.llm_provider_id)
        if not provider:
            raise WorkflowLLMError("LLM_PROVIDER_NOT_CONFIGURED", "项目绑定的 LLM provider 不存在")
        return LLMEngine(provider.api_key, provider.api_base_url, project.llm_model, provider.custom_params)

    def call_json(
        self,
        project: ProjectPO,
        user_prompt: str,
        *,
        system_prompt: str,
        response_model: type[BaseModel] | None = None,
        schema_name: str = "auralis_response",
    ) -> dict[str, Any]:
        json_schema = response_model.model_json_schema() if response_model else None
        try:
            engine = self.make_engine(project)
        except WorkflowLLMError:
            raise
        except Exception as exc:
            raise self._request_error(exc) from exc

        prompt = user_prompt
        for attempt in range(2):
            try:
                content = engine.generate_json(
                    prompt,
                    system_prompt=system_prompt,
                    json_schema=json_schema,
                    schema_name=schema_name,
                )
            except WorkflowLLMError:
                raise
            except Exception as exc:
                raise self._request_error(exc) from exc

            try:
                parsed = self._decode_json(content)
                if response_model:
                    # Some compatible providers wrap an object in a one-item array
                    # even when the declared top-level schema is an object.
                    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                        parsed = parsed[0]
                    if not isinstance(parsed, dict):
                        raise ValueError(
                            f"响应顶层应为 JSON 对象，实际为 {type(parsed).__name__}"
                        )
                    return response_model.model_validate(parsed).model_dump(mode="json")
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"响应顶层应为 JSON 对象，实际为 {type(parsed).__name__}"
                    )
                return parsed
            except (ValueError, ValidationError) as exc:
                if attempt == 0:
                    prompt = self._retry_prompt(user_prompt, content, exc, json_schema)
                    continue
                raise WorkflowLLMError(
                    "LLM_INVALID_RESPONSE",
                    "模型连续返回了不符合要求的数据结构，请重试当前步骤",
                ) from exc

        raise WorkflowLLMError("LLM_INVALID_RESPONSE", "模型返回的结构无法解析，请重试当前步骤")

    @staticmethod
    def _decode_json(content: Any) -> Any:
        text = str(content or "").strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
        if fenced:
            text = fenced.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            raise ValueError("模型返回的内容不是合法 JSON")

    @staticmethod
    def _retry_prompt(
        original_prompt: str,
        content: Any,
        error: Exception,
        json_schema: dict[str, Any] | None,
    ) -> str:
        previous = str(content or "").strip()
        if len(previous) > 4000:
            previous = previous[:4000] + "…"
        schema_hint = ""
        if json_schema:
            schema_hint = "\n必须符合以下 JSON Schema：\n" + json.dumps(json_schema, ensure_ascii=False)
        return (
            original_prompt
            + "\n\n上一轮返回的数据结构不合格，请重新分析原始任务并完整生成结果。"
            + "不要解释、不要使用 Markdown，只返回一个 JSON 对象。"
            + f"\n校验问题：{error}"
            + f"\n上一轮错误输出：{previous or '<空响应>'}"
            + schema_hint
        )

    @staticmethod
    def _request_error(exc: Exception) -> WorkflowLLMError:
        if isinstance(exc, TimeoutError):
            return WorkflowLLMError("LLM_TIMEOUT", "模型响应超时，请稍后重试当前步骤")
        message = str(exc)
        lowered = message.lower()
        if "401" in message or "unauthorized" in lowered or "api key" in lowered:
            code, friendly = "LLM_AUTH_FAILED", "模型鉴权失败，请检查 API Key"
        elif "429" in message or "rate limit" in lowered:
            code, friendly = "LLM_RATE_LIMITED", "模型请求过于频繁，请稍后重试"
        else:
            code, friendly = "LLM_REQUEST_FAILED", "模型服务暂时不可用，请重试当前步骤"
        return WorkflowLLMError(code, friendly)

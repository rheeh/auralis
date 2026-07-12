from __future__ import annotations

import json
import re
from typing import Any

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

    def call_json(self, project: ProjectPO, prompt: str) -> dict[str, Any]:
        try:
            content = self.make_engine(project).generate_text(prompt)
        except WorkflowLLMError:
            raise
        except TimeoutError as exc:
            raise WorkflowLLMError("LLM_TIMEOUT", "模型响应超时，请稍后重试当前步骤") from exc
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if "401" in message or "unauthorized" in lowered or "api key" in lowered:
                code, friendly = "LLM_AUTH_FAILED", "模型鉴权失败，请检查 API Key"
            elif "429" in message or "rate limit" in lowered:
                code, friendly = "LLM_RATE_LIMITED", "模型请求过于频繁，请稍后重试"
            else:
                code, friendly = "LLM_REQUEST_FAILED", "模型服务暂时不可用，请重试当前步骤"
            raise WorkflowLLMError(code, friendly) from exc

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
            raise WorkflowLLMError("LLM_INVALID_RESPONSE", "模型返回的结构无法解析，请重试当前步骤")

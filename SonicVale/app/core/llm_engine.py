import json
import logging
import random
import re
import time
from typing import Any

from openai import APIConnectionError, OpenAI

from app.core.prompts import get_auto_fix_json_prompt


class LLMEngine:
    def __init__(self, api_key: str, base_url: str, model_name: str, custom_params: str):
        """
        api_key: LLM API Key
        base_url: OpenAI-compatible API URL（例如企业版/自建 LLM）
        model_name: 模型名称
        custom_params: 自定义参数（JSON字符串）
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")  # 去掉末尾斜杠
        self.model_name = model_name
        
        # custom_params从string转为dict
        custom_params = json.loads(custom_params)
        if not isinstance(custom_params, dict):
            raise ValueError("无效的 custom_params")
        self.custom_params = custom_params
        
        # 使用新版 OpenAI 客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            # One retry policy owns the request count. Otherwise SDK retries
            # multiply each outer attempt, including provider quota failures.
            max_retries=0,
        )

    def _extract_result_tag(self, text: str) -> str:
        """提取 <result> 标签内容"""
        match = re.search(r"<result>(.*?)</result>", text, re.DOTALL)
        if not match:
            raise ValueError("Response does not contain <result>...</result> tag")
        return match.group(1).strip()

    @staticmethod
    def _messages(prompt: str, system_prompt: str | None = None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _completion(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_format: dict[str, Any] | None = None,
        remove_custom_response_format: bool = False,
        retries: int = 3,
        delay: float = 1.0,
    ) -> str:
        request_params = dict(self.custom_params)
        if remove_custom_response_format:
            request_params.pop("response_format", None)
        if response_format is not None:
            request_params["response_format"] = response_format

        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=self._messages(prompt, system_prompt),
                    stream=False,
                    timeout=3000,
                    **request_params,
                )
                return response.choices[0].message.content
            except Exception as exc:
                if self._retryable_error(exc) and attempt < retries - 1:
                    sleep_time = delay * (2 ** attempt) + random.random()
                    time.sleep(sleep_time)
                else:
                    raise

    @staticmethod
    def _error_text(exc: Exception) -> str:
        parts = [str(exc), str(getattr(exc, "code", "") or "")]
        body = getattr(exc, "body", None)
        if isinstance(body, (dict, list)):
            parts.append(json.dumps(body, ensure_ascii=False, default=str))
        elif isinstance(body, str):
            parts.append(body)
        return " ".join(parts).lower()

    @classmethod
    def _permanent_provider_failure(cls, exc: Exception) -> bool:
        # A provider can report depleted credit/free-tier access as 400 or 429.
        # Neither retrying nor dropping response_format can make that payable
        # request succeed under the user's existing account constraints.
        message = cls._error_text(exc)
        return any(term in message for term in (
            "arrearage", "allocationquota.freetieronly", "freetieronly", "free_tier_only",
            "insufficient_quota", "quota_exhausted", "insufficientbalance", "insufficient_balance",
            "billing_hard_limit", "billing_not_active", "payment_required",
            "invalid_api_key", "invalidapikey", "unauthorized", "authentication",
            "permission_denied", "access_denied", "accessdenied",
            "余额不足", "免费额度已用尽", "免费额度用尽",
        ))

    @classmethod
    def _retryable_error(cls, exc: Exception) -> bool:
        if cls._permanent_provider_failure(exc):
            return False
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code == 429 or 500 <= status_code <= 599
        return isinstance(exc, (APIConnectionError, ConnectionError, TimeoutError))

    @classmethod
    def _structured_output_unsupported(cls, exc: Exception) -> bool:
        if cls._permanent_provider_failure(exc):
            return False
        status_code = getattr(exc, "status_code", None)
        message = cls._error_text(exc)
        format_terms = ("response_format", "json_schema", "json schema", "structured output")
        unsupported_terms = (
            "unsupported", "not support", "doesn't support", "unknown", "unrecognized", "invalid parameter",
            "invalid value", "extra inputs", "not permitted", "not allowed",
        )
        return status_code in {400, 404, 422} and (
            any(term in message for term in format_terms)
            and any(term in message for term in unsupported_terms)
        )

    def generate_text_test(self, prompt: str, system_prompt: str | None = None) -> str:
        """
        测试：生成结果并返回（非流式）
        """
        return self._completion(prompt, system_prompt=system_prompt, retries=1)

    def generate_text(
        self,
        prompt: str,
        retries: int = 3,
        delay: float = 1.0,
        system_prompt: str | None = None,
    ) -> str:
        """非流式文本生成，兼容原有单 user prompt 调用。"""
        return self._completion(
            prompt,
            system_prompt=system_prompt,
            retries=retries,
            delay=delay,
        )

    def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str,
        json_schema: dict[str, Any] | None = None,
        schema_name: str = "auralis_response",
    ) -> str:
        """Prefer native structured output and degrade for OpenAI-compatible providers."""
        response_formats: list[dict[str, Any]] = []
        if json_schema:
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", schema_name)[:64] or "auralis_response"
            response_formats.append({
                "type": "json_schema",
                "json_schema": {
                    "name": safe_name,
                    "strict": False,
                    "schema": json_schema,
                },
            })
        response_formats.append({"type": "json_object"})

        for response_format in response_formats:
            try:
                return self._completion(
                    prompt,
                    system_prompt=system_prompt,
                    response_format=response_format,
                    remove_custom_response_format=True,
                    retries=1,
                )
            except Exception as exc:
                if not self._structured_output_unsupported(exc):
                    raise

        fallback_prompt = prompt
        if json_schema:
            fallback_prompt += (
                "\n\n当前模型接口不支持原生结构化输出。请只返回符合以下 JSON Schema 的 JSON，"
                "不要使用 Markdown 代码块：\n" + json.dumps(json_schema, ensure_ascii=False)
            )
        else:
            fallback_prompt += "\n\n请只返回一个合法 JSON 对象，不要使用 Markdown 代码块。"
        return self._completion(
            fallback_prompt,
            system_prompt=system_prompt,
            remove_custom_response_format=True,
        )

    def save_load_json(self, json_str: str):
        """解析JSON，支持自动提取<result>标签内容"""
        # 先尝试提取 <result> 标签内容
        try:
            json_str = self._extract_result_tag(json_str)
        except ValueError:
            # 没有 <result> 标签，直接使用原文本
            pass
        
        # 尝试加载json
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # JSON解析失败，尝试让LLM修复
            prompt = get_auto_fix_json_prompt(json_str)
            res = self.generate_text(prompt)
            # 递归调用，修复后的结果也可能包含 <result> 标签
            return self.save_load_json(res)

    def generate_smart_text(self, prompt: str, system_prompt: str | None = None) -> str:
        """
        智能文本生成（流式）
        """
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._messages(prompt, system_prompt),
            stream=True,
            timeout=3000
        )

        # 拼接 delta.content
        full_text = ""
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                content = delta.content if hasattr(delta, 'content') else None
                if content:
                    # print(content, end="", flush=True)
                    full_text += content

        logging.debug("流式生成完成")
        return full_text

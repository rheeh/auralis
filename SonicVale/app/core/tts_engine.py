from __future__ import annotations

import asyncio
import base64
import json
import shutil

import requests
from typing import Optional, List, Any
import os
import logging
from urllib.parse import urlparse, urlunparse

class TTSEngine:
    def __init__(self, base_url: str, api_key: str | None = None):
        """
        初始化 TTS 引擎
        :param base_url: TTS 服务的基础 URL，如 http://127.0.0.1:8000
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def synthesize(
        self,
        text: str,
        filename: str,
        emo_text: Optional[str] = None,
        emo_vector: Optional[List[float]] = None,
        save_path: Optional[str] = None
    ) -> bytes:
        """
        调用 /v2/synthesize 接口进行语音合成
        :param text: 要合成的文本
        :param filename: 参考音频文件名（服务端已存在）
        :param emo_text: 情绪文本（可选）
        :param emo_vector: 8维情绪向量（可选，优先级高于 emo_text）
        :param save_path: 如果指定，将保存生成的音频文件到本地
        :return: 音频二进制数据
        """
        url = f"{self.base_url}/v2/synthesize"

        payload = {"text": text, "audio_path": filename}

        if emo_vector is not None:
            payload["emo_vector"] = emo_vector
        elif emo_text:
            payload["emo_text"] = emo_text

        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                # 尝试解析错误信息
                try:
                    error_data = resp.json()
                    error_msg = error_data.get('detail') or error_data.get('message') or error_data.get('msg') or resp.text
                except:
                    error_msg = resp.text
                raise Exception(f"TTS服务返回错误({resp.status_code}): {error_msg}")

            audio_bytes = resp.content
            
            # 检查返回的内容是否为有效音频
            if len(audio_bytes) < 100:
                raise Exception(f"TTS服务返回的音频数据无效，大小: {len(audio_bytes)} 字节")

            if save_path:
                with open(save_path, "wb") as f:
                    f.write(audio_bytes)

            return audio_bytes
            
        except requests.exceptions.ConnectionError:
            raise Exception(f"TTS服务连接失败，请检查TTS服务是否已启动 ({self.base_url})")
        except requests.exceptions.Timeout:
            raise Exception(f"TTS服务请求超时，请检查TTS服务是否正常运行")
        except requests.exceptions.RequestException as e:
            raise Exception(f"TTS服务请求异常: {str(e)}")

    def get_models(self) -> dict:
        """
        调用 /v1/models 获取模型列表
        :return: 模型信息
        """
        url = f"{self.base_url}/v1/models"
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()

    def check_audio_exists(self, filename: str) -> bool:
        """
        调用 /v1/check/audio 检查参考音频是否存在
        :param filename: 原始文件名
        :return: True or False
        """
        url = f"{self.base_url}/v1/check/audio"
        params = {"file_name": filename}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("exists", False)

    def upload_audio(self, file_path: str,full_path=None) -> dict:
        """
                调用 /v1/upload_audio 上传音频
                :param file_path: 本地音频文件路径
                :param full_path: 用于唯一标识的全路径（可选，如果不传则使用 file_path）
                :return: 服务端响应 JSON
                """
        if not os.path.isfile(file_path):
            return {"code": 400, "msg": f"文件不存在: {file_path}"}

        url = f"{self.base_url}/v1/upload_audio"
        try:
            with open(file_path, "rb") as f:
                files = {
                    "audio": (os.path.basename(file_path), f, "audio/wav")
                }
                # 如果需要额外传 fullpath 参数
                data = {}
                if full_path:
                    data["full_path"] = full_path

                resp = requests.post(url, files=files, data=data, timeout=30)
                resp.raise_for_status()
                return resp.json()
        except requests.exceptions.RequestException as e:
            return {"code": 500, "msg": f"请求失败: {str(e)}"}
        except Exception as e:
            return {"code": 500, "msg": f"上传异常: {str(e)}"}


class EdgeTTSEngine:
    """微软 Edge-TTS 免费中文神经音色。运行时才导入 edge_tts，避免未安装依赖时影响应用启动。"""

    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

    def synthesize(
        self,
        text: str,
        save_path: str,
        voice: str | None = None,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        if not save_path:
            raise ValueError("Edge-TTS 需要有效的保存路径")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        voice_name = voice or self.DEFAULT_VOICE

        try:
            import edge_tts
        except Exception as exc:
            raise RuntimeError("Edge-TTS 依赖未安装，请先安装 requirements.txt 中的 edge-tts") from exc

        async def _run() -> None:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_name,
                rate=rate,
                volume=volume,
                pitch=pitch,
            )
            await communicate.save(save_path)

        try:
            asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()

        with open(save_path, "rb") as f:
            audio_bytes = f.read()
        if len(audio_bytes) < 100:
            raise RuntimeError("Edge-TTS 返回的音频数据无效")
        return audio_bytes


class ConfigurableCloudTTSEngine:
    """
    可配置云端 TTS。model 和 custom_params 由用户配置。
    custom_params 支持:
    - driver: auto/http/dashscope_cosyvoice/dashscope_sambert
    - headers: 额外请求头
    - auth_header/auth_prefix: API Key 请求头名和前缀，默认 Authorization: Bearer ...
    - endpoint: 完整请求地址，优先级高于 api_base_url 自动推断
    - payload/body: 完整 JSON 请求体模板
    - query: URL 查询参数
    - audio_base64_path/audio_url_path/audio_path_path: JSON 响应中的音频字段路径
    - voice/language_type/format/sample_rate/rate/pitch/volume: 常用 TTS 参数
    - instruction_mode: native/structured/mapped/none，声明模型的指令能力
    - instruction_field: 通用 HTTP 请求中声音指令的字段路径，如 instructions 或 input.instruction
    模板字符串可使用 {{text}}、{{model}}、{{voice}}、{{reference_path}}、{{emotion}}、{{instruction}}。
    """

    def __init__(
        self,
        api_base_url: str,
        api_key: str | None = None,
        model: str | None = None,
        custom_params: str | dict[str, Any] | None = None,
    ):
        if not api_base_url:
            raise ValueError("云端 TTS 地址未配置")
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.model = model
        self.custom_params = self._parse_params(custom_params)

    def synthesize(
        self,
        text: str,
        save_path: str,
        voice_name: str | None = None,
        reference_path: str | None = None,
        emo_text: str | None = None,
        emo_vector: list[float] | None = None,
        instruction: str | None = None,
    ) -> bytes:
        driver = self._driver()
        if driver == "dashscope_sambert":
            return self._synthesize_dashscope_sambert(text, save_path)
        if driver == "dashscope_cosyvoice":
            return self._synthesize_dashscope_cosyvoice(text, save_path, voice_name=voice_name, instruction=instruction)

        headers = {"Content-Type": "application/json"}
        auth_header = self.custom_params.get("auth_header", "Authorization")
        if self.api_key and auth_header:
            auth_prefix = self.custom_params.get("auth_prefix", "Bearer ")
            headers[str(auth_header)] = f"{auth_prefix}{self.api_key}"
        headers.update(self.custom_params.get("headers") or {})

        request_url = self._resolve_request_url()
        payload = self._build_payload(
            text, voice_name, reference_path, emo_text, emo_vector, instruction, request_url,
        )
        query = self.custom_params.get("query") or {}

        method = str(self.custom_params.get("method") or "POST").upper()
        if method == "GET":
            resp = requests.get(request_url, params={**query, **payload}, headers=headers, timeout=180)
        else:
            resp = requests.post(request_url, json=payload, params=query, headers=headers, timeout=180)
        if resp.status_code >= 400:
            raise RuntimeError(f"云端 TTS 返回错误({resp.status_code}): {resp.text[:500]}")

        audio_bytes = self._extract_audio(resp, save_path)
        if len(audio_bytes) < 100:
            raise RuntimeError(f"云端 TTS 返回的音频数据无效，大小: {len(audio_bytes)} 字节")
        return audio_bytes

    def _build_payload(
        self,
        text: str,
        voice_name: str | None,
        reference_path: str | None,
        emo_text: str | None,
        emo_vector: list[float] | None,
        instruction: str | None,
        request_url: str,
    ) -> dict[str, Any]:
        custom_voice = self.custom_params.get("voice")
        voice_value = voice_name or custom_voice or ""
        context = {
            "text": text,
            "input": text,
            "model": self.model or "",
            "voice": voice_value,
            "reference_path": reference_path or "",
            "emotion": emo_text or "",
            "instruction": (instruction or "").strip(),
        }
        if "payload" in self.custom_params or "body" in self.custom_params:
            template = self.custom_params.get("payload") or self.custom_params.get("body") or {}
            return self._render_template(template, context)

        if self._is_dashscope_multimodal_url(request_url):
            input_payload: dict[str, Any] = {
                "text": text,
                "voice": voice_value or "Cherry",
            }
            language_type = self.custom_params.get("language_type")
            if language_type:
                input_payload["language_type"] = language_type
            if instruction and self.custom_params.get("supports_instruction", False):
                input_payload["instruction"] = instruction.strip()

            payload: dict[str, Any] = {
                "model": self.model,
                "input": input_payload,
            }
            parameters = self.custom_params.get("parameters")
            if isinstance(parameters, dict):
                payload["parameters"] = parameters
            payload.update(self.custom_params.get("extra_payload") or {})
            return {k: v for k, v in payload.items() if v is not None}

        payload: dict[str, Any] = {
            "model": self.model,
            "input": text,
        }
        if self._looks_like_openai_speech_url(request_url):
            payload["voice"] = voice_value or "alloy"
            payload["response_format"] = self.custom_params.get("format") or "wav"
        else:
            payload["text"] = text
            if voice_value:
                payload["voice"] = voice_value
        if reference_path:
            payload["reference_audio"] = reference_path
        if emo_vector is not None:
            payload["emotion_vector"] = emo_vector
        elif emo_text:
            payload["emotion"] = emo_text
        payload.update(self.custom_params.get("extra_payload") or {})
        instruction_field = self._instruction_field()
        if instruction and instruction_field:
            self._set_nested(payload, instruction_field, instruction.strip())
        return {k: v for k, v in payload.items() if v is not None}

    def _instruction_field(self) -> str | None:
        """Return the provider-specific instruction path for non-CosyVoice HTTP adapters."""
        configured = self.custom_params.get("instruction_field")
        if configured is False or self.custom_params.get("supports_instruction") is False:
            return None
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        model = (self.model or "").lower()
        if "qwen" in model and "instruct" in model:
            return "input.instruction"
        if model.startswith("gpt-4o") and "tts" in model:
            return "instructions"
        return None

    @staticmethod
    def _set_nested(payload: dict[str, Any], path: str, value: Any) -> None:
        target = payload
        parts = [part for part in str(path).split(".") if part]
        if not parts:
            return
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                child = {}
                target[part] = child
            target = child
        target[parts[-1]] = value

    def _extract_audio(self, resp: requests.Response, save_path: str) -> bytes:
        content_type = (resp.headers.get("content-type") or "").lower()
        if content_type.startswith("audio/") or content_type == "application/octet-stream":
            audio_bytes = resp.content
            self._write_audio(save_path, audio_bytes)
            return audio_bytes

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError("云端 TTS 未返回音频或 JSON") from exc

        code_path = self.custom_params.get("code_path") or "code"
        code_value = self._first_value(data, [code_path]) if code_path else None
        success_codes = self.custom_params.get("success_codes") or [None, "", 0, 200, "0", "200"]
        if isinstance(data, dict) and code_value not in success_codes:
            message_path = self.custom_params.get("message_path") or "message"
            message = self._first_value(data, [message_path]) or data
            raise RuntimeError(f"云端 TTS 业务错误: {message}")

        audio_value = self._first_value(data, self._response_paths("audio_base64_path", [
            "audio_base64",
            "audio",
            "data.audio_base64",
            "data.audio",
            "output.audio.data",
        ]))
        if isinstance(audio_value, str) and audio_value:
            if audio_value.startswith("data:"):
                audio_value = audio_value.split(",", 1)[-1]
            audio_bytes = base64.b64decode(audio_value)
            self._write_audio(save_path, audio_bytes)
            return audio_bytes

        url_value = self._first_value(data, self._response_paths("audio_url_path", [
            "audio_url",
            "url",
            "data.audio_url",
            "data.url",
            "output.audio.url",
        ]))
        if isinstance(url_value, str) and url_value:
            audio_resp = requests.get(url_value, timeout=120)
            audio_resp.raise_for_status()
            self._write_audio(save_path, audio_resp.content)
            return audio_resp.content

        path_value = self._first_value(data, self._response_paths("audio_path_path", [
            "audio_path",
            "path",
            "data.audio_path",
            "data.path",
        ]))
        if isinstance(path_value, str) and path_value and os.path.exists(path_value):
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            shutil.copy2(path_value, save_path)
            with open(save_path, "rb") as f:
                return f.read()

        raise RuntimeError(f"无法从云端 TTS 响应中解析音频: {data}")

    def _write_audio(self, save_path: str, audio_bytes: bytes) -> None:
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(audio_bytes)

    def _first_value(self, data: Any, paths: list[str]) -> Any:
        for path in paths:
            value = data
            for part in path.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    value = None
                    break
            if value:
                return value
        return None

    def _response_paths(self, key: str, defaults: list[str]) -> list[str]:
        configured = self.custom_params.get(key)
        if not configured:
            return defaults
        if isinstance(configured, str):
            return [configured, *defaults]
        if isinstance(configured, list):
            return [str(item) for item in configured if item] + defaults
        return defaults

    def _parse_params(self, custom_params: str | dict[str, Any] | None) -> dict[str, Any]:
        if not custom_params:
            return {}
        if isinstance(custom_params, dict):
            return custom_params
        try:
            data = json.loads(custom_params)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError as exc:
            raise ValueError("TTS 自定义参数必须是合法 JSON") from exc

    def _resolve_request_url(self) -> str:
        endpoint = self.custom_params.get("endpoint")
        if isinstance(endpoint, str) and endpoint.strip():
            return endpoint.strip()

        base = self.api_base_url.rstrip("/")
        if base.endswith("/compatible-mode/v1"):
            if self._is_dashscope_multimodal_model():
                return base[: -len("/compatible-mode/v1")] + "/api/v1/services/aigc/multimodal-generation/generation"
            return base + "/audio/speech"

        if base.endswith("/api/v1") and self._is_dashscope_multimodal_model():
            return base + "/services/aigc/multimodal-generation/generation"

        return base

    def _driver(self) -> str:
        driver = str(self.custom_params.get("driver") or self.custom_params.get("adapter") or "auto").lower()
        aliases = {
            "custom_http": "http",
            "openai": "http",
            "openai_speech": "http",
            "dashscope-cosyvoice": "dashscope_cosyvoice",
            "cosyvoice": "dashscope_cosyvoice",
            "dashscope-sambert": "dashscope_sambert",
            "sambert": "dashscope_sambert",
        }
        driver = aliases.get(driver, driver)
        if driver != "auto":
            return driver
        if self._is_dashscope_sambert():
            return "dashscope_sambert"
        if self._is_dashscope_cosyvoice():
            return "dashscope_cosyvoice"
        return "http"

    def _is_dashscope_sambert(self) -> bool:
        return (self.model or "").lower().startswith("sambert-")

    def _is_dashscope_cosyvoice(self) -> bool:
        return (self.model or "").lower().startswith("cosyvoice")

    def _is_dashscope_multimodal_model(self) -> bool:
        model = (self.model or "").lower()
        return model.startswith("qwen") or model.startswith("cosyvoice")

    def _is_dashscope_multimodal_url(self, request_url: str) -> bool:
        return "/services/aigc/multimodal-generation/generation" in request_url

    def _looks_like_openai_speech_url(self, request_url: str) -> bool:
        return request_url.rstrip("/").endswith("/audio/speech")

    def _dashscope_websocket_url(self) -> str:
        parsed = urlparse(self.api_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, "/api-ws/v1/inference", "", "", ""))

    def _dashscope_cosyvoice_url(self) -> str:
        endpoint = self.custom_params.get("websocket_url") or self.custom_params.get("url")
        if isinstance(endpoint, str) and endpoint.strip():
            return endpoint.strip()
        return self._dashscope_websocket_url()

    def _cosyvoice_format(self):
        from dashscope.audio.tts_v2 import AudioFormat

        value = str(self.custom_params.get("format") or "mp3").lower()
        aliases = {
            "mp3": "MP3_22050HZ_MONO_256KBPS",
            "wav": "WAV_22050HZ_MONO_16BIT",
            "pcm": "PCM_22050HZ_MONO_16BIT",
        }
        member_name = aliases.get(value, value.upper())
        return getattr(AudioFormat, member_name, AudioFormat.DEFAULT)

    def _synthesize_dashscope_cosyvoice(
        self, text: str, save_path: str, voice_name: str | None = None, instruction: str | None = None,
    ) -> bytes:
        try:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizer
        except Exception as exc:
            raise RuntimeError("CosyVoice 需要 dashscope 依赖，请先安装 requirements.txt 中的 dashscope") from exc

        if self.api_key:
            dashscope.api_key = self.api_key
        dashscope.base_websocket_api_url = self._dashscope_cosyvoice_url()

        voice = voice_name or self.custom_params.get("voice") or "longxiaochun"
        kwargs: dict[str, Any] = {
            "model": self.model,
            "voice": voice,
            "format": self._cosyvoice_format(),
            "url": self._dashscope_cosyvoice_url(),
        }

        option_map = {
            "volume": "volume",
            "speech_rate": "speech_rate",
            "pitch_rate": "pitch_rate",
            "seed": "seed",
            "synthesis_type": "synthesis_type",
            "instruction": "instruction",
            "language_hints": "language_hints",
            "workspace": "workspace",
        }
        for src, dst in option_map.items():
            if src in self.custom_params:
                kwargs[dst] = self.custom_params[src]
        if instruction and instruction.strip():
            prompt = instruction.strip()
            self._apply_prosody_controls(kwargs, prompt)
            prepared = self._prepare_cosyvoice_instruction(prompt)
            if prepared:
                kwargs["instruction"] = prepared
        if isinstance(self.custom_params.get("additional_params"), dict):
            kwargs["additional_params"] = self.custom_params["additional_params"]

        synthesizer = SpeechSynthesizer(**kwargs)
        audio_bytes = synthesizer.call(text)
        if not audio_bytes:
            request_id = getattr(synthesizer, "get_last_request_id", lambda: "")()
            raise RuntimeError(f"CosyVoice TTS 未返回音频，request_id={request_id}")

        self._write_audio(save_path, audio_bytes)
        return audio_bytes

    def _cosyvoice_instruction_mode(self) -> str:
        """Resolve native/structured/mapped instruction behavior from model capabilities."""
        configured = str(self.custom_params.get("instruction_mode") or "auto").strip().lower()
        if configured in {"native", "structured", "mapped", "none"}:
            return configured
        if self.custom_params.get("supports_instruction") is False:
            return "mapped"
        model = (self.model or "").lower()
        if model.startswith(("cosyvoice-v3.5-plus", "cosyvoice-v3.5-flash")):
            return "native"
        if model.startswith(("cosyvoice-v3-flash", "cosyvoice-v3-plus")):
            # DashScope system voices accept a strict Chinese instruction grammar.
            return "structured"
        if model.startswith(("cosyvoice-v1", "cosyvoice-v2")):
            return "mapped"
        return "native" if self.custom_params.get("supports_instruction") is True else "none"

    def _prepare_cosyvoice_instruction(self, prompt: str) -> str | None:
        mode = self._cosyvoice_instruction_mode()
        if mode in {"none", "mapped"}:
            return None
        if mode == "native":
            return prompt[:100]

        emotion_aliases = (
            (("恐惧", "害怕", "惊恐"), "fearful"),
            (("愤怒", "生气", "暴躁", "恼火"), "angry"),
            (("悲伤", "伤心", "低落", "难过"), "sad"),
            (("惊讶", "震惊", "意外"), "surprised"),
            (("开心", "高兴", "欢快", "活泼", "兴奋"), "happy"),
            (("厌恶", "嫌弃", "恶心"), "disgusted"),
        )
        emotion = "neutral"
        for words, value in emotion_aliases:
            if any(word in prompt for word in words):
                emotion = value
                break
        return f"你说话的情感是{emotion}。"

    @staticmethod
    def _apply_prosody_controls(kwargs: dict[str, Any], prompt: str) -> None:
        """Keep common speed/pitch/volume controls across Base and Instruct models."""
        if any(word in prompt for word in ("慢", "克制", "舒缓", "停顿")):
            kwargs["speech_rate"] = min(int(kwargs.get("speech_rate", 0)), -20)
        if any(word in prompt for word in ("快", "急促", "紧张")):
            kwargs["speech_rate"] = max(int(kwargs.get("speech_rate", 0)), 20)
        if any(word in prompt for word in ("压低", "低沉", "低音")):
            kwargs["pitch_rate"] = min(int(kwargs.get("pitch_rate", 0)), -10)
        if any(word in prompt for word in ("高昂", "明亮", "高音")):
            kwargs["pitch_rate"] = max(int(kwargs.get("pitch_rate", 0)), 10)
        if any(word in prompt for word in ("轻声", "小声", "耳语")):
            kwargs["volume"] = min(int(kwargs.get("volume", 50)), 35)

    def _synthesize_dashscope_sambert(self, text: str, save_path: str) -> bytes:
        try:
            import dashscope
            from dashscope.audio.tts import SpeechSynthesizer
        except Exception as exc:
            raise RuntimeError("Sambert 需要 dashscope 依赖，请先安装 requirements.txt 中的 dashscope") from exc

        if self.api_key:
            dashscope.api_key = self.api_key
        dashscope.base_websocket_api_url = self._dashscope_websocket_url()

        pass_through_keys = {
            "format",
            "sample_rate",
            "volume",
            "rate",
            "pitch",
            "word_timestamp_enabled",
            "phoneme_timestamp_enabled",
            "workspace",
        }
        kwargs = {key: self.custom_params[key] for key in pass_through_keys if key in self.custom_params}
        kwargs.setdefault("format", "wav")

        result = SpeechSynthesizer.call(model=self.model, text=text, **kwargs)
        audio_bytes = result.get_audio_data()
        if not audio_bytes:
            get_response = getattr(result, "get_response", None)
            detail = get_response() if callable(get_response) else result
            raise RuntimeError(f"Sambert TTS 未返回音频: {detail}")

        self._write_audio(save_path, audio_bytes)
        return audio_bytes

    def _render_template(self, value: Any, context: dict[str, str]) -> Any:
        if isinstance(value, str):
            for key, replacement in context.items():
                value = value.replace("{{" + key + "}}", replacement)
            return value
        if isinstance(value, list):
            return [self._render_template(item, context) for item in value]
        if isinstance(value, dict):
            return {key: self._render_template(item, context) for key, item in value.items()}
        return value
if __name__ == "__main__":
    # 示例使用
    engine = TTSEngine("https://eihh5fmon4-8200.cnb.run/")

    # 1. 上传音频
    upload_res = engine.upload_audio("C:\\Users\\lxc18\\Music\\多情绪\\吴泽\\解说\\中等.wav",full_path="C:\\Users\\lxc18\\Music\\多情绪\\吴泽\\解说\\中等.wav")
    # print("上传结果:", upload_res)

    # 2. 检查音频是否存在
    exists = engine.check_audio_exists("C:\\Users\\lxc18\\Music\\多情绪\\吴泽\\解说\\中等.wav")
    logging.info("音频存在: %s", exists)

    # 3. 获取模型列表
    models = engine.get_models()
    logging.info("模型信息: %s", models)

    # 4. 合成语音
    if exists:
        audio = engine.synthesize("萧炎，斗之力，三段！级别：低级！", "C:\\Users\\lxc18\\Music\\多情绪\\吴泽\\解说\\中等.wav",emo_text="愤怒", save_path="output.wav")
        logging.info("语音已保存到 output.wav, 大小 %s 字节", len(audio))

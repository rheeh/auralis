"""Create a model-bound voice from a user-authorized public recording."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from sqlalchemy import select

from app.core.config import getConfigPath
from app.models.po import TTSProviderPO, VoicePO

CLONE_MODELS = {'qwen-audio-3.0-tts-plus', 'qwen-audio-3.0-tts-flash', 'cosyvoice-v1'}


class VoiceCloneService:
    def __init__(self, db):
        self.db = db

    def create(self, dto):
        provider = self.db.get(TTSProviderPO, dto.tts_provider_id)
        if not provider or provider.status == 0 or provider.model not in CLONE_MODELS:
            raise ValueError('请选择已启用的 Qwen-Audio 3.0 Plus / Flash 或 CosyVoice v1 配置')
        if not dto.rights_confirmed:
            raise ValueError('需要确认录音来源允许声音复刻')
        source = urlparse(dto.audio_url)
        if source.scheme != 'https' or not source.hostname or source.username or source.password:
            raise ValueError('请提供无需登录、可公开访问的 HTTPS 音频链接')
        base = urlparse(provider.api_base_url)
        host = base.hostname or ''
        if base.scheme != 'https' or not (host == 'dashscope.aliyuncs.com' or host.endswith('.cn-beijing.maas.aliyuncs.com')):
            raise ValueError('声音复刻仅使用已配置的阿里云北京域名')
        existing = self.db.scalar(select(VoicePO).where(VoicePO.tts_provider_id == provider.id, VoicePO.name == dto.name))
        if existing:
            raise ValueError('该模型下已有同名音色，请直接使用或换一个名称')
        # A durable receipt avoids another cloud creation if local persistence fails.
        key = hashlib.sha256(f'{provider.id}|{provider.model}|{dto.audio_url}|{dto.language}'.encode()).hexdigest()
        directory = Path(getConfigPath()) / 'voice_clones'
        directory.mkdir(parents=True, exist_ok=True)
        receipt = directory / f'{key}.json'
        if receipt.exists():
            record = json.loads(receipt.read_text())
        else:
            payload = {'model': 'voice-enrollment', 'input': {'action': 'create_voice', 'target_model': provider.model, 'prefix': f'av{key[:8]}', 'url': dto.audio_url}}
            if provider.model.startswith('qwen-audio'):
                payload['input']['language_hints'] = [dto.language]
            response = requests.post(f'https://{host}/api/v1/services/audio/tts/customization', headers={'Authorization': f'Bearer {provider.api_key}', 'Content-Type': 'application/json'}, json=payload, timeout=90)
            try:
                data = response.json()
            except ValueError:
                raise ValueError(f'阿里云复刻接口返回异常（HTTP {response.status_code}）')
            if response.status_code != 200 or not data.get('output', {}).get('voice_id'):
                code = str(data.get('code') or response.status_code)
                raise ValueError(f'阿里云音色创建失败（{code}），请检查音频链接、长度与账户状态；未自动重试')
            voice_id = data['output']['voice_id']
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', voice_id) or not voice_id.startswith(provider.model + '-'):
                raise ValueError('阿里云返回的音色与当前模型不匹配')
            record = {'voice_id': voice_id, 'model': provider.model, 'source_url': dto.audio_url, 'license_note': dto.license_note, 'request_id': data.get('request_id')}
            receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        marker = 'qwen_voice' if provider.model.startswith('qwen') else 'cosyvoice_voice'
        voice = VoicePO(name=dto.name, tts_provider_id=provider.id, description=f'复刻音色,授权参考,{dto.language},{marker}:{record["voice_id"]}', is_multi_emotion=0)
        self.db.add(voice)
        self.db.commit()
        self.db.refresh(voice)
        return voice

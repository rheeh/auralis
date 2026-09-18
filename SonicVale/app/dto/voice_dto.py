from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, AliasChoices


class VoiceCreateDTO(BaseModel):
    name: str
    tts_provider_id: int
    id: Optional[int] = None
    provider_voice_id: Optional[str] = None
    reference_path: Optional[str] = None
    description: Optional[str] = None
    is_multi_emotion: Optional[int] = 0


class VoiceResponseDTO(BaseModel):
    name: str
    tts_provider_id: int
    id: Optional[int] = None
    provider_voice_id: Optional[str] = None
    reference_path : Optional[str] = None
    description : Optional[str] = None
    is_multi_emotion : Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VoiceExportDTO(BaseModel):
    """导出音色库请求DTO"""
    tts_provider_id: int
    export_path: str
    ids: Optional[List[int]] = Field(default=None, validation_alias=AliasChoices("ids", "voice_ids"))


class VoiceImportDTO(BaseModel):
    """导入音色库请求DTO"""
    tts_provider_id: int
    zip_path: str
    target_dir: str


class VoiceImportResultDTO(BaseModel):
    """导入音色库结果DTO"""
    success_count: int
    skipped_count: int
    skipped_names: List[str]


class VoicePresetSeedDTO(BaseModel):
    """生成内置常见音色请求DTO"""
    tts_provider_id: int
    target_dir: Optional[str] = None
    overwrite: Optional[bool] = False


class VoicePresetSeedResultDTO(BaseModel):
    """生成内置常见音色结果DTO"""
    success_count: int
    skipped_count: int
    failed_count: int
    skipped_names: List[str]
    failed_names: List[str]
    target_dir: str


class VoiceAudioProcessDTO(BaseModel):
    """音色参考音频处理DTO"""
    audio_path: str
    speed: Optional[float] = 1.0
    volume: Optional[float] = 1.0
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    silence_sec: Optional[float] = 0.0
    current_ms: Optional[int] = None


class VoiceCopyDTO(BaseModel):
    """复制音色请求DTO"""
    source_voice_id: int
    new_name: str
    target_dir: Optional[str] = None  # 为空则使用原音色同目录


class VoiceCloneDTO(BaseModel):
    tts_provider_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    audio_url: str = Field(min_length=10, max_length=2048)
    language: str = Field(default='zh', pattern='^(zh|en|de|fr|ja|ko|es|it|ru|pt)$')
    license_note: str = Field(min_length=3, max_length=1000)
    rights_confirmed: bool = False

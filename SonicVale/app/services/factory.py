"""Application service construction, shared by HTTP handlers and background workers."""
from app.repositories.line_repository import LineRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.voice_repository import VoiceRepository
from app.repositories.emotion_repository import EmotionRepository
from app.repositories.strength_repository import StrengthRepository
from app.repositories.multi_emotion_voice_repository import MultiEmotionVoiceRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.services.line_service import LineService
from app.services.role_service import RoleService
from app.services.project_service import ProjectService
from app.services.voice_service import VoiceService
from app.services.emotion_service import EmotionService
from app.services.strength_service import StrengthService
from app.services.multi_emotion_voice_service import MultiEmotionVoiceService


def get_line_service(db):
    return LineService(LineRepository(db), RoleRepository(db), TTSProviderRepository(db), LLMProviderRepository(db))


def get_role_service(db):
    return RoleService(RoleRepository(db))


def get_project_service(db):
    return ProjectService(ProjectRepository(db))


def get_voice_service(db):
    return VoiceService(VoiceRepository(db), MultiEmotionVoiceRepository(db))


def get_emotion_service(db):
    return EmotionService(EmotionRepository(db))


def get_strength_service(db):
    return StrengthService(StrengthRepository(db))


def get_multi_emotion_voice_service(db):
    return MultiEmotionVoiceService(MultiEmotionVoiceRepository(db))

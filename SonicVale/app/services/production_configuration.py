"""Resolve the actual provider binding without exposing provider credentials."""
from sqlalchemy import select
from app.models.po import ChapterPO, LinePO, ProjectPO, RolePO, TTSProviderPO, VoicePO
from app.core.tts_engine import ConfigurableCloudTTSEngine
from app.core.tts_capabilities import cosyvoice_instruction_mode, http_instruction_field
from app.services.line_service import LineService


def effective_provider_id(project, voice):
    return getattr(voice, 'tts_provider_id', None) or getattr(project, 'tts_provider_id', None)


def instruction_mode(provider, voice_name):
    if provider is None:
        return 'none'
    kind = (provider.provider_type or '').lower()
    model = (provider.model or '').lower()
    if kind == 'edge':
        return 'mapped'
    params = ConfigurableCloudTTSEngine._parse_params(provider.custom_params)
    if model.startswith('cosyvoice-'):
        return cosyvoice_instruction_mode(model, params, voice_name)
    return 'native' if http_instruction_field(model, params) else 'none'


def chapter_configuration(db, project_id, chapter_id):
    project, chapter = db.get(ProjectPO, project_id), db.get(ChapterPO, chapter_id)
    if not project or not chapter or chapter.project_id != project_id:
        raise ValueError('章节不存在或不属于当前项目')
    roles = {role.id: role for role in db.execute(select(RolePO).where(RolePO.project_id == project_id)).scalars()}
    result = []
    for line in db.execute(select(LinePO).where(LinePO.chapter_id == chapter_id).order_by(LinePO.line_order)).scalars():
        if line.should_speak == 0 or line.track in {'sfx', 'bgm'}:
            continue
        role = roles.get(line.role_id)
        voice = db.get(VoicePO, role.default_voice_id) if role and role.default_voice_id else None
        provider_id = effective_provider_id(project, voice)
        provider = db.get(TTSProviderPO, provider_id) if provider_id else None
        voice_name = LineService.resolve_cosyvoice_voice(voice) or getattr(voice, 'name', '')
        result.append({
            'line_id': line.id, 'role_id': line.role_id, 'voice_id': getattr(voice, 'id', None),
            'voice_name': getattr(voice, 'name', None), 'provider_id': provider_id,
            'provider_name': getattr(provider, 'name', None), 'model': getattr(provider, 'model', None),
            'binding_source': 'voice' if voice and voice.tts_provider_id else 'project',
            'enabled': bool(voice and provider and provider.status != 0),
            'instruction_mode': instruction_mode(provider, voice_name),
            'needs_generation': line.status != 'done' or line.is_done != 1,
        })
    return {'project_id': project_id, 'chapter_id': chapter_id, 'lines': result}

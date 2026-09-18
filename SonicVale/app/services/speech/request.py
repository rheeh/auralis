"""Freeze resolved generation dependencies before enqueueing; credentials stay in memory."""
import copy
import hashlib
import json
from pathlib import Path
from app.core.config import getConfigPath
from app.core.tts_engine import ConfigurableCloudTTSEngine
from app.core.tts_guidance import edge_prosody, emotion_text_to_vector
from app.models.po import LinePO, RolePO, VoicePO, TTSProviderPO, ProjectPO
from app.services.speech_direction_service import SpeechDirectionService
from app.services.tts_trace_service import redact


def prepare_request(db, project_id, line_id):
    from app.services.speech import routing as speech_routing
    prepared = SpeechDirectionService(db).prepare(project_id,line_id)
    line = db.get(LinePO,line_id)
    role = db.get(RolePO,line.role_id) if line.role_id else None
    voice = db.get(VoicePO,prepared['voice_id']) if prepared['voice_id'] else None
    provider = db.get(TTSProviderPO,prepared['provider_id'])
    request = {'prepared':prepared,'provider':{key:getattr(provider,key,None) for key in
               ('id','provider_type','api_base_url','api_key','model','custom_params')},
               'reference_path':voice.reference_path if voice else None,
               'edge_voice':speech_routing.resolve_edge_voice(role,voice),
               'voice_name':prepared['voice_name'],
               'prosody':edge_prosody(prepared['emotion'],prepared['effective_strength'],prepared['delivery_note']),
               'emo_vector':emotion_text_to_vector(prepared['emotion'],prepared['effective_strength'])}
    request['provider']['custom_params'] = {**ConfigurableCloudTTSEngine._parse_params(provider.custom_params), **prepared['provider_overrides']}
    if request['reference_path'] and Path(request['reference_path']).is_file():
        with open(request['reference_path'],'rb') as reference:
            request['reference_sha256']=hashlib.file_digest(reference,'sha256').hexdigest()
    # Fingerprints never depend on credentials, random execution IDs or clocks.
    snapshot = redact(request,(provider.api_key or '',),bounded=False)
    fingerprint = hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return copy.deepcopy(request),snapshot,fingerprint


def output_path(db, project_id, chapter_id, line_id, token):
    project=db.get(ProjectPO,project_id)
    root=Path(project.project_root_path or getConfigPath()).expanduser().resolve()
    directory=root/str(project_id)/str(chapter_id)/'audio'/'attempts'
    directory.mkdir(parents=True,exist_ok=True)
    return str(directory/f'{line_id}-{token}.wav')

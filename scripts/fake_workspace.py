#!/usr/bin/env python3
"""Disposable browser acceptance backend. Fixed fake LLM/TTS, never real providers.

Run with SonicVale/.venv/bin/python scripts/fake_workspace.py. The process owns
its TemporaryDirectory and removes it on shutdown; no production config loaded.
"""
import os
from pathlib import Path
import sys
import tempfile
import wave

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'SonicVale'))
with tempfile.TemporaryDirectory(prefix='auralis-browser-') as directory:
    os.environ['AURALIS_CONFIG_DIR']=directory
    os.environ['AURALIS_TEST_OFFLINE']='1'
    os.environ['AURALIS_ALLOWED_ORIGINS']='http://127.0.0.1:5175'
    sys.path.insert(0,str(root/'scripts/offline'))
    import sitecustomize
    from app.main import app
    from app.db.database import SessionLocal
    from app.models.po import ProjectPO,TTSProviderPO,VoicePO
    from app.services.source_parser_service import SourceParserService
    from app.services.role_draft_service import RoleDraftService
    from app.services.script_draft_service import ScriptDraftService
    from app.services.script_review_service import ScriptReviewService
    import app.core.tts_runtime as runtime
    script={'title':'固定测试章','logline':'两人听雨','characters':[{'name':'小林'},{'name':'小周'}],
        'scenes':[{'title':'窗边','location':'屋内','mood':'平静','lines':[
            {'type':'dialogue','track':'voice','shouldSpeak':True,'speaker':'小林','text':'雨停了吗？'},
            {'type':'dialogue','track':'voice','shouldSpeak':True,'speaker':'小周','text':'还没有，再等一会。'}]}]}
    SourceParserService.parse=lambda *args,**kwargs:{'title':'固定测试章','characters':script['characters'],'scenePlan':[{'title':'窗边'}]}
    voices=[]
    RoleDraftService.generate=lambda *args,**kwargs:[{'draft_id':f'r{i}','name':name,'selected':True,'default_voice_id':voices[i],
        'identity':'邻居','personality':['平静'],'relationships':[],'speech_style':'短句','voice_type':'测试声'} for i,name in enumerate(['小林','小周'])]
    ScriptDraftService.generate=lambda *args,**kwargs:script
    ScriptReviewService.review=lambda *args,**kwargs:{'passed':True,'score':90,'summary':'固定 fake 审查','strengths':[],'issues':[]}
    def synthesize(request,observer=None):
        if observer:observer('request',{'driver':'fake','text':request['prepared']['tts_text']})
        with wave.open(request['output_path'],'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0\0'*8000)
        data=Path(request['output_path']).read_bytes()
        if observer:observer('response',{'audio_bytes':len(data)})
        return data
    runtime.execute_prepared=synthesize
    @app.on_event('startup')
    def fixture():
        with SessionLocal() as db:
            provider=TTSProviderPO(name='离线测试配音',provider_type='edge',api_base_url='http://unused.invalid',status=1)
            db.add(provider);db.flush()
            for name in ['测试声一','测试声二']:
                voice=VoicePO(name=name,tts_provider_id=provider.id,provider_voice_id='zh-CN-XiaoxiaoNeural')
                db.add(voice);db.flush();voices.append(voice.id)
            project=ProjectPO(name='离线验收工程',project_root_path=directory,tts_provider_id=provider.id)
            db.add(project);db.commit()
            print(f'FAKE_PROJECT_ID={project.id}',flush=True)
    @app.get('/test-fixture')
    def fixture_identity():
        return {'fake_models':True,'temporary_storage':True}
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18200,log_level='warning')

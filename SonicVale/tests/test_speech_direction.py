import asyncio
import io
import json
import os
import tempfile
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.core.tts_engine import ConfigurableCloudTTSEngine, TTSEngine
from app.core.tts_runtime import tts_worker
from app.db.database import Base, get_db
from app.db.migrations import apply_schema_migrations
from app.dto.line_dto import LineCreateDTO
from app.dto.speech_dto import ProjectSpeechSettings
from app.models.po import (AdaptationRunPO, ChapterPO, EmotionPO, LinePO, ProjectPO,
    ProjectSpeechProfilePO, RolePO, StrengthPO, TTSGenerationPO, TTSProviderPO, VoicePO)
from app.routers.speech_router import router
from app.services.speech_direction_service import SpeechDirectionService, clean_spoken_text
from app.services.tts_trace_service import TTSTraceService, TTSRequestRecorder, redact


class SpeechDirectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{self.tmp.name}/test.db', connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.provider = TTSProviderPO(name='test', model='qwen-audio-3.0-tts-plus', provider_type='cloud',
            api_base_url='https://dashscope.aliyuncs.com', api_key='test-private-key', custom_params='{}')
        self.db.add(self.provider); self.db.flush()
        self.project = ProjectPO(name='测试作品', description='多年失散的兄妹在旧站台重逢。', tts_provider_id=self.provider.id)
        self.db.add(self.project); self.db.flush()
        self.chapter = ChapterPO(project_id=self.project.id, title='雨夜')
        self.voice = VoicePO(tts_provider_id=self.provider.id, name='longanlingxin', description='qwen_voice:longanlingxin')
        self.db.add_all([self.chapter, self.voice]); self.db.flush()
        self.role = RolePO(project_id=self.project.id, name='林默', default_voice_id=self.voice.id, tts_route='cloud')
        self.other = RolePO(project_id=self.project.id, name='小安', default_voice_id=self.voice.id, tts_route='cloud')
        self.emotion = EmotionPO(name='害怕')
        self.strengths = [StrengthPO(name=name) for name in ('微弱', '稍弱', '中等', '较强', '强烈')]
        self.db.add_all([self.role, self.other, self.emotion, *self.strengths]); self.db.flush()
        self.lines = []
        for i, (speaker, strength, words) in enumerate([
            (self.role, 0, '你去过重庆吗？'), (self.other, 4, '我昨天才回来。'),
            (self.role, 4, '重庆的 AI lab 还在吗？'), (self.role, 0, '没什么，我随便问问。'),
        ], 1):
            line = LinePO(chapter_id=self.chapter.id, role_id=speaker.id, line_order=i, scene_title='站台',
                text_content=words, strength_id=self.strengths[strength].id, emotion_id=self.emotion.id,
                track='voice', line_type='dialogue', should_speak=1, voice_profile='清晰低声线', production_note='',
                audio_path=f'{self.tmp.name}/line-{i}.wav')
            self.db.add(line); self.lines.append(line)
        self.db.commit()
        self.service = SpeechDirectionService(self.db)

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.tmp.cleanup()

    def save(self, **kwargs):
        return self.service.save_settings(self.project.id, ProjectSpeechSettings(**kwargs))

    def test_profile_validation_and_revision(self):
        self.assertEqual(self.service.settings(self.project.id)['revision'], 0)
        self.assertEqual(self.db.query(ProjectSpeechProfilePO).count(), 0)
        self.assertEqual(self.save(story_background='共同背景')['revision'], 1)
        self.assertEqual(self.save(story_background='第二版')['revision'], 2)
        for entries in ([{'term': '重庆'}], [{'term': '重庆', 'pronunciation': '（慢读）'}],
                        [{'term': 'a', 'spoken_as': 'b'}, {'term': 'a', 'spoken_as': 'c'}]):
            with self.assertRaises(ValidationError): ProjectSpeechSettings(pronunciation_entries=entries)

    def test_qwen_preview_uses_fluent_defaults_without_rewriting_authored_text(self):
        line = self.lines[0]
        line.text_content = '这个小袋我翻过了，大的也……没有。'
        line.voice_profile = ''
        self.db.commit()
        with patch('app.core.tts_engine.requests.post') as post:
            preview = self.service.preview(self.project.id, line.id)
        post.assert_not_called()
        body = preview['request_preview']['payload']['input']
        self.assertEqual(body['text'], line.text_content)
        self.assertIn('连贯', body['instruction'])
        self.assertNotIn('关键词', body['instruction'])
        self.assertNotIn('句尾', body['instruction'])
        self.assertNotIn('rate', body)
        self.assertEqual(line.production_note, '')

    def test_context_and_pronunciation_never_enter_spoken_text(self):
        self.save(story_background='两人并不知道对方的真实身份。', pronunciation_entries=[{'term': '重庆', 'pronunciation': 'chong2 qing4'}])
        with patch('app.core.tts_engine.requests.post') as post, patch('app.core.tts_engine.requests.get') as get:
            result = self.service.preview(self.project.id, self.lines[2].id)
        post.assert_not_called(); get.assert_not_called()
        body = result['request_preview']['payload']['input']
        self.assertEqual(body['text'], self.lines[2].text_content)
        self.assertEqual(body['hot_fix']['pronunciation'], [{'重庆': 'chong2 qing4'}])
        self.assertIn('共同表演基调', body['instruction'])
        self.assertIn('真实身份', body['instruction'])
        self.assertIn(self.lines[1].text_content, body['instruction'])
        self.assertNotIn('微弱地害怕', body['instruction'])
        self.assertEqual(result['effective_strength'], '稍弱')
        self.assertEqual(self.lines[2].strength_id, self.strengths[4].id)
        self.assertEqual(self.provider.custom_params, '{}')

    def test_continuity_is_repeatable_and_does_not_borrow_other_speaker(self):
        first = self.service.prepare(self.project.id, self.lines[2].id)
        self.lines[1].strength_id = self.strengths[0].id; self.db.commit()
        second = self.service.prepare(self.project.id, self.lines[2].id)
        self.assertEqual(first['effective_strength'], second['effective_strength'])
        self.assertEqual(first['context']['previous_same_speaker']['line_id'], self.lines[0].id)
        self.assertEqual(self.service.prepare(self.project.id, self.lines[3].id)['effective_strength'], '微弱')
        self.lines[2].production_note = '情绪转折，终于认出对方，喊出名字。'; self.db.commit()
        self.assertEqual(self.service.prepare(self.project.id, self.lines[2].id)['effective_strength'], '强烈')
        self.assertEqual(self.service.prepare(self.project.id, self.lines[3].id)['effective_strength'], '微弱')
        self.lines[2].production_note = '不要情绪转折，不要大喊。'; self.db.commit()
        self.assertEqual(self.service.prepare(self.project.id, self.lines[2].id)['effective_strength'], '稍弱')
        self.save(continuity_enabled=False)
        self.assertEqual(self.service.prepare(self.project.id, self.lines[2].id)['effective_strength'], '强烈')

    def test_scene_boundary_clears_adjacent_context(self):
        self.lines[1].scene_title = '另一处'
        self.db.commit()
        result = self.service.prepare(self.project.id, self.lines[2].id)
        self.assertEqual(result['context']['previous_lines'], [])
        self.assertIsNone(result['context']['previous_same_speaker'])
        self.assertEqual(result['effective_strength'], '中等')

    def test_committed_analysis_fallback_and_queued_input(self):
        self.db.add(AdaptationRunPO(project_id=self.project.id, chapter_id=self.chapter.id, title='稿',
            committed_at=datetime.now(timezone.utc), parsed_json={'logline': '章节梗概', 'genre': '悬疑'}, instruction='轻松的表演'))
        self.db.commit()
        dto = LineCreateDTO(**{key: getattr(self.lines[2], key) for key in LineCreateDTO.model_fields if hasattr(self.lines[2], key)})
        dto.text_content = '排队时的台词'; dto.production_note = '确认名字，短收。'
        result = self.service.prepare(self.project.id, self.lines[2].id, dto)
        self.assertEqual(result['tts_text'], '排队时的台词')
        self.assertEqual(result['context']['background_source'], 'committed_analysis')
        self.assertIn('章节梗概', result['instruction'])
        self.assertIn('轻松的表演', result['instruction'])
        self.assertEqual(self.lines[2].text_content, '重庆的 AI lab 还在吗？')

    def test_fallback_longest_replacement_once_and_unsupported_pinyin_warning(self):
        self.provider.provider_type = 'edge'; self.voice.description = ''; self.voice.name = 'zh-CN-XiaoxiaoNeural'
        self.lines[2].text_content = 'ABC A 重庆'; self.db.commit()
        self.save(pronunciation_entries=[{'term': 'ABC', 'spoken_as': 'A B C'}, {'term': 'A', 'spoken_as': '诶'}, {'term': '重庆', 'pronunciation': 'chong2 qing4'}])
        result = self.service.preview(self.project.id, self.lines[2].id)
        self.assertEqual(result['tts_text'], 'A B C 诶 重庆')
        self.assertEqual(result['request_preview']['text'], result['tts_text'])
        self.assertTrue(any('重庆' in warning and '未应用' in warning for warning in result['warnings']))
        self.assertNotIn('instruction', result['request_preview'])
        self.assertEqual(clean_spoken_text('hello  world（轻声）'), 'hello world')

    def test_qwen_extra_input_keeps_text_and_project_glossary(self):
        self.provider.custom_params = json.dumps({'hot_fix': {'pronunciation': [{'别处': 'bie2 chu4'}]},
            'extra_payload': {'input': {'sample_rate': 24000, 'hot_fix': {'pronunciation': [{'重庆': 'zhong4 qing4'}]}}}})
        self.db.commit(); self.save(pronunciation_entries=[{'term': '重庆', 'pronunciation': 'chong2 qing4'}])
        body = self.service.preview(self.project.id, self.lines[2].id)['request_preview']['payload']['input']
        self.assertEqual(body['text'], self.lines[2].text_content)
        self.assertEqual(body['sample_rate'], 24000)
        self.assertIn({'重庆': 'chong2 qing4'}, body['hot_fix']['pronunciation'])
        self.assertIn({'别处': 'bie2 chu4'}, body['hot_fix']['pronunciation'])

    def test_custom_template_and_qwen3_use_supported_fields(self):
        self.provider.api_base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        self.provider.model = 'qwen3-tts-instruct-flash'; self.voice.name = 'Cherry'; self.voice.description = 'qwen_voice:Cherry'; self.db.commit()
        body = self.service.preview(self.project.id, self.lines[2].id)['request_preview']['payload']['input']
        self.assertIn('instructions', body); self.assertIs(body['optimize_instructions'], False)
        self.assertNotIn('instruction', body)
        self.provider.custom_params = json.dumps({'payload': {'text': '{{text}}', 'direction': '{{instruction}}'}}); self.db.commit()
        body = self.service.preview(self.project.id, self.lines[2].id)['request_preview']['payload']
        self.assertIn('作品背景', body['direction']); self.assertEqual(body['text'], self.lines[2].text_content)

    def test_api_roundtrip_scope_and_history_without_preview(self):
        other = ProjectPO(name='其他项目'); self.db.add(other); self.db.commit()
        app = FastAPI(); app.include_router(router)
        def dependency():
            with self.Session() as session: yield session
        app.dependency_overrides[get_db] = dependency
        with TestClient(app) as client:
            base = f'/projects/{self.project.id}'
            self.assertEqual(client.put(base+'/speech-settings', json={'story_background': 'API 保存'}).status_code, 200)
            self.assertEqual(client.get(base+'/speech-settings').json()['data']['story_background'], 'API 保存')
            self.assertEqual(client.get(f'/projects/{other.id}/lines/{self.lines[2].id}/speech-preview').status_code, 400)
            self.assertNotIn('test-private-key', client.get(base+f'/lines/{self.lines[2].id}/speech-preview').text)
            self.provider.status = 0; self.db.commit()
            self.assertEqual(client.get(base+f'/lines/{self.lines[2].id}/speech-preview').status_code, 400)
            self.assertEqual(client.get(base+'/tts-generations').status_code, 200)

    def test_trace_records_exact_http_error_and_redacts_sensitive_response(self):
        trace = TTSTraceService(self.db)
        generation_id = trace.begin(self.project.id, self.chapter.id, self.lines[2].id)
        recorder = TTSRequestRecorder(self.engine, generation_id, ('test-private-key',))
        engine = ConfigurableCloudTTSEngine(self.provider.api_base_url, self.provider.api_key, self.provider.model, {})
        engine.observer = recorder
        response = Mock(status_code=400, headers={'content-type':'application/json'}, text='invalid test-private-key')
        response.json.return_value = {'request_id': 'request-123', 'message': response.text, 'audio': {'url':'https://user:pass@test/a.mp3?token=abc'}}
        with patch('app.core.tts_engine.requests.post', return_value=response) as post:
            with self.assertRaises(RuntimeError) as error:
                engine.synthesize('正文', None, voice_name='longanlingxin', instruction='自然交谈')
        trace.finish(generation_id, error=error.exception, secrets=('test-private-key',)); self.db.expire_all()
        row = self.db.get(TTSGenerationPO, generation_id)
        self.assertEqual(row.request_json['payload'], post.call_args.kwargs['json'])
        self.assertEqual(row.response_json['body']['request_id'], 'request-123')
        self.assertEqual(row.response_json['body']['audio']['url'], 'https://test/a.mp3')
        self.assertNotIn('test-private-key', json.dumps(TTSTraceService.serialize(row), default=str))
        self.assertEqual(row.status, 'failed')
        recorder('request', {'text': 'late thread request'}); self.db.expire_all()
        self.assertEqual(self.db.get(TTSGenerationPO, generation_id).status, 'failed')

    def test_trace_pagination_preserves_deleted_line_and_migration(self):
        trace = TTSTraceService(self.db)
        ids = [trace.begin(self.project.id, self.chapter.id, self.lines[2].id) for _ in range(3)]
        trace.finish(ids[-1], audio=b'audio' * 500, version_id='take-1')
        self.db.delete(self.lines[2]); self.db.commit()
        first = trace.list(self.project.id, limit=2)
        second = trace.list(self.project.id, limit=2, before=first['next_cursor'])
        self.assertEqual(len(first['items'])+len(second['items']), 3)
        self.assertEqual(len({row['id'] for row in first['items']+second['items']}), 3)
        result = first['items'][0]['result_json']
        self.assertEqual(result['bytes'], 2500); self.assertIn('sha256', result)
        with self.assertRaises(ValueError): trace.list(999, before=ids[0])
        apply_schema_migrations(self.engine); apply_schema_migrations(self.engine)
        self.assertTrue({'project_speech_profiles', 'tts_generations'} <= set(inspect(self.engine).get_table_names()))
        self.assertEqual(self.db.query(TTSGenerationPO).count(), 3)

    def test_legacy_trace_uses_transport_payload_and_retains_error_response(self):
        trace = TTSTraceService(self.db)
        generation_id = trace.begin(self.project.id, self.chapter.id, self.lines[2].id)
        engine = TTSEngine('https://test.invalid', 'test-private-key')
        engine.observer = TTSRequestRecorder(self.engine, generation_id, ('test-private-key',))
        response = Mock(status_code=422, headers={'content-type': 'application/json'}, text='bad input')
        response.json.return_value = {'request_id': 'legacy-error', 'detail': 'bad input'}
        with patch('app.core.tts_engine.requests.post', return_value=response) as post:
            with self.assertRaises(Exception): engine.synthesize('正文', 'reference.wav', emo_vector=[0.1]*8)
        self.db.expire_all()
        row = self.db.get(TTSGenerationPO, generation_id)
        self.assertEqual(row.request_json['payload'], post.call_args.kwargs['json'])
        self.assertEqual(row.response_json['body']['request_id'], 'legacy-error')

    def test_project_deletion_cleans_own_profiles_and_traces(self):
        from app.repositories.project_repository import ProjectRepository
        from app.services.project_service import ProjectService
        self.project.project_root_path = self.tmp.name
        self.db.commit(); self.save(story_background='背景')
        TTSTraceService(self.db).begin(self.project.id, self.chapter.id, self.lines[2].id)
        ProjectService(ProjectRepository(self.db)).delete_project(self.project.id)
        self.assertEqual(self.db.query(TTSGenerationPO).count(), 0)
        self.assertEqual(self.db.query(ProjectSpeechProfilePO).count(), 0)
        self.assertIsNotNone(self.db.get(TTSProviderPO, self.provider.id))

    def test_redaction_limits_and_no_audio_blob(self):
        output = redact({'api_key': 'secret', 'audio_data': 'x'*2000, 'url': 'https://test/a?Signature=abc',
            'message': 'Bearer credential sk-exampletoken', 'malformed': 'https://[broken'})
        self.assertEqual(output['audio_data'], '[audio omitted]')
        self.assertNotIn('credential', output['message']); self.assertNotIn('Signature', output['url'])
        self.assertEqual(output['malformed'], '[invalid URL omitted]')

    def test_worker_writes_success_failure_and_preparation_error_without_network(self):
        async def run_one(failure=False):
            line = self.lines[2]
            dto = LineCreateDTO(**{key: getattr(line, key) for key in LineCreateDTO.model_fields if hasattr(line, key)})
            app = FastAPI(); app.state.tts_queue = asyncio.Queue()
            with ThreadPoolExecutor(max_workers=1) as executor:
                app.state.tts_executor = executor
                data = io.BytesIO()
                with wave.open(data, 'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b'\0\0'*1600)
                audio = data.getvalue()
                response = Mock(status_code=400 if failure else 200,
                    headers={'content-type': 'application/json' if failure else 'audio/wav'},
                    content=audio, text='mock failure')
                response.json.return_value = {'request_id':'fixture-error','message':'mock failure'}
                with patch('app.core.tts_runtime.SessionLocal', self.Session), patch('app.core.tts_runtime.manager.broadcast', new=AsyncMock()), \
                     patch('app.core.tts_engine.requests.post', return_value=response) as post:
                    task = asyncio.create_task(tts_worker(app))
                    from app.services.audio_task_service import AudioTaskService
                    AudioTaskService(self.db).enqueue(app.state.tts_queue,self.project.id,self.chapter.id,line,dto)
                    await asyncio.wait_for(app.state.tts_queue.join(), timeout=10)
                    task.cancel()
                    try: await task
                    except asyncio.CancelledError: pass
                return post
        post = asyncio.run(run_one()); self.db.expire_all()
        row = self.db.scalar(select(TTSGenerationPO).order_by(TTSGenerationPO.created_at.desc()))
        self.assertEqual(row.status, 'succeeded', row.error_message)
        self.assertEqual(row.request_json['payload'], post.call_args.kwargs['json'])
        self.assertEqual(row.input_snapshot['prepared']['tts_text'], self.lines[2].text_content)
        self.assertTrue(row.audio_version_id); self.assertGreater(row.result_json['bytes'], 100)
        asyncio.run(run_one(True)); self.db.expire_all()
        row = self.db.scalar(select(TTSGenerationPO).order_by(TTSGenerationPO.created_at.desc()))
        self.assertEqual(row.status, 'failed'); self.assertEqual(row.response_json['body']['request_id'], 'fixture-error')
        self.lines[2].text_content = '（只有指令）'; self.db.commit()
        with patch('app.core.tts_engine.requests.post') as post:
            from app.services.audio_task_service import AudioTaskService
            with self.assertRaisesRegex(ValueError, '为空'):
                AudioTaskService(self.db).enqueue(asyncio.Queue(),self.project.id,self.chapter.id,self.lines[2],
                    LineCreateDTO(chapter_id=self.chapter.id))
            post.assert_not_called()

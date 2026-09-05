import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models.po import ChapterPO, ChatSessionPO, LinePO, ProjectPO, RolePO, TTSProviderPO, VoicePO
from app.services.audio_selection import selected_audio_path
from app.services.chat_session_service import ChatSessionService
from app.services.factory import get_line_service, get_role_service
from app.services.production_configuration import chapter_configuration
from app.services.timeline_service import TimelineService


class WorkspaceIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.project = ProjectPO(name='Workspace')
        self.db.add(self.project)
        self.db.flush()
        self.chapter = ChapterPO(project_id=self.project.id, title='雨夜', text_content='原文')
        self.db.add(self.chapter)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_prohibited_llm_is_rejected_before_any_network_request(self):
        from unittest.mock import Mock
        from app.core.llm_engine import LLMEngine
        engine = LLMEngine.__new__(LLMEngine)
        engine.model_name, engine.custom_params, engine.client = 'qwen-plus', {}, Mock()
        with self.assertRaisesRegex(ValueError, 'qwen-plus'):
            engine._completion('禁止调用')
        engine.client.chat.completions.create.assert_not_called()

    def test_open_existing_chapter_is_idempotent_and_does_not_generate(self):
        with patch('app.services.drama_workflow_service.DramaWorkflowService.start') as generate:
            first = ChatSessionService(self.db).open_chapter(self.project.id, self.chapter.id)
            second = ChatSessionService(self.db).open_chapter(self.project.id, self.chapter.id)
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertEqual(first['current_stage'], 'completed')
        self.assertEqual(first['source_text'], '原文')
        self.assertEqual(self.db.query(ChatSessionPO).count(), 1)
        generate.assert_not_called()
        with self.assertRaises(ValueError):
            ChatSessionService(self.db).open_chapter(self.project.id + 99, self.chapter.id)

    def test_open_preserves_pending_confirmation(self):
        session = ChatSessionPO(id='pending', project_id=self.project.id, chapter_id=self.chapter.id,
                                title='待确认', current_stage='awaiting_role_confirmation')
        self.db.add(session)
        self.db.commit()
        result = ChatSessionService(self.db).open_chapter(self.project.id, self.chapter.id)
        self.assertEqual(result['session_id'], 'pending')
        self.assertEqual(result['current_stage'], 'awaiting_role_confirmation')

    def test_configuration_matches_voice_binding_and_excludes_credentials(self):
        base = TTSProviderPO(name='项目模型', provider_type='edge', api_base_url='', model='edge', status=1)
        voice_provider = TTSProviderPO(name='保存的声音', provider_type='cloud', api_base_url='',
                                      model='qwen-audio-3.0-tts-plus', api_key='PRIVATE-KEY', status=0)
        self.db.add_all([base, voice_provider]); self.db.flush()
        self.project.tts_provider_id = base.id
        voice = VoicePO(name='角色声音', tts_provider_id=voice_provider.id, description='qwen_voice: longanlingxin')
        self.db.add(voice); self.db.flush()
        role = RolePO(project_id=self.project.id, name='林澈', default_voice_id=voice.id)
        self.db.add(role); self.db.flush()
        line = LinePO(chapter_id=self.chapter.id, role_id=role.id, text_content='别开门', status='done', is_done=1)
        self.db.add(line); self.db.commit()
        config = chapter_configuration(self.db, self.project.id, self.chapter.id)
        item = config['lines'][0]
        self.assertEqual(item['provider_id'], voice_provider.id)
        self.assertEqual(item['binding_source'], 'voice')
        self.assertEqual(item['instruction_mode'], 'native')
        self.assertFalse(item['enabled'])
        self.assertNotIn('PRIVATE-KEY', str(config))
        voice_provider.custom_params = '{"supports_instruction": false}'
        self.db.commit()
        self.assertEqual(chapter_configuration(self.db, self.project.id, self.chapter.id)['lines'][0]['instruction_mode'], 'none')

    def test_voice_and_guidance_changes_invalidate_audio_without_deleting_takes(self):
        role = RolePO(project_id=self.project.id, name='角色')
        self.db.add(role); self.db.flush()
        line = LinePO(chapter_id=self.chapter.id, role_id=role.id, text_content='原台词', status='done', is_done=1,
                      audio_versions=[{'id':'saved','audio_path':'/preserved/take.wav'}], active_audio_version_id='saved')
        self.db.add(line); self.db.commit()
        get_line_service(self.db).update_line(line.id, {'production_note':'压低声音'})
        self.db.refresh(line)
        self.assertEqual(line.status, 'pending')
        self.assertEqual(line.audio_versions[0]['id'], 'saved')
        line.status='done';line.is_done=1;self.db.commit()
        get_role_service(self.db).update_role(role.id, {'default_voice_id':123})
        self.db.refresh(line)
        self.assertEqual(line.status, 'pending')
        self.assertEqual(line.active_audio_version_id, 'saved')

    def test_playback_and_timeline_agree_when_a_processed_version_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            original = os.path.join(folder, 'original.wav')
            adopted = os.path.join(folder, 'adopted.wav')
            for path in [original, adopted]:
                with open(path, 'wb') as file: file.write(b'unchanged')
            line = SimpleNamespace(audio_path=original, audio_variants=[{'id':'missing','audio_path':'/missing.wav'}],
                                   active_audio_variant_id='missing', audio_versions=[{'id':'take','audio_path':adopted}], active_audio_version_id='take')
            self.assertEqual(selected_audio_path(line), adopted)
            self.assertEqual(TimelineService._selected_audio_path(line), adopted)
            self.assertEqual(get_line_service(self.db).resolve_audio_path(line), adopted)
            with open(original, 'rb') as file: self.assertEqual(file.read(), b'unchanged')

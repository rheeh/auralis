import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.dto.sound_library_dto import SoundRecommendationDTO
from app.models.po import ChapterPO, ChatSessionPO, LinePO, LLMProviderPO, ProjectPO
from app.services.sound_recommendation_service import SoundRecommendationService
from app.services.workflow_llm_service import WorkflowLLMError


class SoundRecommendationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.provider = LLMProviderPO(name='test', api_key='not-a-real-key', api_base_url='https://example.invalid/v1', model_list='qwen3.8-27b', custom_params='{}')
        self.db.add(self.provider)
        self.db.flush()
        project = ProjectPO(name='test', llm_provider_id=self.provider.id, llm_model='qwen3.8-27b')
        self.db.add(project)
        self.db.flush()
        self.chapter = ChapterPO(title='雨夜', project_id=project.id, text_content='备用原文')
        self.db.add(self.chapter)
        self.db.flush()
        self.line = LinePO(chapter_id=self.chapter.id, track='sfx', line_type='sfx', should_speak=0, line_order=2, text_content='门外敲击，一慢两快', sound_prompt='木门上三次敲击', audio_path='/unchanged.wav')
        self.db.add_all([self.line, LinePO(chapter_id=self.chapter.id, line_order=1, text_content='千万别开门。'), ChatSessionPO(id='s', project_id=project.id, chapter_id=self.chapter.id, source_text='小说原文：雨水敲打窗户，门外响起熟悉的节奏。')])
        self.db.commit()
        audio = Path(self.temp.name) / 'knock.wav'
        audio.write_bytes(b'untouched sound')
        self.asset = dict(id='builtin_knock', name='木门敲击', tags=['门', '敲门'], category='doors', duration_ms=2000, source_type='builtin', path=str(audio))
        self.library = Mock()
        self.library.list_assets.return_value = [self.asset]
        self.service = SoundRecommendationService(self.db, self.library, Path(self.temp.name) / 'cache')
        self.dto = SoundRecommendationDTO(chapter_id=self.chapter.id, line_id=self.line.id)
        self.choice = dict(asset_id='builtin_knock', reason='声源匹配，但需自行核对一慢两快的节奏。', fit='approximate', placement='with', volume_db=-12)
        self.llm = Mock()
        self.llm.generate_text.return_value = json.dumps(dict(summary='门外有来客', missing_sound='需要特定敲门节奏', recommendations=[self.choice]))
        self.patcher = patch('app.services.sound_recommendation_service.WorkflowLLMService.make_engine', return_value=self.llm)
        self.make_engine = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_context_real_assets_and_no_production_mutation(self):
        result = self.service.recommend(self.dto)
        prompt = json.loads(self.llm.generate_text.call_args.args[0])
        self.assertIn('小说原文', prompt['novel_excerpt'])
        self.assertEqual(prompt['target']['sound_prompt'], '木门上三次敲击')
        self.assertIn('千万别开门', prompt['nearby_lines'][0]['text'])
        self.assertNotIn('path', prompt['catalog'][0])
        self.assertNotIn('not-a-real-key', self.llm.generate_text.call_args.args[0])
        self.assertEqual(result['recommendations'][0]['asset']['id'], self.asset['id'])
        self.assertEqual(self.llm.generate_text.call_args.kwargs['retries'], 1)
        self.assertEqual(self.make_engine.call_args.args[0].llm_model, 'qwen3.8-27b')
        self.db.expire_all()
        self.assertEqual(self.db.get(LinePO, self.line.id).audio_path, '/unchanged.wav')
        self.assertEqual(Path(self.asset['path']).read_bytes(), b'untouched sound')
        self.assertEqual(self.db.query(LinePO).count(), 2)

    def test_cache_reuses_and_invalidates_on_context_or_library_change(self):
        self.assertFalse(self.service.recommend(self.dto)['cached'])
        self.assertTrue(self.service.recommend(self.dto)['cached'])
        self.assertEqual(self.llm.generate_text.call_count, 1)
        self.line.sound_prompt = '非常轻的敲门'
        self.db.commit()
        self.assertFalse(self.service.recommend(self.dto)['cached'])
        self.asset['tags'].append('轻敲')
        self.assertFalse(self.service.recommend(self.dto)['cached'])
        self.assertEqual(self.llm.generate_text.call_count, 3)
        self.assertFalse(self.service.recommend(self.dto.model_copy(update={'refresh': True}))['cached'])

    def test_reject_cross_chapter_and_unapproved_models_before_network(self):
        with self.assertRaises(ValueError):
            self.service.recommend(self.dto.model_copy(update={'chapter_id': 999}))
        with self.assertRaises(ValidationError):
            SoundRecommendationDTO(chapter_id=self.chapter.id, line_id=self.line.id, model='qwen-plus')
        with self.assertRaises(ValueError):
            self.service.recommend(self.dto.model_copy(update={'model': 'qwen-plus'}))
        with self.assertRaisesRegex(ValueError, 'kimi-k3'):
            self.service.recommend(self.dto.model_copy(update={'model': 'kimi-k3'}))
        self.make_engine.assert_not_called()

    def test_filters_invented_and_duplicate_ids(self):
        self.llm.generate_text.return_value = json.dumps(dict(summary='推荐', recommendations=[dict(self.choice, asset_id='invented'), self.choice, self.choice]))
        self.assertEqual(len(self.service.recommend(self.dto)['recommendations']), 1)
        self.llm.generate_text.return_value = json.dumps(dict(summary='推荐', recommendations=[dict(self.choice, asset_id='invented')]))
        with self.assertRaises(WorkflowLLMError):
            self.service.recommend(self.dto.model_copy(update={'refresh': True}))

    def test_quota_failure_has_no_retry_or_model_fallback(self):
        self.llm.generate_text.side_effect = RuntimeError('AllocationQuota.FreeTierOnly')
        with self.assertRaisesRegex(WorkflowLLMError, '免费额度'):
            self.service.recommend(self.dto)
        self.assertEqual(self.llm.generate_text.call_count, 1)
        self.assertFalse(list((Path(self.temp.name) / 'cache').glob('*.json')))

    def test_missing_sound_is_honest_and_removed_assets_are_not_cached(self):
        self.llm.generate_text.return_value = json.dumps(dict(summary='没有匹配', missing_sound='需要特殊节奏', recommendations=[]))
        self.assertEqual(self.service.recommend(self.dto)['recommendations'], [])
        Path(self.asset['path']).unlink()
        result = self.service.recommend(self.dto)
        self.assertEqual(result['candidate_count'], 0)
        self.assertFalse(result['cached'])
        self.assertEqual(self.llm.generate_text.call_count, 1)

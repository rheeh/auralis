import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from app.core.sound_tags import infer_tags, normalize_tags, rank_assets
from app.core.prompts import get_audio_drama_script_prompt
from app.workflows.drama.schemas import ScriptLine
from app.dto.sound_library_dto import SoundTagMatchDTO
from app.services.sound_tag_service import SoundTagService

class SoundTagsTest(unittest.TestCase):
    def test_parse_stores_generated_tags_and_backfills_missing_tags(self):
        self.assertIn('soundTags',get_audio_drama_script_prompt())
        line=ScriptLine(type='sfx',soundPrompt='室内木地板脚步',soundTags=['footstep','木地板'])
        self.assertEqual(line.soundTags,['脚步','木地板'])
        old=ScriptLine(type='sfx',soundPrompt='门外敲门')
        self.assertIn('敲门',old.soundTags)
        self.assertNotIn('开关门',old.soundTags)
        self.assertEqual(ScriptLine(text='谁在敲门？').soundTags,[])

    def test_aliases_negation_and_partial_ranking(self):
        self.assertEqual(normalize_tags(['rain','雨声','雷声']),['雨声','雷声'])
        self.assertNotIn('脚步',infer_tags('没有脚步声，只有雨声'))
        assets=[{'id':'rain','name':'雨','tags':['雨声','室内']},{'id':'steps','name':'步','tags':['脚步','木地板']},{'id':'room','name':'房间','tags':['室内']}]
        ranked=rank_assets(assets,['脚步','木地板','室内'])
        self.assertEqual([a['id'] for a in ranked],['steps'])
        self.assertEqual(ranked[0]['missing_tags'],['室内'])
        self.assertEqual(rank_assets(assets,[]),[])
        self.assertEqual(rank_assets(assets,['警报']),[])

    def test_old_project_matching_needs_no_provider_and_does_not_write(self):
        db=MagicMock();db.get.return_value=SimpleNamespace(id=4,chapter_id=2,sound_tags=None,sound_prompt='纸张翻动',text_content='旧行')
        library=MagicMock();library.list_assets.return_value=[{'id':'paper','name':'纸','tags':['纸张']}]
        with patch('app.services.workflow_llm_service.WorkflowLLMService.make_engine',side_effect=AssertionError('No model call')):
            result=SoundTagService(db,library).match(SoundTagMatchDTO(chapter_id=2,line_id=4))
        self.assertEqual(result['tag_source'],'local')
        self.assertEqual(result['matches'][0]['id'],'paper')
        db.commit.assert_not_called()
        result=SoundTagService(db,library).match(SoundTagMatchDTO(chapter_id=2,line_id=4,tags=[]))
        self.assertEqual(result['matches'],[])
        with self.assertRaises(ValueError):SoundTagService(db,library).match(SoundTagMatchDTO(chapter_id=3,line_id=4))

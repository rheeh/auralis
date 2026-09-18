import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.models.po import (ProjectPO, ChapterPO, LinePO, RolePO, ChatSessionPO,
                           AdaptationRunPO, TimelineTrackPO, AudioTaskPO)
from app.services.factory import get_line_service
from app.services.drama_commit_service import DramaCommitService
from app.services.production_assistant_service import ProductionAssistantAgent


class ReliabilityCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict('os.environ', {'AURALIS_CONFIG_DIR': self.tmp.name})
        self.env.start()
        self.engine = create_engine(f'sqlite:///{self.tmp.name}/test.db')
        event.listen(self.engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.project = ProjectPO(name='测试', project_root_path=self.tmp.name)
        self.db.add(self.project); self.db.flush()
        self.chapter = ChapterPO(project_id=self.project.id, title='同名')
        self.role = RolePO(project_id=self.project.id, name='甲')
        self.db.add_all([self.chapter, self.role]); self.db.flush()
        self.line = LinePO(chapter_id=self.chapter.id, role_id=self.role.id,
                           text_content='原句', production_note='原指导', status='done', is_done=1)
        self.db.add(self.line); self.db.commit()
        self.service = get_line_service(self.db)

    def tearDown(self):
        self.db.close(); self.engine.dispose(); self.env.stop(); self.tmp.cleanup()

    def ready_session(self, name='sess_new', chapter_id=None):
        run = AdaptationRunPO(project_id=self.project.id, title='同名', source_text='固定故事',
             final_json={'title':'同名','logline':'测试','characters':[{'name':'甲'}], 'scenes':[
                 {'title':'场','location':'屋','mood':'平静','lines':[
                     {'type':'dialogue','track':'voice','speaker':'甲','text':'新句','shouldSpeak':True}]}]})
        self.db.add(run); self.db.flush()
        session = ChatSessionPO(id=name, project_id=self.project.id, chapter_id=chapter_id,
            adaptation_run_id=run.id, title='同名', current_stage='script_draft_ready')
        self.db.add(session); self.db.commit()
        return session

    def test_same_title_creates_new_chapter(self):
        session = self.ready_session()
        result = DramaCommitService(self.db).commit_session(session.id)
        self.assertNotEqual(result['chapter_id'], self.chapter.id)
        self.db.refresh(self.line)
        self.assertEqual(self.line.text_content, '原句')

    def test_existing_chapter_requires_explicit_confirmation(self):
        session = self.ready_session(chapter_id=self.chapter.id)
        with self.assertRaises(ValueError):
            DramaCommitService(self.db).commit_session(session.id)
        self.db.refresh(self.line)
        self.assertEqual(self.line.text_content, '原句')

    def test_explicit_null_and_omitted_fields(self):
        self.service.update_line(self.line.id, {'production_note':None})
        self.db.refresh(self.line)
        self.assertIsNone(self.line.production_note)
        self.assertEqual(self.line.text_content, '原句')
        self.service.clear_role_id(self.role.id)
        self.db.refresh(self.line)
        self.assertIsNone(self.line.role_id)

    def test_assistant_note_uses_same_invalidation(self):
        session = ChatSessionPO(id='sess_agent',project_id=self.project.id,chapter_id=self.chapter.id,current_stage='completed')
        track = TimelineTrackPO(project_id=self.project.id, chapter_id=self.chapter.id, track_type='voice', name='人物声', status='ready')
        self.db.add_all([session,track]); self.db.commit()
        ProductionAssistantAgent(self.db)._update_line(session, {'line_id':self.line.id,'production_note':'新指导'})
        self.db.refresh(self.line); self.db.refresh(track)
        self.assertEqual((self.line.status,self.line.is_done),('pending',0))
        self.assertEqual(track.status,'stale')

    def test_update_dto_forbids_internal_fields(self):
        from app.dto.line_dto import LineUpdateDTO
        from pydantic import ValidationError
        for key,value in {'status':'done','is_done':1,'chapter_id':99,'audio_path':'/tmp/x','audio_versions':[]}.items():
            with self.subTest(key=key), self.assertRaises(ValidationError):
                LineUpdateDTO.model_validate({key:value})

    def test_atomic_invalidation_failure_rolls_back_edit(self):
        with patch('app.services.timeline_service.TimelineService.invalidate_line', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.service.update_line(self.line.id, {'text_content':'不应提交'})
        self.db.expire_all()
        self.assertEqual(self.db.get(LinePO,self.line.id).text_content,'原句')

    def test_role_delete_rolls_back_with_its_unbinding(self):
        from app.services.factory import get_role_service
        with patch('app.services.timeline_service.TimelineService.invalidate_line',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):get_role_service(self.db).delete_role(self.role.id)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(RolePO,self.role.id))
        self.assertEqual(self.line.role_id,self.role.id)

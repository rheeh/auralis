import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.models.po import (ProjectPO, ChapterPO, LinePO, RolePO, AdaptationRunPO, ChatSessionPO,
    ChatMessagePO, WorkflowEventPO, AdaptationDraftRevisionPO, AudioTaskPO, AudioAssetPO, TimelineTrackPO, TimelineClipPO)
from app.repositories.project_repository import ProjectRepository
from app.repositories.line_repository import LineRepository
from app.routers.project_router import router
from app.services.project_service import ProjectService


class ProjectDeletionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        def add(row):
            self.db.add(row)
            self.db.flush()
        add(ProjectPO(id=1,name='旧项目',project_root_path=str(self.root)))
        add(ProjectPO(id=2,name='保留项目',project_root_path=str(self.root)))
        add(ChapterPO(id=1,project_id=1,title='旧章节'))
        add(LinePO(id=1,chapter_id=1,text_content='已配音'))
        add(RolePO(id=1,project_id=1,name='角色'))
        add(AdaptationRunPO(id=1,project_id=1,chapter_id=1,title='历史改编'))
        add(ChatSessionPO(id='s',project_id=1,chapter_id=1,adaptation_run_id=1))
        add(ChatMessagePO(id='m',session_id='s',role='user'))
        add(WorkflowEventPO(id='e',session_id='s',project_id=1,sequence=1,event_type='done',stage='completed'))
        add(AdaptationDraftRevisionPO(session_id='s',run_id=1,draft_type='script',revision=1,payload_json={}))
        add(AudioTaskPO(id='a',project_id=1,chapter_id=1,session_id='s',line_id=1,status='done'))
        add(AudioAssetPO(id=1,project_id=1,chapter_id=1,line_id=1,asset_type='tts_take',path='original.wav'))
        add(AudioAssetPO(id=2,project_id=1,chapter_id=1,line_id=1,asset_type='processed',path='processed.wav',source_asset_id=1))
        add(TimelineTrackPO(id=1,project_id=1,chapter_id=1,track_type='voice',name='人物'))
        add(TimelineClipPO(project_id=1,chapter_id=1,track_id=1,line_id=1,asset_id=2,track_type='voice',start_ms=0,duration_ms=1000))
        self.db.commit()
        for pid in [1,2]:
            (self.root/str(pid)).mkdir()
            (self.root/str(pid)/'audio.wav').write_bytes(b'preserved original')
        self.service = ProjectService(ProjectRepository(self.db))
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_old_delete_order_fails_but_endpoint_removes_complete_graph(self):
        # Reproduce the historical order with real FK enforcement, in isolation.
        with self.assertRaises(IntegrityError):
            LineRepository(self.db).delete_all_by_chapter_id(1)
        self.db.rollback()
        result = self.client.delete('/projects/1')
        self.assertEqual(result.json()['code'],200)
        for model in [ChapterPO,LinePO,RolePO,AdaptationRunPO,ChatSessionPO,ChatMessagePO,WorkflowEventPO,AdaptationDraftRevisionPO,AudioTaskPO,AudioAssetPO,TimelineTrackPO,TimelineClipPO]:
            self.assertEqual(self.db.query(model).count(),0,model.__name__)
        self.assertIsNotNone(self.db.get(ProjectPO,2))
        self.assertEqual((self.root/'2/audio.wav').read_bytes(),b'preserved original')
        self.assertFalse((self.root/'1').exists())
        self.assertEqual(self.client.delete('/projects/1').json()['code'],404)

    def test_file_permission_failure_rolls_back_all_database_changes(self):
        with patch('app.services.project_service.Path.rename',side_effect=PermissionError('test denied')):
            response = self.client.delete('/projects/1')
        self.assertEqual(response.status_code,500)
        self.assertIsNotNone(self.db.get(LinePO,1))
        self.assertIsNotNone(self.db.get(AudioTaskPO,'a'))
        self.assertEqual((self.root/'1/audio.wav').read_bytes(),b'preserved original')

    def test_commit_failure_restores_project_directory(self):
        with patch.object(self.db,'commit',side_effect=RuntimeError('commit failed')):
            with self.assertRaisesRegex(RuntimeError,'commit failed'):
                self.service.delete_project(1)
        self.assertIsNotNone(self.db.get(ProjectPO,1))
        self.assertEqual((self.root/'1/audio.wav').read_bytes(),b'preserved original')
        self.assertFalse(list(self.root.glob('.deleting-*')))

    def test_running_job_is_rejected_without_modification(self):
        self.db.get(AudioTaskPO,'a').status='running'
        self.db.commit()
        self.assertEqual(self.client.delete('/projects/1').status_code,409)
        self.assertIsNotNone(self.db.get(ProjectPO,1))
        self.assertTrue((self.root/'1/audio.wav').exists())

    def test_legacy_missing_root_uses_configured_directory(self):
        self.db.get(ProjectPO,1).project_root_path=None
        self.db.commit()
        with patch('app.services.project_service.getConfigPath',return_value=str(self.root/'legacy-config')):
            self.assertTrue(self.service.delete_project(1))
        self.assertTrue((self.root/'1/audio.wav').exists())  # An unconfigured old path is never guessed.

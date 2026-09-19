import unittest
from unittest.mock import Mock
import test_drama_workflow as fixtures
from app.dto.chat_dto import ChatSessionCreateDTO
from app.services.chat_session_service import ChatSessionService
from app.services.drama_workflow_service import WorkflowConflictError

class WorkflowRecoveryTest(unittest.TestCase):
    setUp=fixtures.DramaWorkflowTest.setUp
    tearDown=fixtures.DramaWorkflowTest.tearDown
    _workflow=fixtures.DramaWorkflowTest._workflow

    def test_created_session_restart_waits_for_explicit_http_resume(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.db.database import get_db
        from app.routers.chat_router import router
        from app.runtime.recovery import recover_interrupted
        sid=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))['session_id']
        self.db.close();self.db=self.Session()
        recover_interrupted(self.db)
        state=ChatSessionService(self.db).get(sid)
        self.assertEqual(state['current_stage'],'failed')
        self.assertEqual(state['pending_confirm']['retry_stage'],'created')
        workflow=self._workflow()
        workflow.source_parser.parse=Mock(wraps=workflow.source_parser.parse)
        app=FastAPI();app.include_router(router);app.dependency_overrides[get_db]=lambda:self.db
        with TestClient(app) as client, patch('app.routers.chat_router._run_action',side_effect=workflow.submit_action):
            for _ in range(2):
                self.assertEqual(client.post(f'/chat/sessions/{sid}/resume').status_code,202)
        self.assertEqual(workflow.source_parser.parse.call_count,1)
        self.assertEqual(workflow.snapshot(sid)['current_stage'],'awaiting_role_confirmation')

    def test_role_generation_failure_reuses_saved_parse(self):
        sid=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))['session_id']
        workflow=self._workflow()
        workflow.role_drafter.generate=Mock(side_effect=ValueError('fake roles unavailable'))
        with self.assertRaises(ValueError):workflow.start(sid)
        resumed=self._workflow()
        resumed.source_parser.parse=Mock(side_effect=AssertionError('saved parse must be reused'))
        self.assertEqual(resumed.resume(sid)['current_stage'],'awaiting_role_confirmation')

    def test_review_failure_retries_saved_draft_only(self):
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        workflow=self._workflow();sid=snapshot['session_id'];roles=workflow.start(sid)
        workflow.script_reviewer.review=Mock(side_effect=ValueError('fake reviewer down'))
        action={'action':'confirm_roles','payload':{'roles':roles['role_drafts']['roles']},'client_request_id':'confirm-one'}
        with self.assertRaises(ValueError):workflow.submit_action(sid,action)
        resumed=self._workflow()
        resumed.script_drafter.generate=Mock(side_effect=AssertionError('must not regenerate'))
        self.assertEqual(resumed.resume(sid)['current_stage'],'awaiting_script_confirmation')

    def test_duplicate_action_checked_before_stage(self):
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        workflow=self._workflow();sid=snapshot['session_id'];roles=workflow.start(sid)
        action={'action':'confirm_roles','payload':{'roles':roles['role_drafts']['roles']},'client_request_id':'confirm-one'}
        workflow.submit_action(sid,action)
        workflow.script_drafter.generate=Mock(side_effect=AssertionError('duplicate call'))
        self.assertEqual(workflow.submit_action(sid,action)['current_stage'],'awaiting_script_confirmation')

    def test_stale_session_cannot_acquire_second_lease(self):
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        first=self._workflow();session=first._session(snapshot['session_id'])
        with self.Session() as other_db:
            from app.services.drama_workflow_service import DramaWorkflowService
            second=DramaWorkflowService(other_db);stale=second._session(session.id)
            token=first._acquire_lease(session)
            with self.assertRaises(WorkflowConflictError):second._acquire_lease(stale)
            first._release_lease(session.id,token)

    def test_final_review_retry_does_not_repeat_repair(self):
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        workflow=self._workflow();sid=snapshot['session_id'];roles=workflow.start(sid)
        workflow.script_reviewer.review=Mock(side_effect=[{'passed':False,'score':60,'issues':[]},ValueError('review offline')])
        workflow.script_drafter.revise_from_review=Mock(side_effect=lambda *args:args[4])
        with self.assertRaises(ValueError):workflow.submit_action(sid,{'action':'confirm_roles','payload':{'roles':roles['role_drafts']['roles']},'client_request_id':'repair-case'})
        resumed=self._workflow()
        resumed.script_drafter.generate=Mock(side_effect=AssertionError('must not draft'))
        resumed.script_drafter.revise_from_review=Mock(side_effect=AssertionError('must not repair again'))
        self.assertEqual(resumed.resume(sid)['current_stage'],'awaiting_script_confirmation')

    def test_repair_failure_retry_skips_initial_review(self):
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        workflow=self._workflow();sid=snapshot['session_id'];roles=workflow.start(sid)
        workflow.script_reviewer.review=Mock(return_value={'passed':False,'score':60,'issues':[]})
        workflow.script_drafter.revise_from_review=Mock(side_effect=ValueError('repair offline'))
        with self.assertRaises(ValueError):workflow.submit_action(sid,{'action':'confirm_roles','payload':{'roles':roles['role_drafts']['roles']},'client_request_id':'repair-failure'})
        resumed=self._workflow()
        resumed.script_drafter.generate=Mock(side_effect=AssertionError('must not draft'))
        resumed.script_drafter.revise_from_review=Mock(side_effect=lambda *args:args[4])
        resumed.script_reviewer.review=Mock(return_value={'passed':True,'score':92,'issues':[]})
        self.assertEqual(resumed.resume(sid)['current_stage'],'awaiting_script_confirmation')
        self.assertEqual(resumed.script_reviewer.review.call_count,1)

    def test_event_sequence_does_not_use_stale_session_counter(self):
        from app.models.po import ChatSessionPO
        from app.workflows.drama.events import WorkflowEventPublisher
        snapshot=ChatSessionService(self.db).create(ChatSessionCreateDTO(project_id=self.project_id,source_text='固定故事'))
        session=self.db.get(ChatSessionPO,snapshot['session_id'])
        with self.Session() as other:
            stale=other.get(ChatSessionPO,session.id)
            first=WorkflowEventPublisher(self.db).publish(session,'test_one')
            second=WorkflowEventPublisher(other).publish(stale,'test_two')
        self.assertEqual(second['sequence'],first['sequence']+1)

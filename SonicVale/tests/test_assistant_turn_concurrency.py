import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import test_production_assistant as fixtures
from app.db.database import get_db
from app.models.po import ChatMessagePO
from app.routers.chat_router import router
from app.runtime.recovery import recover_interrupted
from app.services.production_assistant_service import ProductionAssistantAgent, AssistantPlan, AssistantToolCall


class AssistantTurnConcurrencyTest(unittest.TestCase):
    setUp = fixtures.ProductionAssistantTest.setUp
    tearDown = fixtures.ProductionAssistantTest.tearDown

    def test_parallel_sessions_claim_before_planning_or_tools(self):
        user_id = ProductionAssistantAgent(self.db).accept_message('sess_assistant', '修改台本', 'parallel').id
        self.db.rollback()
        barrier, started, release = threading.Barrier(2), threading.Event(), threading.Event()
        plans, tools = [], []

        def run():
            with self.Session() as db:
                agent = ProductionAssistantAgent(db)
                original = agent._session
                def synchronized_session(sid):
                    session = original(sid)
                    barrier.wait(timeout=3)
                    return session
                agent._session = synchronized_session
                def plan(*_):
                    plans.append(1)
                    started.set()
                    self.assertTrue(release.wait(3))
                    return AssistantPlan(tool_calls=[AssistantToolCall(name='revise_current_draft', arguments={})])
                agent._plan = plan
                agent._execute_tool = lambda *_: tools.append(1) or {'ok':True, 'summary':'完成'}
                try:
                    return agent.run_turn('sess_assistant', user_id)
                except Exception as exc:
                    return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            self.assertTrue(started.wait(3))
            wait(futures, timeout=.2, return_when=FIRST_COMPLETED)
            release.set()
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(tools), 1)
        self.assertFalse(any(isinstance(result, Exception) for result in results), results)
        agent = ProductionAssistantAgent(self.db)
        agent._plan = Mock(side_effect=AssertionError('completed turn must not replan'))
        self.assertIsNotNone(agent.run_turn('sess_assistant', user_id))

    def test_http_duplicate_only_schedules_once(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        with TestClient(app) as client, patch('app.routers.chat_router._run_assistant') as runner:
            for _ in range(2):
                response = client.post('/chat/sessions/sess_assistant/message',
                                       json={'message':'检查项目', 'client_request_id':'same-http'})
                self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(response.json()['data']['turn_status'], 'queued')

    def test_interrupted_tool_is_not_replayed_after_restart(self):
        agent = ProductionAssistantAgent(self.db)
        user = agent.accept_message('sess_assistant', '修改', 'interrupted')
        agent._plan = lambda *_: AssistantPlan(tool_calls=[AssistantToolCall(name='update_line', arguments={})])
        agent._execute_tool = Mock(side_effect=KeyboardInterrupt('simulated process exit'))
        with self.assertRaises(KeyboardInterrupt):
            agent.run_turn('sess_assistant', user.id)
        self.assertIsNotNone(user.payload_json.get('pending_tool'))
        self.db.close()
        self.db = self.Session()
        recover_interrupted(self.db)
        recovered = self.db.get(ChatMessagePO, user.id)
        self.assertEqual(recovered.turn_status, 'interrupted')
        self.assertIn('operation_key', recovered.payload_json['pending_tool'])
        retry = ProductionAssistantAgent(self.db)
        retry._plan = Mock(side_effect=AssertionError('unknown write must not replay'))
        self.assertIsNone(retry.run_turn('sess_assistant', user.id))

    def test_lost_turn_claim_cannot_execute_a_late_plan(self):
        agent=ProductionAssistantAgent(self.db)
        user=agent.accept_message('sess_assistant','修改','lost-claim')
        def plan(*_):
            with self.Session() as recovered:
                recover_interrupted(recovered)
            return AssistantPlan(tool_calls=[AssistantToolCall(name='update_line',arguments={})])
        agent._plan=plan
        agent._execute_tool=Mock(return_value={'ok':True,'summary':'must not run'})
        agent.run_turn('sess_assistant',user.id)
        agent._execute_tool.assert_not_called()

    def test_lost_turn_claim_cannot_start_final_model_call(self):
        agent = ProductionAssistantAgent(self.db)
        user = agent.accept_message('sess_assistant', '检查进度', 'lost-before-summary')
        calls = []
        def plan(*_):
            if not calls:
                calls.append(1)
                return AssistantPlan(tool_calls=[AssistantToolCall(name='get_project_status', arguments={})])
            with self.Session() as recovered:
                recover_interrupted(recovered)
            return AssistantPlan(reply='已有结果')
        agent._plan = plan
        agent._execute_tool = Mock(return_value={'ok': True, 'summary': '已检查'})
        agent._final_reply = Mock(return_value='不应调用')
        self.assertIsNone(agent.run_turn('sess_assistant', user.id))
        agent._execute_tool.assert_called_once()
        agent._final_reply.assert_not_called()

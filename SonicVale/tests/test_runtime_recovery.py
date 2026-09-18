import asyncio
import unittest
from unittest.mock import Mock
import test_production_assistant as fixtures
from app.models.po import AudioTaskPO, LinePO, ChatSessionPO
from app.runtime.recovery import InstanceLock, recover_interrupted
from app.services.production_assistant_service import ProductionAssistantAgent,AssistantPlan,AssistantToolCall

class RuntimeRecoveryTest(unittest.TestCase):
    setUp=fixtures.ProductionAssistantTest.setUp
    tearDown=fixtures.ProductionAssistantTest.tearDown

    def test_restart_marks_interrupted_without_queue_or_provider(self):
        line=self.db.get(LinePO,self.line_id);line.status='processing'
        self.db.add(AudioTaskPO(id='lost',project_id=self.project_id,chapter_id=line.chapter_id,
            line_id=line.id,status='processing',run_token='old'))
        self.db.commit()
        self.assertEqual(recover_interrupted(self.db),1)
        task=self.db.get(AudioTaskPO,'lost')
        self.assertEqual(task.error_code,'PROCESS_INTERRUPTED');self.assertIsNone(task.run_token)
        self.assertEqual(line.status,'pending')

    def test_single_instance_required_before_recovery(self):
        lock=InstanceLock(self.tempdir.name)
        try:
            with self.assertRaises(RuntimeError):InstanceLock(self.tempdir.name)
        finally:lock.close()

    def test_partial_success_survives_failure_and_retry(self):
        agent=ProductionAssistantAgent(self.db)
        user=agent.accept_message('sess_assistant','把第一句指导改为警觉，再修改不存在的一句','partial-test')
        agent._plan=lambda *_:AssistantPlan(tool_calls=[
            AssistantToolCall(name='update_line',arguments={'line_id':self.line_id,'production_note':'警觉'}),
            AssistantToolCall(name='update_line',arguments={'line_id':99999,'text':'不可写'})])
        reply=agent.run_turn('sess_assistant',user.id)
        self.assertEqual(len(reply.payload_json.get('tool_results',[])),1)
        self.assertIn('部分',reply.content)
        agent._execute_tool=Mock(side_effect=AssertionError('duplicate tool'))
        self.assertEqual(agent.run_turn('sess_assistant',user.id).id,reply.id)

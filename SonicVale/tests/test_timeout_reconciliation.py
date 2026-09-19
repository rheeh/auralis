import asyncio
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import app.core.tts_runtime as runtime
import test_generation_consistency as fixtures
from app.models.po import AudioTaskPO, TTSGenerationPO
from app.runtime.recovery import recover_interrupted


class TimeoutReconciliationTest(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.GenerationConsistencyTest.setUp
    tearDown=fixtures.GenerationConsistencyTest.tearDown
    enqueue=fixtures.GenerationConsistencyTest.enqueue
    output=fixtures.GenerationConsistencyTest.output

    async def test_timeout_is_visible_before_late_output_and_keeps_slot(self):
        task,item=self.enqueue();queue=asyncio.Queue();queue.put_nowait(item)
        release=threading.Event();notified=asyncio.Event();calls=[]
        def blocked(request,observer):
            calls.append(request['output_path'])
            self.assertTrue(release.wait(3))
            return self.output({'request':request})
        async def notify(db,task,remaining):
            if task.status=='failed':notified.set()
        with ThreadPoolExecutor(max_workers=1) as executor:
            app=SimpleNamespace(state=SimpleNamespace(tts_queue=queue,tts_executor=executor))
            with patch.object(runtime,'SessionLocal',sessionmaker(bind=self.engine)),patch.object(runtime,'execute_prepared',side_effect=blocked),patch.object(runtime,'TTS_TIMEOUT_SECONDS',.02),patch.object(runtime,'_notify',side_effect=notify):
                worker=asyncio.create_task(runtime.tts_worker(app))
                try:
                    await asyncio.wait_for(notified.wait(),1)
                    self.db.expire_all()
                    trace=self.db.scalar(select(TTSGenerationPO))
                    self.assertEqual(trace.status,'timed_out')
                    self.assertEqual(trace.result_json['execution_state'],'running_after_timeout')
                    self.assertEqual(runtime.execution_health(app)['blocked_slots'],1)
                    self.assertEqual(queue._unfinished_tasks,1)
                    self.assertEqual(len(calls),1)
                    from app.services.audio_task_service import AudioTaskService
                    following=AudioTaskService(self.db).enqueue(queue,self.project.id,self.chapter.id,self.line,None)
                    self.assertEqual(following.status,'queued')
                    self.assertEqual(queue.qsize(),1)
                    release.set();await asyncio.wait_for(queue.join(),2)
                    self.db.expire_all()
                    self.assertEqual(trace.status,'timed_out')
                    self.assertEqual(trace.result_json['execution_state'],'late_succeeded')
                    self.assertEqual(trace.result_json['orphan_path'],item['request']['output_path'])
                    self.assertNotEqual(self.line.active_audio_version_id,item['run_token'])
                    self.assertEqual(self.line.active_audio_version_id,following.run_token)
                    self.assertEqual(self.db.get(AudioTaskPO,task.id).error_code,'TTS_TIMEOUT')
                    self.assertEqual(runtime.execution_health(app)['blocked_slots'],0)
                finally:
                    release.set();worker.cancel();await asyncio.gather(worker,return_exceptions=True)

    async def test_shutdown_records_interrupted_trace(self):
        task,item=self.enqueue();queue=asyncio.Queue();queue.put_nowait(item)
        release=threading.Event();started=threading.Event()
        def blocked(*_):started.set();release.wait(3);return self.output(item)
        with ThreadPoolExecutor(max_workers=1) as executor:
            app=SimpleNamespace(state=SimpleNamespace(tts_queue=queue,tts_executor=executor))
            with patch.object(runtime,'SessionLocal',sessionmaker(bind=self.engine)),patch.object(runtime,'execute_prepared',side_effect=blocked):
                worker=asyncio.create_task(runtime.tts_worker(app))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait,1))
                    worker.cancel();await asyncio.gather(worker,return_exceptions=True)
                    self.db.expire_all()
                    trace=self.db.scalar(select(TTSGenerationPO))
                    self.assertEqual(trace.status,'interrupted')
                    self.assertEqual(trace.result_json['execution_state'],'unknown_after_shutdown')
                finally:release.set()
                await asyncio.sleep(.02)

    async def test_restart_reconciles_active_and_timed_out_traces(self):
        for status in ['preparing','requesting','timed_out']:
            self.db.add(TTSGenerationPO(id=status,project_id=self.project.id,chapter_id=self.chapter.id,
                line_id=self.line.id,status=status,result_json={'execution_state':'running_after_timeout'}))
        self.db.commit();recover_interrupted(self.db)
        for trace in self.db.scalars(select(TTSGenerationPO)):
            self.assertNotIn(trace.status,['preparing','requesting'])
            self.assertEqual(trace.result_json['execution_state'],'unknown_after_shutdown')
            self.assertIsNotNone(trace.completed_at)

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch
from sqlalchemy.orm import sessionmaker
import test_generation_consistency as fixtures
import app.core.tts_runtime as runtime

class WorkerBoundaryTest(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.GenerationConsistencyTest.setUp
    tearDown=fixtures.GenerationConsistencyTest.tearDown
    enqueue=fixtures.GenerationConsistencyTest.enqueue
    output=fixtures.GenerationConsistencyTest.output

    async def test_malformed_item_does_not_stop_following_valid_task(self):
        task,item=self.enqueue()
        queue=asyncio.Queue();queue.put_nowait(None);queue.put_nowait(item)
        with ThreadPoolExecutor(max_workers=1) as executor:
            app=SimpleNamespace(state=SimpleNamespace(tts_queue=queue,tts_executor=executor))
            with patch.object(runtime,'SessionLocal',sessionmaker(bind=self.engine)),patch.object(runtime,'execute_prepared',side_effect=lambda request,observer:self.output(item)):
                worker=asyncio.create_task(runtime.tts_worker(app))
                try:await asyncio.wait_for(queue.join(),2)
                finally:
                    worker.cancel();await asyncio.gather(worker,return_exceptions=True)
        self.db.expire_all();self.assertEqual(self.line.status,'done')

    async def test_timed_out_thread_never_adopts_its_late_file(self):
        task,item=self.enqueue();queue=asyncio.Queue();queue.put_nowait(item)
        def slow(request,observer):
            time.sleep(.06);return self.output(item)
        with ThreadPoolExecutor(max_workers=1) as executor:
            app=SimpleNamespace(state=SimpleNamespace(tts_queue=queue,tts_executor=executor))
            with patch.object(runtime,'SessionLocal',sessionmaker(bind=self.engine)),patch.object(runtime,'execute_prepared',side_effect=slow),patch.object(runtime,'TTS_TIMEOUT_SECONDS',.01):
                worker=asyncio.create_task(runtime.tts_worker(app))
                try:await asyncio.wait_for(queue.join(),2)
                finally:
                    worker.cancel();await asyncio.gather(worker,return_exceptions=True)
        self.db.expire_all();self.assertNotEqual(self.line.status,'done')
        self.assertIsNone(self.line.active_audio_version_id)
        self.assertEqual(self.db.get(type(task),task.id).error_code,'TTS_TIMEOUT')

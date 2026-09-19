import asyncio
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import get_db
from app.models.po import AudioTaskPO, ChatSessionPO
from app.routers.chat_router import router
from app.services.audio_task_service import AudioTaskService
import test_generation_consistency as fixtures


class RegenerationEntryTest(unittest.TestCase):
    setUp = fixtures.GenerationConsistencyTest.setUp
    tearDown = fixtures.GenerationConsistencyTest.tearDown
    output = fixtures.GenerationConsistencyTest.output

    def client(self):
        session = ChatSessionPO(id='regeneration', project_id=self.project.id,
                                chapter_id=self.chapter.id, current_stage='completed')
        self.db.add(session)
        self.db.commit()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.state.tts_queue = asyncio.Queue(maxsize=4)
        return TestClient(app), app.state.tts_queue

    def test_http_active_attempt_rejects_guidance_without_saving(self):
        client, queue = self.client()
        service = AudioTaskService(self.db)
        task = service.enqueue(queue, self.project.id, self.chapter.id, self.line, None, 'regeneration')
        item = queue.get_nowait()
        self.assertTrue(service.claim(task.id, item['run_token']))
        for status in ('queued', 'processing', 'completing'):
            task.status = status
            self.db.commit()
            response = client.post(f'/chat/sessions/regeneration/audio-tasks/lines/{self.line.id}/regenerate',
                                   json={'prompt': '新指导 B'})
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()['data']['task_id'], task.id)
            self.assertIn('原指导', str(response.json()['data']['input_snapshot']))
            self.db.refresh(self.line)
            self.assertEqual(self.line.production_note, '原指导')
            self.assertEqual(len(list(self.db.scalars(select(AudioTaskPO)))), 1)
            self.assertEqual(queue.qsize(), 0)
        task.status = 'processing'
        self.db.commit()
        # B was rejected, so A remains valid for the unchanged stored input.
        self.assertTrue(service.complete(task.id, item['run_token'], self.output(item)))
        self.assertNotIn('新指导 B', str(self.line.audio_versions))

    def test_http_new_attempt_freezes_saved_guidance(self):
        client, queue = self.client()
        response = client.post(f'/chat/sessions/regeneration/audio-tasks/lines/{self.line.id}/regenerate',
                               json={'prompt': '新指导 B'})
        self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(self.line)
        self.assertEqual(self.line.production_note, '新指导 B')
        task = self.db.get(AudioTaskPO, response.json()['data']['task_id'])
        self.assertIn('新指导 B', str(task.input_snapshot))
        self.assertEqual(queue.qsize(), 1)

    def test_http_full_queue_does_not_save_guidance(self):
        client, queue = self.client()
        for _ in range(4):
            queue.put_nowait({})
        response = client.post(f'/chat/sessions/regeneration/audio-tasks/lines/{self.line.id}/regenerate',
                               json={'prompt': '新指导 B'})
        self.assertEqual(response.status_code, 429, response.text)
        self.db.refresh(self.line)
        self.assertEqual(self.line.production_note, '原指导')

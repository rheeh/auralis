import asyncio
import os
import wave
import unittest
from unittest.mock import patch
import test_reliability_commands as fixtures
from app.dto.line_dto import LineCreateDTO
from app.models.po import TTSProviderPO
from app.services.audio_task_service import AudioTaskService


class GenerationConsistencyTest(unittest.TestCase):
    tearDown=fixtures.ReliabilityCommandsTest.tearDown
    def setUp(self):
        fixtures.ReliabilityCommandsTest.setUp(self)
        provider=TTSProviderPO(name='fake edge',provider_type='edge',api_base_url='http://unused.invalid',status=1)
        self.db.add(provider); self.db.flush()
        self.project.tts_provider_id=provider.id
        self.line.audio_path=f'{self.tmp.name}/original.wav'
        self.db.commit()

    def enqueue(self):
        q=asyncio.Queue(maxsize=5)
        task=AudioTaskService(self.db).enqueue(q,self.project.id,self.chapter.id,self.line,
            LineCreateDTO(id=self.line.id,chapter_id=self.chapter.id,text_content=self.line.text_content,role_id=self.line.role_id,audio_path=self.line.audio_path))
        return task,q.get_nowait()

    def output(self, item):
        path=item['request']['output_path']
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with wave.open(path,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*400)
        return path

    def test_old_input_retained_without_selecting(self):
        task,item=self.enqueue()
        svc=AudioTaskService(self.db)
        self.assertTrue(svc.claim(task.id,item['run_token']))
        path=self.output(item)
        self.service.update_line(self.line.id,{'text_content':'已经修改'})
        self.assertFalse(svc.complete(task.id,item['run_token'],path))
        self.db.refresh(self.line)
        self.assertEqual(self.line.status,'pending')
        self.assertIsNone(self.line.active_audio_version_id)
        self.assertEqual(len(self.line.audio_versions),1)

    def test_duplicate_completion_idempotent_and_unique_output(self):
        task,item=self.enqueue();svc=AudioTaskService(self.db)
        self.assertNotEqual(item['request']['output_path'],self.line.audio_path)
        svc.claim(task.id,item['run_token'])
        path=self.output(item)
        self.assertTrue(svc.complete(task.id,item['run_token'],path))
        svc.complete(task.id,item['run_token'],path)
        self.db.refresh(self.line)
        self.assertEqual(len(self.line.audio_versions),1)
        self.assertEqual(self.line.status,'done')

    def test_settings_change_invalidates_completion(self):
        task,item=self.enqueue();svc=AudioTaskService(self.db);svc.claim(task.id,item['run_token'])
        self.project.description='新的作品背景';self.db.commit()
        self.assertFalse(svc.complete(task.id,item['run_token'],self.output(item)))

    def test_enqueue_failure_is_recoverable(self):
        q=asyncio.Queue()
        with patch.object(q,'put_nowait',side_effect=RuntimeError('queue offline')):
            with self.assertRaises(RuntimeError):
                AudioTaskService(self.db).enqueue(q,self.project.id,self.chapter.id,self.line,
                    LineCreateDTO(id=self.line.id,chapter_id=self.chapter.id))
        self.db.refresh(self.line)
        self.assertNotEqual(self.line.status,'processing')

    def test_material_selection_preserves_existing_take_history(self):
        task,item=self.enqueue();svc=AudioTaskService(self.db);svc.claim(task.id,item['run_token'])
        path=self.output(item);svc.complete(task.id,item['run_token'],path)
        saved=list(self.line.audio_versions)
        self.service.attach_audio_asset(self.line.id,path)
        self.db.refresh(self.line)
        self.assertEqual(self.line.audio_versions[:len(saved)],saved)

    def test_version_switch_rolls_back_if_invalidation_fails(self):
        task,item=self.enqueue();svc=AudioTaskService(self.db);svc.claim(task.id,item['run_token'])
        path=self.output(item);svc.complete(task.id,item['run_token'],path)
        old=self.line.active_audio_version_id
        other=self.service.register_generated_audio_version(self.line.id,path)
        with patch('app.services.timeline_service.TimelineService.invalidate_line',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.service.activate_generated_audio_version(self.line.id,old)
        self.db.expire_all()
        self.assertEqual(self.line.active_audio_version_id,other['id'])

    def test_fingerprint_covers_long_inputs_but_not_credentials(self):
        from app.services.speech.request import prepare_request
        self.line.production_note='a'*25000+'x';self.db.commit()
        _,_,first=prepare_request(self.db,self.project.id,self.line.id)
        self.line.production_note='a'*25000+'y';self.db.commit()
        _,_,second=prepare_request(self.db,self.project.id,self.line.id)
        self.assertNotEqual(first,second)
        provider=self.db.get(TTSProviderPO,self.project.tts_provider_id)
        provider.api_key='new-secret';self.db.commit()
        _,snapshot,third=prepare_request(self.db,self.project.id,self.line.id)
        self.assertEqual(second,third)
        self.assertNotIn('new-secret',str(snapshot))

    def test_parallel_enqueue_creates_only_one_active_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from sqlalchemy.orm import sessionmaker
        from app.models.po import LinePO
        project_id,chapter_id,line_id=self.project.id,self.chapter.id,self.line.id
        Session=sessionmaker(bind=self.engine)
        def enqueue():
            with Session() as db:
                line=db.get(LinePO,line_id);queue=asyncio.Queue()
                task=AudioTaskService(db).enqueue(queue,project_id,chapter_id,line,LineCreateDTO(id=line_id,chapter_id=chapter_id))
                return task.id,queue.qsize()
        self.db.rollback()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:enqueue(),range(2)))
        self.assertEqual(len({result[0] for result in results}),1)
        self.assertEqual(sum(result[1] for result in results),1)

    def test_task_completion_is_not_current_production_progress(self):
        from app.models.po import ChatSessionPO
        session=ChatSessionPO(id='progress',project_id=self.project.id,chapter_id=self.chapter.id,current_stage='completed')
        self.db.add(session);self.db.commit()
        queue=asyncio.Queue();svc=AudioTaskService(self.db)
        task=svc.enqueue(queue,self.project.id,self.chapter.id,self.line,LineCreateDTO(id=self.line.id,chapter_id=self.chapter.id),session.id)
        item=queue.get_nowait();svc.claim(task.id,item['run_token']);svc.complete(task.id,item['run_token'],self.output(item))
        self.service.update_line(self.line.id,{'production_note':'different'})
        result=svc.summary(session.id)
        self.assertEqual(result['counts']['done'],1)
        self.assertEqual(result['completed'],0)
        self.assertEqual(result['total'],1)

    def test_legacy_processing_preserves_selected_source_file(self):
        import hashlib
        from pathlib import Path
        from app.dto.line_dto import LineAudioProcessDTO
        task,item=self.enqueue();svc=AudioTaskService(self.db);svc.claim(task.id,item['run_token'])
        path=self.output(item);svc.complete(task.id,item['run_token'],path)
        before=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.assertTrue(self.service.process_audio(self.line.id,LineAudioProcessDTO(silence_sec=.1)))
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),before)
        self.db.refresh(self.line)
        self.assertIsNotNone(self.line.active_audio_variant_id)

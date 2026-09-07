import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.models.po import TTSProviderPO, VoicePO
from app.dto.voice_dto import VoiceCloneDTO
from app.services.voice_clone_service import VoiceCloneService

class VoiceCloneTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.provider=TTSProviderPO(name='test',model='qwen-audio-3.0-tts-plus',provider_type='cloud',api_base_url='https://dashscope.aliyuncs.com/api/v1',api_key='test-key',status=1)
        self.db.add(self.provider);self.db.commit()
        self.dto=VoiceCloneDTO(tts_provider_id=self.provider.id,name='Reference A',audio_url='https://example.org/voice.wav',license_note='CC0 voice donation',rights_confirmed=True)
        self.config=patch('app.services.voice_clone_service.getConfigPath',return_value=self.temp.name);self.config.start()
    def tearDown(self):
        self.config.stop();self.db.close();self.engine.dispose();self.temp.cleanup()
    def test_registration_keeps_source_and_receipt_and_reuses_cloud_id(self):
        response=MagicMock(status_code=200)
        response.json.return_value={'output':{'voice_id':'qwen-audio-3.0-tts-plus-avsample-123'},'request_id':'test'}
        with patch('app.services.voice_clone_service.requests.post',return_value=response) as post:
            voice=VoiceCloneService(self.db).create(self.dto)
            self.assertIn('qwen_voice:qwen-audio-3.0-tts-plus-avsample-123',voice.description)
            self.assertIsNone(voice.reference_path)
            payload=post.call_args.kwargs['json'];self.assertEqual(payload['input']['target_model'],self.provider.model)
            self.assertEqual(payload['input']['url'],self.dto.audio_url)
            VoiceCloneService(self.db).create(self.dto.model_copy(update={'name':'Alias'}))
            self.assertEqual(post.call_count,1)
        receipt=json.loads(next((Path(self.temp.name)/'voice_clones').glob('*.json')).read_text())
        self.assertEqual(receipt['license_note'],self.dto.license_note)
        self.assertNotIn('test-key',json.dumps(receipt))
    def test_authorization_unsupported_model_and_duplicate_rejected_before_network(self):
        with patch('app.services.voice_clone_service.requests.post') as post:
            with self.assertRaises(ValueError):VoiceCloneService(self.db).create(self.dto.model_copy(update={'rights_confirmed':False}))
            self.provider.model='qwen3-tts-vc-2026-01-22';self.db.commit()
            with self.assertRaises(ValueError):VoiceCloneService(self.db).create(self.dto)
            post.assert_not_called()
    def test_cloud_failure_creates_no_voice_and_does_not_retry(self):
        response=MagicMock(status_code=403);response.json.return_value={'code':'AllocationQuota.FreeTierOnly'}
        with patch('app.services.voice_clone_service.requests.post',return_value=response) as post:
            with self.assertRaisesRegex(ValueError,'未自动重试'):VoiceCloneService(self.db).create(self.dto)
            self.assertEqual(post.call_count,1)
        self.assertEqual(self.db.query(VoicePO).count(),0)

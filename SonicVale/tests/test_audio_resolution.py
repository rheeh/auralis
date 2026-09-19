import os
import unittest
from pathlib import Path

import test_generation_consistency as fixtures
from app.services.audio_selection import selected_audio_path
from app.services.production.audio_state import generation_state
from app.services.speech.request import prepare_request
from app.services.timeline_service import TimelineService
from app.services.timeline_render_service import TimelineRenderService


class AudioResolutionTest(unittest.TestCase):
    setUp=fixtures.GenerationConsistencyTest.setUp
    tearDown=fixtures.GenerationConsistencyTest.tearDown
    output=fixtures.GenerationConsistencyTest.output

    def takes(self):
        _,_,a=prepare_request(self.db,self.project.id,self.line.id)
        path_a=self.output({'request':{'output_path':f'{self.tmp.name}/a.wav'}})
        self.line.production_note='输入 B';self.db.commit()
        _,_,b=prepare_request(self.db,self.project.id,self.line.id)
        path_b=self.output({'request':{'output_path':f'{self.tmp.name}/b.wav'}})
        self.line.audio_versions=[{'id':'A','audio_path':path_a,'input_fingerprint':a,'text':'A 的文本'},
                                  {'id':'B','audio_path':path_b,'input_fingerprint':b,'text':'B 的文本'}]
        self.line.audio_variants=[{'id':'processed-B','audio_path':f'{self.tmp.name}/missing.wav','source_audio_version_id':'B'}]
        self.line.active_audio_variant_id='processed-B'
        self.line.active_audio_version_id='A'
        self.line.audio_path=path_b
        self.db.commit()
        return path_a,path_b

    def test_missing_processed_file_uses_actual_fallback_fingerprint(self):
        a,b=self.takes()
        self.assertEqual(selected_audio_path(self.line),a)
        state=generation_state(self.db,self.line)
        self.assertFalse(state['input_current'])
        self.assertEqual(state['selected_version_id'],'A')
        self.assertIsNone(state['selected_variant_id'])
        self.assertEqual(state['audio_resolution']['fallback_reason'],'selected_variant_missing')
        timeline=TimelineService(self.db).build_chapter_timeline(self.project.id,self.chapter.id)
        self.assertEqual(timeline['audio_sources'][str(self.line.id)]['source_version_id'],'A')
        self.assertEqual(timeline['status'],'stale')
        with self.assertRaisesRegex(ValueError,'stale'):
            TimelineRenderService(self.db).render_chapter(self.project.id,self.chapter.id)

    def test_missing_generated_file_canonical_fallback_matches_export_source(self):
        a,b=self.takes()
        self.line.active_audio_variant_id=None
        Path(a).unlink();self.db.commit()
        state=generation_state(self.db,self.line)
        self.assertTrue(state['input_current'])
        self.assertEqual(state['selected_version_id'],'B')
        self.assertEqual(state['audio_resolution']['path'],b)
        timeline=TimelineService(self.db).build_chapter_timeline(self.project.id,self.chapter.id)
        self.assertEqual(timeline['clip_count'],1)
        rendered=TimelineRenderService(self.db).render_chapter(self.project.id,self.chapter.id)
        import json
        manifest=json.loads(Path(rendered['manifest_path']).read_text())
        self.assertEqual(manifest['clips'][0]['asset_path'],b)
        self.assertEqual(manifest['audio_sources'][str(self.line.id)]['source_version_id'],'B')

    def test_existing_processed_file_retains_its_source(self):
        a,b=self.takes()
        variant_path=self.line.audio_variants[0]['audio_path']
        self.output({'request':{'output_path':variant_path}})
        state=generation_state(self.db,self.line)
        self.assertTrue(state['input_current'])
        self.assertEqual(state['selected_version_id'],'B')
        self.assertEqual(state['selected_variant_id'],'processed-B')
        self.assertEqual(selected_audio_path(self.line),variant_path)

import unittest
from unittest.mock import patch
import test_timeline_render_service as fixtures
from app.services.timeline_render_service import TimelineRenderService
from app.models.po import TimelineClipPO

class RenderSnapshotTest(unittest.TestCase):
    setUp=fixtures.TimelineRenderServiceTest.setUp
    tearDown=fixtures.TimelineRenderServiceTest.tearDown
    _tone=fixtures.TimelineRenderServiceTest._tone
    _build_three_clip_timeline=fixtures.TimelineRenderServiceTest._build_three_clip_timeline

    def test_edit_during_render_keeps_old_snapshot_stale(self):
        self._build_three_clip_timeline()
        service=TimelineRenderService(self.session)
        real_render=service._render_active_clips
        def edit_while_rendering(*args):
            real_render(*args)
            clip=self.session.query(TimelineClipPO).first()
            clip.volume_db=-24;self.session.commit()
        with patch.object(service,'_render_active_clips',side_effect=edit_while_rendering):
            result=service.render_chapter(self.project.id,self.chapter.id)
        with self.assertRaisesRegex(ValueError,'过期'):
            service.get_latest_render(self.project.id,self.chapter.id)

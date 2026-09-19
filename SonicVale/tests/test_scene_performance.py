import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import ValidationError
from sqlalchemy import select, text, create_engine
from app.db.migrations import apply_schema_migrations

from app.core.speech_context_budget import compile_context_instruction, instruction_weight
from app.models.po import AdaptationRunPO, ChapterPO, ChatSessionPO, LinePO, ProjectSpeechProfilePO
from app.services.drama_commit_service import DramaCommitService
from app.services.scene_performance_service import bind_scene_performance, save_chapter_performances, performance_issues
from app.services.script_draft_service import ScriptDraftService
from app.services.script_review_service import ScriptReviewService
from app.workflows.drama.schemas import DirectedDramaScript, DramaScript, ScriptLine
from tests import test_speech_direction as speech_fixture


def directed_script():
    return {'title': '重逢', 'characters': [{'name': '林默'}, {'name': '小安'}], 'scenes': [{
        'title': '站台',
        'performancePlan': {
            'purpose': '确认两人的关系', 'baseline': '自然交谈，保持平稳', 'pace': '听完再回答',
            'characters': [
                {'speaker': '林默', 'objective': '确认对方行程', 'relationship': '尚不熟悉', 'baseline': '清晰稳定'},
                {'speaker': '小安', 'objective': '简短回答', 'relationship': '保持距离', 'baseline': '日常语调'},
            ],
            'beats': [
                {'id': 'b1', 'purpose': '相互试探', 'delivery': '疑问词轻点'},
                {'id': 'b2', 'purpose': '秘密揭露', 'delivery': '未来高潮才激烈哭喊'},
            ],
        },
        'lines': [
            {'type': 'dialogue', 'speaker': '林默', 'text': '你去过重庆吗？', 'strength': '微弱',
             'performanceCue': {'beatId': 'b1', 'intent': '询问行程', 'delivery': '疑问词轻点'}},
            {'type': 'dialogue', 'speaker': '小安', 'text': '我昨天才回来。',
             'performanceCue': {'beatId': 'b1', 'intent': '回答来处', 'respondsTo': 1}},
            {'type': 'dialogue', 'speaker': '林默', 'text': '重庆的 AI lab 还在吗？', 'strength': '强烈',
             'performanceCue': {'beatId': 'b1', 'intent': '再次确认', 'respondsTo': 2}},
            {'type': 'dialogue', 'speaker': '林默', 'text': '没什么，我随便问问。', 'strength': '微弱',
             'performanceCue': {'beatId': 'b2', 'intent': '突然回避', 'turningPoint': True, 'evidence': '他突然认出了她'}},
        ],
    }]}


class ScenePerformanceTest(unittest.TestCase):
    def setUp(self):
        self.f = speech_fixture.SpeechDirectionTest(); self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def bind(self, script=None):
        f = self.f
        script = DirectedDramaScript.model_validate(script or directed_script()).model_dump()
        entry = bind_scene_performance(script['scenes'][0], f.lines, {f.role.id: f.role.name, f.other.id: f.other.name}, '他突然认出了她')
        save_chapter_performances(f.chapter, [entry]); f.db.commit()
        return entry

    def test_new_generations_require_plan_but_old_drafts_remain_readable(self):
        script = directed_script(); del script['scenes'][0]['performancePlan']
        for line in script['scenes'][0]['lines']: line.pop('performanceCue')
        self.assertIsNone(DramaScript.model_validate(script).scenes[0].performancePlan)
        with self.assertRaises(ValidationError): DirectedDramaScript.model_validate(script)
        self.assertEqual(ScriptLine(type='narration', text='Three years later.').strength, '微弱')
        self.assertEqual(ScriptLine(type='dialogue', text='AI lab').text, 'AI lab')

    def test_dangling_future_nonspoken_and_backwards_references_rejected(self):
        for change in ('future', 'dangling', 'missing_cue', 'speaker', 'backwards', 'nonspoken'):
            script = directed_script(); scene = script['scenes'][0]
            if change == 'future': scene['lines'][0]['performanceCue']['respondsTo'] = 4
            if change == 'dangling': scene['lines'][0]['performanceCue']['beatId'] = 'unknown'
            if change == 'missing_cue': del scene['lines'][1]['performanceCue']
            if change == 'speaker': scene['performancePlan']['characters'].pop()
            if change == 'backwards': scene['lines'][0]['performanceCue']['beatId'] = 'b2'
            if change == 'nonspoken': scene['lines'][0] = {'type': 'sfx', 'text': '雨声'}
            with self.subTest(change=change), self.assertRaises(ValidationError): DirectedDramaScript.model_validate(script)

    def test_native_compiler_uses_current_intent_and_never_future_beat(self):
        f = self.f; self.bind()
        result = f.service.preview(f.project.id, f.lines[2].id)
        self.assertEqual(result['context']['scene_performance']['status'], 'current')
        self.assertIn('再次确认', result['instruction'])
        self.assertNotIn('未来高潮才激烈哭喊', result['instruction'])
        self.assertNotIn('秘密揭露', result['instruction'])
        self.assertEqual(result['context']['reply_to']['line_id'], f.lines[1].id)
        self.assertEqual(result['tts_text'], f.lines[2].text_content)
        self.assertLessEqual(instruction_weight(result['instruction']), 2000)
        self.assertEqual(result['effective_strength'], '稍弱')

    def test_current_grounded_turn_releases_only_its_line(self):
        f = self.f; script = directed_script()
        script['scenes'][0]['lines'][2]['performanceCue'].update(turningPoint=True, evidence='他突然认出了她')
        self.bind(script)
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['effective_strength'], '强烈')
        self.assertEqual(f.service.prepare(f.project.id, f.lines[3].id)['effective_strength'], '微弱')
        script['scenes'][0]['lines'][2]['performanceCue']['evidence'] = '编造的剧情依据'
        self.bind(script)
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['effective_strength'], '稍弱')
        self.assertEqual(len(performance_issues(script, '他突然认出了她')), 1)

    def test_text_role_or_direction_changes_disable_old_plan(self):
        f = self.f
        for field, value in [('text_content', '改写后的话'), ('production_note', '改为正常回答'), ('role_id', f.other.id), ('strength_id', f.strengths[2].id)]:
            self.bind(); original = getattr(f.lines[0], field)
            setattr(f.lines[0], field, value); f.db.commit()
            result = f.service.prepare(f.project.id, f.lines[2].id)
            self.assertEqual(result['context']['scene_performance']['status'], 'stale')
            self.assertNotIn('整场表演', result['instruction'])
            setattr(f.lines[0], field, original); f.db.commit()

    def test_audio_status_changes_do_not_invalidate_design(self):
        f = self.f; self.bind()
        f.lines[0].status = 'done'; f.lines[0].audio_versions = [{'id': 'new-take'}]; f.db.commit()
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['context']['scene_performance']['status'], 'current')

    def test_insert_delete_reorder_and_adjacent_duplicate_titles(self):
        f = self.f; self.bind()
        inserted = LinePO(chapter_id=f.chapter.id, role_id=f.role.id, line_order=2, text_content='插入的对白', scene_title='站台')
        f.lines[1].line_order = 3; f.lines[2].line_order = 4; f.lines[3].line_order = 5
        f.db.add(inserted); f.db.commit()
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['context']['scene_performance']['status'], 'stale')
        f.db.delete(inserted); f.db.commit(); self.bind()
        f.lines[0].line_order = 8; f.db.commit()
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['context']['scene_performance']['status'], 'stale')
        f.lines[0].line_order = 1; f.db.commit(); self.bind()
        f.db.delete(f.lines[0]); f.db.commit()
        self.assertEqual(f.service.prepare(f.project.id, f.lines[2].id)['context']['scene_performance']['status'], 'stale')

    def test_duplicate_scene_names_keep_independent_context(self):
        f = self.f; script = directed_script(); entries = []
        roles = {f.role.id: f.role.name, f.other.id: f.other.name}
        for source, lines in [(script['scenes'][0]['lines'][:2], f.lines[:2]), (script['scenes'][0]['lines'][2:], f.lines[2:])]:
            scene = copy.deepcopy(script['scenes'][0]); scene['lines'] = source
            for raw in scene['lines']: raw['performanceCue']['respondsTo'] = None
            entries.append(bind_scene_performance(scene, lines, roles, '他突然认出了她'))
        save_chapter_performances(f.chapter, entries); f.db.commit()
        result = f.service.prepare(f.project.id, f.lines[2].id)
        self.assertEqual(result['context']['previous_lines'], [])
        self.assertEqual(result['context']['scene_performance']['scene_id'], entries[1]['id'])

    def test_budget_omits_whole_fields_and_rejects_long_base_before_request(self):
        context = {'当前人物': '林默', '共同表演基调': '自然', '作品背景': '背景'*300,
                   '整场表演': {'本句意图': '确认', '人物目标': '询问'}, '后文': '未来'*300}
        prompt, omitted = compile_context_instruction('自然回答', context, budget=450)
        self.assertLessEqual(instruction_weight(prompt), 450)
        self.assertIn('本句意图', prompt); self.assertIn('作品背景', omitted); self.assertIn('后文', omitted)
        with self.assertRaises(ValueError): compile_context_instruction('长指导'*1000, context, budget=450)

    def test_generation_and_repair_share_project_brief_without_an_extra_call(self):
        f = self.f; f.save(story_background='九十年代失散的兄妹', delivery_style='生活化，慢慢试探')
        service = ScriptDraftService(f.db); service.llm = SimpleNamespace(call_json=Mock(return_value=directed_script()))
        draft = service.generate(f.project, {}, [], '他突然认出了她')
        service.llm.call_json.assert_called_once()
        self.assertIn('九十年代失散', service.llm.call_json.call_args.args[1])
        self.assertIs(service.llm.call_json.call_args.kwargs['response_model'], DirectedDramaScript)
        service.llm.call_json.reset_mock()
        revised = service.revise_from_review(f.project, {}, [], '他突然认出了她', draft, {'issues': []})
        service.llm.call_json.assert_called_once()
        self.assertIn('生活化，慢慢试探', service.llm.call_json.call_args.args[1])
        self.assertEqual(revised['scenes'][0]['performancePlan'], draft['scenes'][0]['performancePlan'])

    def test_reviewer_cannot_pass_a_fabricated_turning_point_quote(self):
        f = self.f; service = ScriptReviewService(f.db)
        service.llm = SimpleNamespace(call_json=Mock(return_value={'passed': True, 'score': 95, 'summary': '通过', 'issues': []}))
        report = service.review(f.project, {}, [], '只有普通问答。', directed_script())
        self.assertFalse(report['passed']); self.assertLess(report['score'], 80)
        self.assertTrue(any(item['category'] == '表演转折依据' for item in report['issues']))

    def test_commit_binds_plan_to_real_line_ids_and_is_idempotent(self):
        f = self.f
        run = AdaptationRunPO(project_id=f.project.id, title='重逢', final_json=directed_script(), source_text='他突然认出了她')
        f.db.add(run); f.db.flush()
        session = ChatSessionPO(id='scene-commit-test', project_id=f.project.id, adaptation_run_id=run.id,
            chapter_id=f.chapter.id, current_stage='script_draft_ready', title='重逢', source_text='他突然认出了她')
        f.db.add(session); f.db.commit()
        from app.services.production.chapter_lifecycle import chapter_version
        result = DramaCommitService(f.db).commit_session(session.id, replace_chapter_lines=True,
                target_chapter_id=session.chapter_id, expected_version=chapter_version(f.db,session.chapter_id), confirm_replace=True)
        f.db.expire_all(); chapter = f.db.get(ChapterPO, result['chapter_id'])
        entry = chapter.performance_plan['scenes'][0]
        lines = list(f.db.scalars(select(LinePO).where(LinePO.chapter_id == chapter.id).order_by(LinePO.line_order)))
        self.assertEqual(entry['line_ids'], [line.id for line in lines])
        self.assertEqual(entry['cues'][str(lines[2].id)]['responds_to_line_id'], lines[1].id)
        self.assertEqual(f.service.prepare(f.project.id, lines[2].id)['context']['scene_performance']['status'], 'current')
        self.assertTrue(DramaCommitService(f.db).commit_session(session.id)['already_committed'])
        self.assertEqual(chapter.performance_plan['scenes'][0]['id'], entry['id'])
        second_run = AdaptationRunPO(project_id=f.project.id, title='续写', final_json=directed_script(), source_text='他突然认出了她')
        f.db.add(second_run); f.db.flush()
        second_session = ChatSessionPO(id='scene-append-test', project_id=f.project.id, adaptation_run_id=second_run.id,
            chapter_id=chapter.id, current_stage='script_draft_ready', title='续写', source_text='他突然认出了她')
        f.db.add(second_session); f.db.commit()
        DramaCommitService(f.db).commit_session(second_session.id, replace_chapter_lines=False,
            target_chapter_id=chapter.id, expected_version=chapter_version(f.db,chapter.id), confirm_replace=True)
        f.db.expire_all()
        all_lines = list(f.db.scalars(select(LinePO).where(LinePO.chapter_id == chapter.id).order_by(LinePO.line_order)))
        self.assertEqual([line.line_order for line in all_lines], list(range(1, 9)))
        self.assertEqual(len(chapter.performance_plan['scenes']), 2)
        self.assertEqual(chapter.performance_plan['scenes'][0]['id'], entry['id'])
        self.assertEqual(f.service.prepare(f.project.id, all_lines[2].id)['context']['scene_performance']['status'], 'current')


    def test_worker_records_used_scene_design_and_final_request(self):
        f = self.f; self.bind()
        f.test_worker_writes_success_failure_and_preparation_error_without_network()
        from app.models.po import TTSGenerationPO
        row = f.db.scalar(select(TTSGenerationPO).where(TTSGenerationPO.status == 'succeeded'))
        self.assertEqual(row.input_snapshot['prepared']['context']['scene_performance']['status'], 'current')
        instruction = row.request_json['payload']['input']['instruction']
        self.assertIn('再次确认', instruction)
        self.assertNotIn('未来高潮才激烈哭喊', instruction)

    def test_migration_adds_nullable_plan_without_rewriting_existing_chapter(self):
        engine = create_engine('sqlite:///:memory:')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)'))
            conn.execute(text('CREATE TABLE chapters (id INTEGER PRIMARY KEY, project_id INTEGER, title TEXT, text_content TEXT)'))
            conn.execute(text("INSERT INTO projects VALUES (1, '旧工程')"))
            conn.execute(text("INSERT INTO chapters VALUES (1, 1, '旧章节', '旧台本')"))
        apply_schema_migrations(engine); apply_schema_migrations(engine)
        with engine.connect() as conn:
            self.assertEqual(tuple(conn.execute(text('SELECT text_content, performance_plan FROM chapters WHERE id=1')).one()), ('旧台本', None))
            self.assertEqual(conn.execute(text('SELECT MAX(version) FROM schema_migrations')).scalar_one(), 12)
        engine.dispose()

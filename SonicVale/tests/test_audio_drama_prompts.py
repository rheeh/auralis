import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.core.prompts import get_audio_drama_adaptation_rules, get_prompt_str
from app.services.chapter_service import ChapterService
from app.services.script_draft_service import ScriptDraftService
from app.workflows.drama.schemas import DramaScript


class AudioDramaPromptTest(unittest.TestCase):
    def test_shared_rules_define_narration_gate(self):
        rules = get_audio_drama_adaptation_rules()
        self.assertIn("视觉无效信息 → 环境描写 → 动作描写", rules)
        self.assertIn("只有三种情况允许保留旁白", rules)
        self.assertIn("不超过15%", rules)
        prompt = get_prompt_str()
        self.assertNotIn("其余均为旁白内容", prompt)
        self.assertNotIn("100%完整保留", prompt)

    def test_narration_audit_detects_novel_like_script(self):
        script = {
            "scenes": [{
                "lines": [
                    {"type": "narration", "text": "他站在窗边，看着远处灰色的天空，想起很多年前发生的一切，那些回忆像潮水一样缓慢涌来。"},
                    {"type": "narration", "text": "房间里很安静，旧钟依旧走着。"},
                    {"type": "dialogue", "text": "你来了。"},
                ]
            }]
        }
        issues = ScriptDraftService._narration_issues(script)
        self.assertTrue(any("旁白字数占" in issue for issue in issues))
        self.assertTrue(any("连续旁白" in issue for issue in issues))

    def test_narration_audit_accepts_sound_led_scene(self):
        script = {
            "scenes": [{
                "lines": [
                    {"type": "sfx", "text": "雨点击窗，三次敲门"},
                    {"type": "dialogue", "text": "谁？"},
                    {"type": "dialogue", "text": "开门，是我。码头那封信不是我寄的，你先别出声。"},
                    {"type": "narration", "text": "门外的人换了。"},
                    {"type": "dialogue", "text": "你的声音不对。站到灯下，把手从口袋里拿出来。"},
                ]
            }]
        }
        self.assertEqual(ScriptDraftService._narration_issues(script), [])

    def test_auto_voice_assignment_forces_unique_voices(self):
        assignments = ChapterService._unique_voice_assignments(
            ["林澈", "旁白", "顾舟"],
            ["青年男声", "温柔女声", "冷峻男声"],
            {"林澈": "青年男声", "旁白": "青年男声", "顾舟": "不存在的音色"},
        )
        voice_names = [item["voice_name"] for item in assignments]
        self.assertEqual(len(voice_names), len(set(voice_names)))
        self.assertEqual(set(voice_names), {"青年男声", "温柔女声", "冷峻男声"})

    def test_empty_sound_tracks_receive_visible_scene_specific_prompts(self):
        script = {
            "scenes": [{
                "title": "雨夜码头",
                "lines": [
                    {"type": "sfx", "track": "sfx", "text": "", "soundPrompt": "", "productionNote": ""},
                    {"type": "bgm", "track": "bgm", "text": "", "soundPrompt": "", "productionNote": ""},
                ],
            }]
        }
        ScriptDraftService._ensure_sound_prompts(script)
        for line in script["scenes"][0]["lines"]:
            self.assertIn("雨夜码头", line["soundPrompt"])
            self.assertEqual(line["text"], line["soundPrompt"])

    def test_tts_text_moves_parenthetical_sound_into_audio_events(self):
        script = DramaScript.model_validate({
            "title": "电话",
            "characters": [{"name": "周正明"}],
            "scenes": [{
                "title": "通话",
                "lines": [{
                    "type": "dialogue",
                    "role_name": "周正明",
                    "text_content": "因为我想告诉你一件事。（电流嘶啦声）关于你父亲的事。",
                    "emotion_name": "冷静",
                    "strength_name": "中等",
                    "audio_events": [],
                }],
            }],
        }).model_dump()
        line = script["scenes"][0]["lines"][0]
        self.assertEqual(line["text"], "因为我想告诉你一件事。关于你父亲的事。")
        self.assertEqual(line["speaker"], "周正明")
        self.assertEqual(line["audioEvents"][0]["content"], "电流嘶啦声")
        self.assertNotIn("（", line["text"])

    def test_script_schema_rejects_parallel_dialogue_arrays_without_lines(self):
        with self.assertRaises(ValidationError):
            DramaScript.model_validate({
                "title": "深夜便利店",
                "characters": [{"name": "陈默"}],
                "scenes": [{
                    "title": "便利店",
                    "lines": [],
                    "dialogues": [{"character": "陈默", "text": "下班了。"}],
                }],
            })

    def test_script_generation_leaves_narration_repair_to_independent_reviewer(self):
        draft = {
            "title": "雨夜",
            "characters": [{"name": "林默"}],
            "scenes": [{
                "title": "门外",
                "lines": [
                    {"type": "narration", "text": "他站在窗边，看着远处灰色的天空，想起很多年前发生的一切。"},
                    {"type": "narration", "text": "房间里很安静，旧钟依旧走着。"},
                    {"type": "dialogue", "speaker": "林默", "text": "谁？"},
                ],
            }],
        }
        calls = []
        service = ScriptDraftService.__new__(ScriptDraftService)
        service.llm = SimpleNamespace(call_json=lambda *args, **kwargs: calls.append(kwargs) or draft)

        result = service.generate(
            SimpleNamespace(),
            {"title": "雨夜"},
            [{"name": "林默"}],
            "雨夜，林默听见敲门。",
        )

        self.assertEqual(len(calls), 1)
        self.assertTrue(ScriptDraftService._narration_issues(result))


if __name__ == "__main__":
    unittest.main()

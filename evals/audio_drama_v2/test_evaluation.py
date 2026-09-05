import unittest
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from run_evaluation import ALLOWED_MODELS, ROOT, EvaluationCancelled, evaluate_job, metrics, request
from app.workflows.drama.schemas import DramaScript


class EvaluationEvidenceTest(unittest.TestCase):
    def test_unauthorized_model_is_rejected_before_network_access(self):
        self.assertEqual(ALLOWED_MODELS, ("qwen3.8-27b", "kimi-k3"))
        with self.assertRaises(ValueError):
            request(None, "qwen-plus", "", "")

    def test_provider_cannot_silently_return_another_model(self):
        fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(model="qwen-plus")
        )))
        with self.assertRaises(ValueError):
            request(fake, "qwen3.8-27b", "", "")

    def test_metrics_expose_raw_contamination_before_schema_repairs_it(self):
        raw = {"title": "电话", "characters": [{"name": "甲"}], "scenes": [{"title": "门内", "lines": [
            {"type": "dialogue", "speaker": "甲", "text": "等一下。（敲门声）", "shouldSpeak": False},
        ]}]}
        before = metrics(raw)
        normalized = DramaScript.model_validate(raw).model_dump()
        after = metrics(normalized)
        self.assertEqual(before["tts_contamination"], 1)
        self.assertEqual(before["unvoiced_spoken_lines"], 1)
        self.assertEqual(after["tts_contamination"], 0)
        self.assertEqual(after["audio_event_count"], 1)

    def test_consecutive_narration_is_counted_across_sound_only_rows(self):
        raw = {"scenes": [{"lines": [
            {"type": "narration", "text": "三天后。"},
            {"type": "sfx", "soundPrompt": "风声"},
            {"type": "narration", "text": "旧屋里没有人。"},
        ]}]}
        result = metrics(raw)
        self.assertEqual(result["consecutive_narrations"], 1)
        self.assertEqual(result["empty_sound_prompts"], 0)

    def test_quota_errors_make_one_request_and_stop_the_shared_batch(self):
        for code, status in [("Arrearage", 400), ("AllocationQuota.FreeTierOnly", 400),
                             ("insufficient_quota", 429), ("AllocationQuota.Exhausted", 429)]:
            with self.subTest(code=code), patch("run_evaluation.time.sleep") as sleep:
                error = RuntimeError("response_format not allowed")
                error.status_code = status
                error.body = {"error": {"code": code}}
                completion = SimpleNamespace(create=unittest.mock.Mock(side_effect=error))
                client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
                stopped = threading.Event()
                with self.assertRaises(RuntimeError) as raised:
                    request(client, "qwen3.8-27b", "rules", "input", stop_event=stopped)
                self.assertIs(raised.exception, error)
                self.assertTrue(stopped.is_set())
                with self.assertRaises(EvaluationCancelled):
                    request(client, "qwen3.8-27b", "rules", "next input", stop_event=stopped)
                self.assertEqual(completion.create.call_count, 1)
                sleep.assert_not_called()

    def test_transient_rate_limit_retries_identical_request_once(self):
        error = RuntimeError("temporary rate limit")
        error.status_code = 429
        error.code = "rate_limit_exceeded"
        response = SimpleNamespace(model="qwen3.8-27b", choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop")], usage=None)
        completion = SimpleNamespace(create=unittest.mock.Mock(side_effect=[error, response]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        with patch("run_evaluation.time.sleep") as sleep:
            result = request(client, "qwen3.8-27b", "rules", "input")
        self.assertEqual(result["raw_response"], '{"ok":true}')
        self.assertEqual(completion.create.call_count, 2)
        self.assertEqual(completion.create.call_args_list[0], completion.create.call_args_list[1])
        sleep.assert_called_once()

    def test_worker_stops_before_constructing_next_client_after_quota_failure(self):
        sample = {"id": "SAMPLE", "title": "测试", "source_text": "门铃响了。", "characters": [], "recommended_max_scenes": 1}
        settings = {"api_key": "unit-test-placeholder", "base_url": "https://example.test/v1", "model": "qwen3.8-27b", "skip_judge": True}
        error = RuntimeError("free quota exhausted")
        error.status_code = 400
        error.code = "AllocationQuota.FreeTierOnly"
        completion = SimpleNamespace(create=unittest.mock.Mock(side_effect=error))
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion), close=lambda: None)
        stopped = threading.Event()
        with tempfile.TemporaryDirectory() as tmp, patch("run_evaluation.OpenAI", return_value=client) as factory:
            first = evaluate_job((sample, 1, "a_current", "rules"), settings, Path(tmp), stopped)
            second = evaluate_job((sample, 1, "b_fact_locked", "rules"), settings, Path(tmp), stopped)
            self.assertEqual(first["status"], "failed")
            self.assertTrue(first["error"]["stop_batch"])
            self.assertEqual(second["status"], "cancelled")
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
            self.assertEqual(completion.create.call_count, 1)

    def test_v1_cli_is_retired_before_it_creates_an_output_or_reads_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "must-not-exist"
            result = subprocess.run([sys.executable, str(ROOT / "evals/audio_drama_v1/run_evaluation.py"),
                                     "--config-dir", str(Path(tmp) / "missing-config"), "--output-dir", str(output)],
                                    capture_output=True, text=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("请改用 evals/audio_drama_v2/run_evaluation.py", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

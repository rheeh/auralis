#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT / "SonicVale"
DATASET_PATH = HERE / "dataset.json"


class EvalJudgment(BaseModel):
    source_fidelity: int = Field(ge=1, le=5)
    audible_comprehension: int = Field(ge=1, le=5)
    character_dialogue: int = Field(ge=1, le=5)
    narration_control: int = Field(ge=1, le=5)
    production_readiness: int = Field(ge=1, le=5)
    human_edit_cost: int = Field(ge=1, le=5)
    critical_fact_errors: list[str] = Field(default_factory=list)
    prohibited_inventions: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    rationale: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Auralis audio-drama A/B evaluation.")
    parser.add_argument("--config-dir", default=str(ROOT / ".local-data"))
    parser.add_argument("--provider-id", type=int, default=1)
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--samples", help="Comma-separated sample ids; defaults to all samples")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def weighted_score(judgment: dict[str, Any]) -> float:
    weights = {
        "source_fidelity": 0.25,
        "audible_comprehension": 0.20,
        "character_dialogue": 0.15,
        "narration_control": 0.15,
        "production_readiness": 0.15,
        "human_edit_cost": 0.10,
    }
    return round(sum(float(judgment[name]) * weight for name, weight in weights.items()), 3)


def calibrate_judgment(judgment: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic rubric caps while preserving the model's qualitative review."""
    calibrated = dict(judgment)
    ratio = float(metrics.get("narration_ratio") or 0)
    if ratio > 0.18:
        calibrated["narration_control"] = min(int(calibrated["narration_control"]), 2)
    elif ratio > 0.15:
        calibrated["narration_control"] = min(int(calibrated["narration_control"]), 3)
    if metrics.get("consecutive_narrations"):
        calibrated["narration_control"] = min(int(calibrated["narration_control"]), 2)
    elif metrics.get("long_narrations"):
        calibrated["narration_control"] = min(int(calibrated["narration_control"]), 3)
    if metrics.get("tts_text_contamination"):
        calibrated["production_readiness"] = min(int(calibrated["production_readiness"]), 2)
    if calibrated.get("critical_fact_errors"):
        calibrated["source_fidelity"] = min(int(calibrated["source_fidelity"]), 2)
    if calibrated.get("prohibited_inventions"):
        calibrated["source_fidelity"] = min(int(calibrated["source_fidelity"]), 1)
    return calibrated


def structural_metrics(script: dict[str, Any]) -> dict[str, Any]:
    counts = {"dialogue": 0, "narration": 0, "sfx": 0, "bgm": 0}
    spoken_chars = 0
    narration_chars = 0
    consecutive_narrations = 0
    long_narrations = 0
    tts_text_contamination = 0
    bracket_pattern = re.compile(r"[()（）\[\]【】]")

    for scene in script.get("scenes", []):
        previous_narration = False
        for line in scene.get("lines", []):
            line_type = str(line.get("type") or "dialogue").lower()
            if line_type not in counts:
                continue
            counts[line_type] += 1
            text = str(line.get("text") or "")
            compact = "".join(text.split())
            if line_type in {"dialogue", "narration"}:
                spoken_chars += len(compact)
                tts_text_contamination += int(bool(bracket_pattern.search(text)))
            if line_type == "narration":
                narration_chars += len(compact)
                long_narrations += int(len(compact) > 45)
                consecutive_narrations += int(previous_narration)
                previous_narration = True
            else:
                previous_narration = False

    line_count = sum(counts.values())
    return {
        "scene_count": len(script.get("scenes", [])),
        "line_count": line_count,
        "line_type_counts": counts,
        "spoken_chars": spoken_chars,
        "narration_chars": narration_chars,
        "narration_ratio": round(narration_chars / spoken_chars, 4) if spoken_chars else 0.0,
        "consecutive_narrations": consecutive_narrations,
        "long_narrations": long_narrations,
        "tts_text_contamination": tts_text_contamination,
    }


def baseline_prompt(sample: dict[str, Any], rules: str) -> tuple[str, str]:
    system_prompt = "\n\n".join([
        "你是广播剧编剧。请一次性把小说原文改编为可制作的广播剧脚本，不执行分阶段解析、独立审查或返修。",
        rules,
        "dialogue/narration 的 shouldSpeak=true；sfx/bgm 的 shouldSpeak=false。",
        "每个场景把所有内容按播放顺序统一写入 scenes[].lines。",
        "只返回符合响应结构的 JSON。",
    ])
    user_prompt = "\n\n".join([
        f"建议最多场景数：{sample['recommended_max_scenes']}",
        f"小说原文：\n{sample['source_text']}",
    ])
    return system_prompt, user_prompt


def judge_prompt(
    sample: dict[str, Any], script: dict[str, Any], metrics: dict[str, Any]
) -> tuple[str, str]:
    system_prompt = """
你是独立的广播剧质量评审。你不知道候选脚本来自哪个方案，也不得猜测方案。
严格按 1 到 5 分评分：原文忠实度25%、听觉可理解性20%、角色一致性与对白自然度15%、
广播剧规范与旁白控制15%、可制作性15%、人工修改成本10%。人工修改成本分数越高表示修改越少。
评分必须有区分度：3 分表示达到可用中位水平；4 分表示只有少量明确问题；5 分只用于几乎无需修改的卓越输出，不能因为结构合法就给满分。
逐条核对 required_facts 和 prohibited_inventions；检查角色是否为了向听众解释而机械复述双方已知信息。
严重事实错误和禁编内容必须单独列出，不能被流畅度抵消。客观结构指标是已计算证据，必须纳入评分。
只返回符合响应结构的 JSON。
""".strip()
    payload = {
        "source_text": sample["source_text"],
        "characters": sample["characters"],
        "required_facts": sample["required_facts"],
        "prohibited_inventions": sample["prohibited_inventions"],
        "audio_challenges": sample["audio_challenges"],
        "expected_transformations": sample["expected_transformations"],
        "scoring_focus": sample["scoring_focus"],
        "objective_structural_metrics": metrics,
        "candidate_script": script,
    }
    return system_prompt, json.dumps(payload, ensure_ascii=False)


def sanitize_error(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "code": getattr(exc, "code", None),
        "message": str(exc)[:500],
    }


def main() -> None:
    raise SystemExit("旧版评测入口已退役，拒绝联网执行。请改用 evals/audio_drama_v2/run_evaluation.py；历史结果保持原样。")
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AURALIS_CONFIG_DIR"] = str(Path(args.config_dir).resolve())
    sys.path.insert(0, str(BACKEND))

    from app.core.prompts import get_audio_drama_adaptation_rules
    from app.db.database import SessionLocal
    from app.models.po import ProjectPO
    from app.repositories.llm_provider_repository import LLMProviderRepository
    from app.services.role_draft_service import RoleDraftService
    from app.services.script_draft_service import ScriptDraftService
    from app.services.script_review_service import ScriptReviewService
    from app.services.source_parser_service import SourceParserService
    from app.services.workflow_llm_service import WorkflowLLMService
    from app.workflows.drama.schemas import DramaScript

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    requested = set(args.samples.split(",")) if args.samples else None
    samples = [sample for sample in dataset["samples"] if not requested or sample["id"] in requested]
    if requested and {sample["id"] for sample in samples} != requested:
        raise SystemExit("unknown sample id in --samples")

    results_path = output_dir / "results.json"
    existing = json.loads(results_path.read_text(encoding="utf-8")) if args.resume and results_path.exists() else []
    completed = {(item["sample_id"], item["run_number"], item["variant"]) for item in existing}
    results = existing

    db = SessionLocal()
    provider = LLMProviderRepository(db).get_by_id(args.provider_id)
    if not provider:
        raise SystemExit(f"provider {args.provider_id} not found")
    evaluation_params: dict[str, Any] = {
        "temperature": args.temperature,
        "top_p": args.top_p,
    }
    if not args.enable_thinking:
        evaluation_params["extra_body"] = {"enable_thinking": False}
    provider.custom_params = json.dumps(evaluation_params)
    project = ProjectPO(
        id=-1000,
        name="Auralis Evaluation",
        llm_provider_id=provider.id,
        llm_model=args.model,
        tts_provider_id=None,
    )
    llm = WorkflowLLMService(db)
    parser = SourceParserService(db)
    role_drafter = RoleDraftService(db)
    script_drafter = ScriptDraftService(db)
    reviewer = ScriptReviewService(db)
    rules = get_audio_drama_adaptation_rules()

    run_config = {
        "evaluation_id": output_dir.name,
        "started_at": now_iso(),
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "dataset_sha256": sha256(DATASET_PATH),
        "provider": provider.name,
        "provider_id": provider.id,
        "model": args.model,
        "sampling": {"temperature": args.temperature, "top_p": args.top_p},
        "thinking_enabled": args.enable_thinking,
        "runs_per_variant": args.runs,
        "sample_ids": [sample["id"] for sample in samples],
        "variants": ["baseline_one_shot", "auralis_workflow"],
        "judge": "same-model blinded LLM-as-judge",
        "token_usage": "not available from current LLMEngine abstraction",
        "git_commit": os.popen(f"git -C '{ROOT}' rev-parse HEAD").read().strip(),
    }
    write_json(output_dir / "run_config.json", run_config)

    try:
        total = len(samples) * args.runs * 2
        done = len(completed)
        for sample in samples:
            for run_number in range(1, args.runs + 1):
                variants = ["baseline_one_shot", "auralis_workflow"]
                random.Random(f"{sample['id']}-{run_number}").shuffle(variants)
                for variant in variants:
                    key = (sample["id"], run_number, variant)
                    if key in completed:
                        continue
                    started = time.perf_counter()
                    stage_seconds: dict[str, float] = {}
                    record: dict[str, Any] = {
                        "sample_id": sample["id"],
                        "sample_title": sample["title"],
                        "category": sample["category"],
                        "difficulty": sample["difficulty"],
                        "run_number": run_number,
                        "variant": variant,
                        "model": args.model,
                        "status": "running",
                        "started_at": now_iso(),
                    }
                    try:
                        if variant == "baseline_one_shot":
                            system_prompt, user_prompt = baseline_prompt(sample, rules)
                            tick = time.perf_counter()
                            script = llm.call_json(
                                project,
                                user_prompt,
                                system_prompt=system_prompt,
                                response_model=DramaScript,
                                schema_name="baseline_drama_script",
                            )
                            stage_seconds["generation"] = round(time.perf_counter() - tick, 3)
                            workflow_meta = {"repair_applied": False, "review_score": None}
                        else:
                            tick = time.perf_counter()
                            parsed = parser.parse(project, sample["source_text"], "保留事实与人物动机，完成声音化改编。")
                            stage_seconds["source_parse"] = round(time.perf_counter() - tick, 3)
                            tick = time.perf_counter()
                            roles = role_drafter.generate(project, parsed)
                            stage_seconds["role_draft"] = round(time.perf_counter() - tick, 3)
                            tick = time.perf_counter()
                            script = script_drafter.generate(project, parsed, roles, sample["source_text"])
                            stage_seconds["script_draft"] = round(time.perf_counter() - tick, 3)
                            tick = time.perf_counter()
                            initial_review = reviewer.review(
                                project,
                                parsed,
                                roles,
                                sample["source_text"],
                                script,
                                script_drafter._narration_issues(script),
                            )
                            stage_seconds["initial_review"] = round(time.perf_counter() - tick, 3)
                            repair_applied = not initial_review.get("passed", False)
                            final_review = initial_review
                            if repair_applied:
                                tick = time.perf_counter()
                                script = script_drafter.revise_from_review(
                                    project, parsed, roles, sample["source_text"], script, initial_review
                                )
                                stage_seconds["repair"] = round(time.perf_counter() - tick, 3)
                                tick = time.perf_counter()
                                final_review = reviewer.review(
                                    project,
                                    parsed,
                                    roles,
                                    sample["source_text"],
                                    script,
                                    script_drafter._narration_issues(script),
                                )
                                stage_seconds["final_review"] = round(time.perf_counter() - tick, 3)
                            workflow_meta = {
                                "repair_applied": repair_applied,
                                "initial_review_score": initial_review.get("score"),
                                "review_score": final_review.get("score"),
                                "review_passed": final_review.get("passed"),
                                "review_issue_count": len(final_review.get("issues") or []),
                            }

                        metrics = structural_metrics(script)
                        tick = time.perf_counter()
                        judge_system, judge_user = judge_prompt(sample, script, metrics)
                        raw_judgment = llm.call_json(
                            project,
                            judge_user,
                            system_prompt=judge_system,
                            response_model=EvalJudgment,
                            schema_name="blind_audio_drama_evaluation",
                        )
                        stage_seconds["blind_judge"] = round(time.perf_counter() - tick, 3)
                        judgment = calibrate_judgment(raw_judgment, metrics)
                        record.update({
                            "status": "completed",
                            "script": script,
                            "structural_metrics": metrics,
                            "raw_judgment": raw_judgment,
                            "judgment": judgment,
                            "weighted_score": weighted_score(judgment),
                            "workflow_meta": workflow_meta,
                        })
                    except Exception as exc:
                        record.update({"status": "failed", "error": sanitize_error(exc)})
                    record["stage_seconds"] = stage_seconds
                    record["latency_seconds"] = round(time.perf_counter() - started, 3)
                    record["finished_at"] = now_iso()
                    results.append(record)
                    write_json(results_path, results)
                    raw_name = f"{sample['id'].lower()}-r{run_number}-{variant}.json"
                    write_json(output_dir / "raw" / raw_name, record)
                    done += 1
                    print(
                        f"[{done}/{total}] {sample['id']} r{run_number} {variant}: "
                        f"{record['status']} {record['latency_seconds']:.1f}s",
                        flush=True,
                    )
    finally:
        db.close()

    columns = [
        "sample_id", "run_number", "variant", "model", "status", "weighted_score",
        "source_fidelity", "audible_comprehension", "character_dialogue", "narration_control",
        "production_readiness", "human_edit_cost", "critical_fact_errors", "prohibited_inventions",
        "narration_ratio", "consecutive_narrations", "long_narrations", "tts_text_contamination",
        "latency_seconds", "repair_applied", "review_score", "review_passed", "notes",
    ]
    with (output_dir / "scorecard.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in results:
            judgment = item.get("judgment") or {}
            metrics = item.get("structural_metrics") or {}
            meta = item.get("workflow_meta") or {}
            writer.writerow({
                "sample_id": item["sample_id"],
                "run_number": item["run_number"],
                "variant": item["variant"],
                "model": item["model"],
                "status": item["status"],
                "weighted_score": item.get("weighted_score"),
                "source_fidelity": judgment.get("source_fidelity"),
                "audible_comprehension": judgment.get("audible_comprehension"),
                "character_dialogue": judgment.get("character_dialogue"),
                "narration_control": judgment.get("narration_control"),
                "production_readiness": judgment.get("production_readiness"),
                "human_edit_cost": judgment.get("human_edit_cost"),
                "critical_fact_errors": len(judgment.get("critical_fact_errors") or []),
                "prohibited_inventions": len(judgment.get("prohibited_inventions") or []),
                "narration_ratio": metrics.get("narration_ratio"),
                "consecutive_narrations": metrics.get("consecutive_narrations"),
                "long_narrations": metrics.get("long_narrations"),
                "tts_text_contamination": metrics.get("tts_text_contamination"),
                "latency_seconds": item.get("latency_seconds"),
                "repair_applied": meta.get("repair_applied"),
                "review_score": meta.get("review_score"),
                "review_passed": meta.get("review_passed"),
                "notes": (item.get("error") or {}).get("message", ""),
            })
    print(f"results: {results_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reproducible prompt-only comparison; reads provider credentials without DB writes."""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import random
import re
import sqlite3
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ALLOWED_MODELS = ("qwen3.8-27b", "kimi-k3")
sys.path.insert(0, str(ROOT / "SonicVale"))
from app.core.tts_guidance import EMOTION_NAMES, STRENGTH_NAMES
from app.core.llm_engine import LLMEngine
from app.workflows.drama.schemas import DramaScript


class Judgment(BaseModel):
    source_fidelity: int = Field(ge=1, le=5)
    audible_comprehension: int = Field(ge=1, le=5)
    dialogue_subtext: int = Field(ge=1, le=5)
    production_readiness: int = Field(ge=1, le=5)
    critical_fact_errors: list[str]
    invented_facts: list[str]
    evidence: list[str]
    revision_needed: list[str]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def metrics(script: dict) -> dict:
    counts = {name: 0 for name in ("dialogue", "narration", "sfx", "bgm")}
    spoken_chars = narration_chars = contaminated = unvoiced_spoken = empty_sounds = 0
    max_spoken_length = notes = consecutive = long_narrations = events = 0
    opening_sound_scenes = 0
    for scene in script.get("scenes", []):
        lines = scene.get("lines", [])
        if lines and (lines[0].get("type") in {"sfx", "bgm"} or lines[0].get("audioEvents")):
            opening_sound_scenes += 1
        previous_narration = False
        for line in lines:
            kind = line.get("type", "dialogue")
            if kind not in counts:
                continue
            counts[kind] += 1
            text = str(line.get("text") or "")
            events += len(line.get("audioEvents") or [])
            if kind in {"dialogue", "narration"}:
                n = len(re.sub(r"\s", "", text))
                spoken_chars += n
                max_spoken_length = max(max_spoken_length, n)
                contaminated += int(bool(re.search(r"[()（）\[\]【】]", text)))
                unvoiced_spoken += int(line.get("shouldSpeak") is False)
                notes += bool(line.get("productionNote"))
                if kind == "narration":
                    narration_chars += n
                    long_narrations += int(n > 45)
                    consecutive += int(previous_narration)
                previous_narration = kind == "narration"
            elif kind in {"sfx", "bgm"}:
                empty_sounds += not bool(line.get("soundPrompt") or text)
    return {
        "scene_count": len(script.get("scenes", [])), "line_counts": counts,
        "spoken_chars": spoken_chars, "narration_ratio": round(narration_chars / max(spoken_chars, 1), 4),
        "consecutive_narrations": consecutive, "long_narrations": long_narrations,
        "tts_contamination": contaminated, "unvoiced_spoken_lines": unvoiced_spoken,
        "empty_sound_prompts": empty_sounds, "max_spoken_line_chars": max_spoken_length,
        "actor_notes": notes, "audio_event_count": events, "opening_sound_scenes": opening_sound_scenes,
    }


def prompt_variants() -> dict[str, str]:
    a = (HERE / "prompts/a_current.txt").read_text().strip()
    b = (HERE / "prompts/b_fact_locked.txt").read_text().strip()
    c = b + "\n\n" + (HERE / "prompts/c_director_example_suffix.txt").read_text().strip()
    variants = {"a_current": a, "b_fact_locked": b, "c_director_example": c}
    final = HERE / "prompts/d_fact_audited.txt"
    if final.exists():
        variants["d_fact_audited"] = final.read_text().strip()
    return variants


def user_prompt(sample: dict) -> str:
    # Rubric/required facts intentionally withheld from all generators.
    payload = {
        "用户要求": "悬疑/都市广播剧；保留事实和动机，克制自然，能直接配音和后期制作。",
        "最多场景数": sample["recommended_max_scenes"],
        "已确认角色": sample["characters"], "小说原文": sample["source_text"],
        "emotion候选": EMOTION_NAMES, "strength候选": STRENGTH_NAMES,
        "response_schema": DramaScript.model_json_schema(),
    }
    return json.dumps(payload, ensure_ascii=False)


class EvaluationCancelled(RuntimeError):
    pass


def provider_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    body = getattr(error, "body", None)
    if not code and isinstance(body, dict):
        details = body.get("error", body)
        if isinstance(details, dict):
            code = details.get("code")
    value = str(code or "")
    return value if re.fullmatch(r"[\w.-]{1,100}", value) else ""


def stops_batch(error: Exception) -> bool:
    code = provider_error_code(error).lower()
    return (
        LLMEngine._permanent_provider_failure(error)
        or getattr(error, "status_code", None) in {401, 402, 403}
        or code in {"modelnotfound", "invalidmodel"}
        # Allocation/billing quota errors are not temporary rate-limit signals.
        or any(term in code for term in ("quota", "arrearage", "balance", "billing", "payment"))
    )


def request(client: OpenAI, model: str, system: str, user: str, *, judging: bool = False,
            stop_event: threading.Event | None = None) -> dict:
    if model not in ALLOWED_MODELS:
        raise ValueError("Only explicitly authorized qwen3.8-27b or kimi-k3 may be requested; no fallback")
    started = time.perf_counter()
    for attempt in range(2):
        if stop_event is not None and stop_event.is_set():
            raise EvaluationCancelled("Batch stopped before another provider request")
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"}, temperature=0 if judging else 0.3,
                top_p=0.8, max_tokens=5000, extra_body={"enable_thinking": False},
            )
            break
        except Exception as error:
            if stops_batch(error):
                if stop_event is not None:
                    stop_event.set()
                raise
            if attempt == 1 or not LLMEngine._retryable_error(error):
                raise
            if stop_event is not None:
                if stop_event.wait(0.5):
                    raise EvaluationCancelled("Batch stopped before retry") from error
            else:
                time.sleep(0.5)
    if completion.model != model:
        if stop_event is not None:
            stop_event.set()
        raise ValueError("Provider returned a different model; refusing implicit fallback")
    content = completion.choices[0].message.content or ""
    return {
        "raw_response": content, "finish_reason": completion.choices[0].finish_reason,
        "seconds": round(time.perf_counter() - started, 3),
        "usage": completion.usage.model_dump() if completion.usage else None,
        "response_model": completion.model,
    }


def judge_payload(sample: dict, script: dict, structural: dict) -> tuple[str, str]:
    system = (
        "你是独立广播剧评审，不知道候选提示词策略，也不要猜测。原文是唯一事实依据。"
        "按1到5分评价：事实与结尾边界；听众仅靠真实可发出的声音理解证据、空间、因果；"
        "自然对白、角色意图与潜台词；分轨可制作性。3分为可用但有明显修改，4分为少量修改，5分为几乎无需修改。"
        "productionNote、标题和角色表只给制作人员看，不能当成听众已经获知的事实。"
        "普通合情理的口语化不算新编事实，但不许增添关键证据、身份、动机或结果。"
        "不因零旁白或音效数量多而加分，不能把压低旁白率当成最高目标。"
        "指出具体句子和遗漏事实，不能空泛表扬；只返回符合给定schema的JSON。"
    )
    user = json.dumps({
        "source": sample["source_text"], "required_facts": sample["required_facts"],
        "prohibited_inventions": sample["prohibited_inventions"],
        "audio_challenges": sample["audio_challenges"], "candidate": script,
        "raw_structural_metrics": structural, "response_schema": Judgment.model_json_schema(),
    }, ensure_ascii=False)
    return system, user


def evaluate_job(job: tuple, settings: dict, output: Path, stop_event: threading.Event | None = None) -> dict:
    sample, repetition, variant, system = job
    record_path = output / "raw" / f"{sample['id']}-r{repetition}-{variant}.json"
    previous = None
    if record_path.exists():
        previous = json.loads(record_path.read_text())
        if previous.get("status") == "completed" or (settings.get("skip_judge") and previous.get("status") == "generated"):
            return previous
    record = {
        "sample_id": sample["id"], "title": sample["title"], "repetition": repetition,
        "variant": variant, "status": "started", "started_at": datetime.now(timezone.utc).isoformat(),
        "system_prompt_sha256": digest(system), "user_prompt_sha256": digest(user_prompt(sample)),
    }
    if stop_event is not None and stop_event.is_set():
        record["status"] = "cancelled"
        write_json(record_path, record)
        return record
    # Credentials remain only in process memory, never in saved settings or error text.
    client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"], timeout=180, max_retries=0)
    try:
        generated = (previous or {}).get("generation") or request(client, settings["model"], system, user_prompt(sample), stop_event=stop_event)
        record["generation"] = generated
        write_json(record_path, record)
        raw = json.loads(generated["raw_response"])
        record["raw_metrics"] = metrics(raw)
        validated = DramaScript.model_validate(raw).model_dump(mode="json")
        record["script"] = validated
        record["normalized_metrics"] = metrics(validated)
        if settings.get("skip_judge"):
            record["status"] = "generated"
            write_json(record_path, record)
            return record
        system_j, user_j = judge_payload(sample, raw, record["raw_metrics"])
        judged = request(client, settings["model"], system_j, user_j, judging=True, stop_event=stop_event)
        record["judge_response"] = judged
        assessment = Judgment.model_validate_json(judged["raw_response"]).model_dump()
        record["judgment"] = assessment
        # Keep uncapped score visible. Fact errors block a recommendation independently.
        record["weighted_score"] = round(
            assessment["source_fidelity"] * .35 + assessment["audible_comprehension"] * .25
            + assessment["dialogue_subtext"] * .25 + assessment["production_readiness"] * .15, 3
        )
        record["fact_gate_passed"] = not (assessment["critical_fact_errors"] or assessment["invented_facts"])
        record["status"] = "completed"
    except Exception as error:
        record["status"] = "cancelled" if isinstance(error, EvaluationCancelled) else "failed"
        # Provider error codes identify quota/parameter failures without retaining
        # request payloads, headers, secrets, or unsanitized exception strings.
        record["error"] = {"type": type(error).__name__, "status_code": getattr(error, "status_code", None),
                           "provider_code": provider_error_code(error), "stop_batch": stops_batch(error)}
        if record["error"]["stop_batch"] and stop_event is not None:
            stop_event.set()
    finally:
        client.close()
    write_json(record_path, record)
    return record


def summarize(records: list[dict], output: Path) -> None:
    write_json(output / "results.json", sorted(records, key=lambda x: (x["sample_id"], x["repetition"], x["variant"])))
    summary = []
    for variant in sorted({r["variant"] for r in records}):
        group = [r for r in records if r["variant"] == variant and r["status"] in {"completed", "generated"}]
        judged_group = [r for r in group if "weighted_score" in r]
        summary.append({
            "variant": variant, "completed": len(group),
            "mean_weighted_score": round(statistics.mean(r["weighted_score"] for r in judged_group), 3) if judged_group else None,
            "fact_gate_passed": sum(r["fact_gate_passed"] for r in judged_group) if judged_group else None,
            "mean_narration_ratio": round(statistics.mean(r["raw_metrics"]["narration_ratio"] for r in group), 4) if group else None,
            "raw_tts_contamination": sum(r["raw_metrics"]["tts_contamination"] for r in group),
            "generation_seconds_mean": round(statistics.mean(r["generation"]["seconds"] for r in group), 1) if group else None,
        })
    write_json(output / "summary.json", summary)
    with (output / "scorecard.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "repetition", "variant", "status", "weighted_score", "fact_gate_passed", "narration_ratio", "raw_tts_contamination"])
        writer.writeheader()
        for r in records:
            writer.writerow({**{k: r.get(k) for k in ["sample_id", "repetition", "variant", "status", "weighted_score", "fact_gate_passed"]},
                             "narration_ratio": r.get("raw_metrics", {}).get("narration_ratio"),
                             "raw_tts_contamination": r.get("raw_metrics", {}).get("tts_contamination")})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config-dir", default=str(ROOT / ".local-data"))
    p.add_argument("--provider-id", type=int, default=1)
    p.add_argument("--model", choices=ALLOWED_MODELS, default="qwen3.8-27b")
    p.add_argument("--skip-judge", action="store_true", help="Save writer outputs only; no extra self-evaluation calls")
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--samples", default="AD-001,AD-006,DEMO-001")
    p.add_argument("--variants", default="a_current,b_fact_locked,c_director_example")
    p.add_argument("--output", default=str(HERE / "runs/2026-09-05-qwen3.8-27b-demo"))
    args = p.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    dataset_text = (HERE / "dataset.json").read_text()
    samples = [s for s in json.loads(dataset_text)["samples"] if s["id"] in args.samples.split(",")]
    if len(samples) != len(set(args.samples.split(","))):
        p.error("unknown sample id")
    db_path = Path(args.config_dir).resolve() / "app_test.db"
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        row = db.execute("SELECT api_key,api_base_url FROM llm_provider WHERE id=?", (args.provider_id,)).fetchone()
    if not row or not row[0]:
        p.error("configured provider/key is missing")
    settings = {"api_key": row[0], "base_url": row[1], "model": args.model, "skip_judge": args.skip_judge}
    available = prompt_variants()
    requested = args.variants.split(",")
    if not set(requested).issubset(available):
        p.error("unknown prompt variant")
    variants = {key: available[key] for key in requested}
    config = {
        "model": args.model, "provider_id": args.provider_id, "sampling": {"temperature": .3, "top_p": .8, "max_tokens": 5000, "enable_thinking": False},
        "judge": "disabled; writer only" if args.skip_judge else "same-model, separate blinded calls; no human listening panel", "judge_temperature": None if args.skip_judge else 0,
        "sample_ids": [s["id"] for s in samples], "repetitions": args.repetitions,
        "dataset_sha256": digest(dataset_text), "prompt_sha256": {k: digest(v) for k, v in variants.items()},
        "scope": "draft prompt only; identical source, confirmed characters, model, schema and sampling; no parser/reviewer repair",
    }
    existing_config = output / "run_config.json"
    if existing_config.exists() and json.loads(existing_config.read_text()) != config:
        p.error("output already contains a different frozen run; choose a new output directory")
    write_json(existing_config, config)
    (output / "dataset.json").write_text(dataset_text, encoding="utf-8")
    for key, value in variants.items():
        (output / f"{key}.txt").write_text(value + "\n", encoding="utf-8")
    jobs = [(s, rep, v, text) for s in samples for rep in range(1, args.repetitions + 1) for v, text in variants.items()]
    random.Random(20260905).shuffle(jobs)
    records = []
    stop_event = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(evaluate_job, job, settings, output, stop_event) for job in jobs]
        for future in concurrent.futures.as_completed(pending):
            if future.cancelled():
                continue
            record = future.result()
            records.append(record)
            summarize(records, output)
            print(f"[{len(records)}/{len(jobs)}] {record['sample_id']} r{record['repetition']} {record['variant']}: {record['status']} score={record.get('weighted_score')} fact_gate={record.get('fact_gate_passed')}", flush=True)
            if stop_event.is_set():
                cancelled = sum(f.cancel() for f in pending if not f.done())
                print(f"Provider unavailable; cancelled {cancelled} queued calls. No model fallback.", flush=True)
    print(f"Saved {len(records)} records to {output}", flush=True)


if __name__ == "__main__":
    main()

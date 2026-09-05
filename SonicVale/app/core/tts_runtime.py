# app/tts_worker.py
import asyncio
from fastapi import FastAPI

from app.core.ws_manager import manager
from app.db.database import SessionLocal
from app.services.factory import get_voice_service, get_emotion_service, get_strength_service
from app.services.factory import get_multi_emotion_voice_service
from app.services.factory import get_line_service, get_role_service, get_project_service
from app.models.po import ChatSessionPO
from app.core.tts_guidance import emotion_text_to_vector
from app.services.audio_task_service import AudioTaskService
from app.services.production_configuration import effective_provider_id
from app.workflows.drama.events import WorkflowEventPublisher

TTS_TIMEOUT_SECONDS = 1200  # 可调
async def tts_worker(app: FastAPI):
    q = app.state.tts_queue
    ex = app.state.tts_executor
    while True:
        item = await q.get()
        if isinstance(item, dict):
            project_id = item["project_id"]
            session_id = item.get("session_id")
            task_id = item.get("task_id")
            dto = item["dto"]
        else:
            project_id, dto = item
            session_id = None
            task_id = None
        db = SessionLocal()
        task_service = AudioTaskService(db)
        try:
            line_service = get_line_service(db)
            task = task_service.mark(task_id, "processing") if task_id else None
            if task:
                _publish_task_event(db, task, q.qsize())
            if dto.should_speak == 0 or dto.track in {"sfx", "bgm"} or dto.line_type in {"sfx", "bgm"}:
                if dto.id:
                    line_service.update_line(dto.id, {"status": "pending", "is_done": 1})
                task = task_service.mark(task_id, "skipped") if task_id else None
                if task:
                    _publish_task_event(db, task, q.qsize())
                await manager.broadcast({
                    "event": "line_update",
                    "project_id": project_id,
                    "session_id": session_id,
                    "task_id": task_id,
                    "line_id": dto.id,
                    "status": "skipped",
                    "progress": q.qsize(),
                    "meta": "素材轨不进入 TTS，请导入或制作音效/BGM 文件"
                })
                await manager.broadcast({
                    "event": "tts_queue_rest",
                    "queue_rest": q.qsize(),
                    "project_id": project_id
                })
                continue

            role_service = get_role_service(db)
            voice_service = get_voice_service(db)
            multi_emotion_service = get_multi_emotion_voice_service(db)
            project_service = get_project_service(db)
            emotion_service = get_emotion_service(db)
            strength_service = get_strength_service(db)


            # line_service.update_line(dto.id, {"status": "processing"})
            await manager.broadcast({
                "event": "line_update",
                "project_id": project_id,
                "session_id": session_id,
                "task_id": task_id,
                "line_id": dto.id,
                "status": "processing",
                "progress": q.qsize() + 1,  # +1 包含当前正在处理的任务
                "meta": f"角色 {dto.role_id} 开始生成"
            })

            role = role_service.get_role(dto.role_id)
            voice = voice_service.get_voice(role.default_voice_id) if role and role.default_voice_id else None
            reference_path = voice.reference_path if voice else None


            # if voice.is_multi_emotion == 1:
            #     # 使用多音色
            #     multi_emotion = multi_emotion_service.get_multi_emotion_voice_by_voice_id_emotion_id_strength_id(voice.id, dto.emotion_id, dto.strength_id)
            #     if multi_emotion is not None:
            #         reference_path = multi_emotion.reference_path

            # 9.13
            emotion = emotion_service.get_emotion(dto.emotion_id) if dto.emotion_id else None
            strength = strength_service.get_strength(dto.strength_id) if dto.strength_id else None
            # 拼接
            # emo_text = f"{strength.name}的{emotion.name} "
            # if emotion.name is "解说":
            #     emo_text = None
            emotion_name = emotion.name if emotion else None
            strength_name = strength.name if strength else None
            emo_text = None
            emo_vector = emotion_text_to_vector(emotion_name or "", strength_name or "")

            project = project_service.get_project(project_id)

            # Preserve the currently generated take before the canonical output
            # path is overwritten by a regeneration.
            if dto.id:
                line_service.ensure_generated_audio_version(dto.id)

            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(
                    ex,
                    line_service.generate_audio,
                    reference_path,
                    effective_provider_id(project, voice),
                    dto.text_content,
                    emo_text,
                    emo_vector,
                    dto.audio_path,
                    role,
                    voice,
                    dto.line_type,
                    dto.track,
                    emotion_name,
                    strength_name,
                    dto.production_note,
                ),
                timeout=TTS_TIMEOUT_SECONDS
            )

            generated_version = line_service.register_generated_audio_version(dto.id, dto.audio_path, {
                "text": dto.text_content,
                "prompt": dto.production_note,
                "emotion_id": dto.emotion_id,
                "strength_id": dto.strength_id,
                "voice_id": role.default_voice_id if role else None,
                "task_id": task_id,
            }) if dto.id else None

            line_service.update_line(dto.id, {"status": "done", "is_done": 1})
            task = task_service.mark(task_id, "done", audio_path=dto.audio_path) if task_id else None
            if task:
                _publish_task_event(db, task, q.qsize())
            await manager.broadcast({
                "event": "line_update",
                "project_id": project_id,
                "session_id": session_id,
                "task_id": task_id,
                "line_id": dto.id,
                "status": "done",
                "progress":  q.qsize(),
                "meta": "生成完成",
                "audio_path": dto.audio_path,
                "audio_version_id": (generated_version or {}).get("id"),
            })
            # 发送给前端，队列中剩余的数量
            await manager.broadcast({
                "event": "tts_queue_rest",
                "queue_rest": q.qsize(),
                "project_id": project_id
            })

        except Exception as e:
            try:
                line_service.update_line(dto.id, {"status": "failed"})
            except Exception:
                pass
            task = task_service.mark(task_id, "failed", error=e) if task_id else None
            if task:
                _publish_task_event(db, task, q.qsize())
            await manager.broadcast({
                "event": "line_update",
                "project_id": project_id,
                "session_id": session_id,
                "task_id": task_id,
                "line_id": dto.id,
                "status": "failed",
                "progress":  q.qsize(),
                "meta": f"失败: {e}"
            })

        finally:

            db.close()
            q.task_done()


def _publish_task_event(db, task, queue_size: int) -> None:
    if not task.session_id:
        return
    session = db.get(ChatSessionPO, task.session_id)
    if not session:
        return
    WorkflowEventPublisher(db).publish(session, "tts_task_updated", {
        "task_id": task.id,
        "line_id": task.line_id,
        "status": task.status,
        "attempt": task.attempt,
        "error_message": task.error_message,
        "audio_path": task.audio_path,
        "queue_size": queue_size,
    })

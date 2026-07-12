# app/tts_worker.py
import asyncio
from fastapi import FastAPI

from app.core.ws_manager import manager
from app.db.database import SessionLocal
from app.routers.chapter_router import get_voice_service, get_emotion_service, get_strength_service
from app.routers.multi_emotion_voice_router import get_multi_emotion_voice_service
from app.routers.role_router import get_line_service, get_role_service, get_project_service
from app.models.po import ChatSessionPO
from app.services.audio_task_service import AudioTaskService
from app.workflows.drama.events import WorkflowEventPublisher

TTS_TIMEOUT_SECONDS = 1200  # 可调
def emotion_text_to_vector(emotion: str, intensity: str) -> list[float]:
    """
    将情绪(文本) + 强度(文本) 转换成 8维向量
    8维分别对应: [高兴, 生气, 伤心, 害怕, 厌恶, 低落, 惊喜, 平静]
    基础情绪为 one-hot，复合情绪为多维加权混合
    :param emotion: 情绪名称
    :param intensity: "微弱" / "稍弱" / "中等" / "较强" / "强烈"
    :return: 长度为8的向量
    """
    # 8维基础情绪索引: 高兴=0, 生气=1, 伤心=2, 害怕=3, 厌恶=4, 低落=5, 惊喜=6, 平静=7
    BASE_EMOTIONS = ["高兴", "生气", "伤心", "害怕", "厌恶", "低落", "惊喜", "平静"]

    # 复合情绪 → 基础情绪权重（各维度满强度，由 intensity 统一缩放）
    COMPOSITE_MAP = {
        "嘲讽":   {"高兴": 0.5, "厌恶": 1.0},  # 讽刺语气
        "悲愤":   {"伤心": 1.0, "生气": 1.0},  # 悲愤交加
    }

    INTENSITY_MAP = {
        "微弱": 0.2,
        "稍弱": 0.4,
        "中等": 0.6,
        "较强": 0.8,
        "强烈": 1.0
    }

    scale = INTENSITY_MAP.get(intensity, 0.5)
    vec = [0.0] * 8

    if emotion in BASE_EMOTIONS:
        # 基础情绪: one-hot
        vec[BASE_EMOTIONS.index(emotion)] = scale
    elif emotion in COMPOSITE_MAP:
        # 复合情绪: 多维加权混合
        for base_name, weight in COMPOSITE_MAP[emotion].items():
            vec[BASE_EMOTIONS.index(base_name)] = round(scale * weight, 4)
    # 未知情绪返回全零向量（静默降级）
    return vec
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

            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(
                    ex,
                    line_service.generate_audio,
                    reference_path,
                    (voice.tts_provider_id if voice and voice.tts_provider_id else project.tts_provider_id),
                    dto.text_content,
                    emo_text,
                    emo_vector,
                    dto.audio_path,
                    role,
                    voice,
                    dto.line_type,
                    dto.track,
                    emotion_name,
                    dto.production_note,
                ),
                timeout=TTS_TIMEOUT_SECONDS
            )

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
                "audio_path": dto.audio_path
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

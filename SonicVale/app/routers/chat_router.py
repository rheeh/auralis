from __future__ import annotations

import asyncio
from uuid import uuid4
import os
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import CHAT_EVENT_REPLAY_LIMIT, WORKFLOW_CHAT_UI_ENABLED, WORKFLOW_TTS_REVIEW_ENABLED
from app.core.config import getConfigPath
from app.core.response import Res
from app.db.database import SessionLocal, get_db
from app.dto.chat_dto import AudioReviewDTO, ChatCommitDTO, ChatConfirmDTO, ChatMessageCreateDTO, ChatSessionCreateDTO, LineAudioRegenerateDTO, SourceDocumentCreateDTO
from app.dto.line_dto import LineCreateDTO
from app.models.po import ChatSessionPO, LinePO
from app.services.audio_task_service import AudioTaskService
from app.services.production_configuration import chapter_configuration
from app.services.chat_session_service import ChatSessionService
from app.services.drama_commit_service import DramaCommitService
from app.services.drama_workflow_service import DramaWorkflowService, WorkflowConflictError
from app.services.production_assistant_service import ProductionAssistantAgent


router = APIRouter(prefix="/chat", tags=["Conversational Drama Workflow"])


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": status_code, "message": message, "data": None})


def get_chat_service(db: Session = Depends(get_db)) -> ChatSessionService:
    return ChatSessionService(db)


def _run_start(session_id: str) -> None:
    db = SessionLocal()
    try:
        DramaWorkflowService(db).start(session_id)
    except Exception:
        pass
    finally:
        db.close()


def _run_action(session_id: str, action: dict) -> None:
    db = SessionLocal()
    try:
        DramaWorkflowService(db).submit_action(session_id, action)
    except Exception:
        pass
    finally:
        db.close()


def _run_assistant(session_id: str, message_id: str, queue) -> None:
    db = SessionLocal()
    try:
        ProductionAssistantAgent(db, queue).run_turn(session_id, message_id)
    finally:
        db.close()


class _ThreadsafeQueueProxy:
    """Schedule asyncio queue writes from FastAPI's background worker thread."""

    def __init__(self, queue, loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop

    def full(self) -> bool:
        return bool(self.queue.maxsize and self.queue.qsize() >= self.queue.maxsize)

    def put_nowait(self, item) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, item)


@router.post("/projects/{project_id}/chapters/{chapter_id}/workspace", response_model=Res[dict])
def open_chapter_workspace(project_id: int, chapter_id: int, service: ChatSessionService = Depends(get_chat_service)):
    try:
        return Res(code=200, data=service.open_chapter(project_id, chapter_id), message="章节工作台已就绪")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/projects/{project_id}/chapters/{chapter_id}/configuration", response_model=Res[dict])
def production_configuration(project_id: int, chapter_id: int, db: Session = Depends(get_db)):
    try:
        return Res(code=200, data=chapter_configuration(db, project_id, chapter_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/capabilities", response_model=Res[dict])
def workflow_capabilities():
    return Res(data={
        "workflow_enabled": True,
        "workflow_engine": "database_state_machine",
        "assistant_enabled": True,
        "chat_ui_enabled": WORKFLOW_CHAT_UI_ENABLED,
        "tts_review_enabled": WORKFLOW_TTS_REVIEW_ENABLED,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "state_backend": "sqlalchemy",
    }, message="工作流能力可用")


@router.post("/source-documents", response_model=Res[dict])
def create_source_document(dto: SourceDocumentCreateDTO, service: ChatSessionService = Depends(get_chat_service)):
    try:
        document = service.create_source_document(dto)
        return Res(data={"id": document.id, "project_id": document.project_id, "name": document.name}, message="原文已保存")
    except ValueError as exc:
        return _error(400, str(exc))


@router.post("/sessions", response_model=Res[dict], status_code=202)
def create_session(dto: ChatSessionCreateDTO, tasks: BackgroundTasks, service: ChatSessionService = Depends(get_chat_service)):
    try:
        snapshot = service.create(dto)
        tasks.add_task(_run_start, snapshot["session_id"])
        return Res(data=snapshot, code=202, message="会话已创建，正在解析小说")
    except ValueError as exc:
        return _error(400, str(exc))


@router.get("/sessions", response_model=Res[list[dict]])
def list_sessions(
    project_id: int | None = Query(default=None), status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200), service: ChatSessionService = Depends(get_chat_service),
):
    return Res(data=service.list(project_id, status, limit), message="查询成功")


@router.get("/sessions/{session_id}", response_model=Res[dict])
def get_session(session_id: str, service: ChatSessionService = Depends(get_chat_service)):
    try:
        return Res(data=service.get(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/sessions/{session_id}/history", response_model=Res[list[dict]])
def get_history(
    session_id: str, limit: int = Query(default=100, ge=1, le=200), before_id: str | None = None,
    service: ChatSessionService = Depends(get_chat_service),
):
    try:
        return Res(data=service.history(session_id, limit, before_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/role-avatar", response_model=Res[dict])
async def upload_role_avatar(
    session_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    session = db.get(ChatSessionPO, session_id)
    if not session or session.deleted_at is not None:
        return _error(404, "改编会话不存在")
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        return _error(400, "头像仅支持 JPG、PNG 或 WebP")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        return _error(400, "头像不能超过 5MB")
    target_dir = os.path.join(getConfigPath(), "projects", str(session.project_id), "role-avatars")
    os.makedirs(target_dir, exist_ok=True)
    filename = f"role_{uuid4().hex}{suffix}"
    target_path = os.path.join(target_dir, filename)
    with open(target_path, "wb") as avatar_file:
        avatar_file.write(content)
    return Res(data={
        "avatar_path": target_path,
        "preview_url": f"/chat/sessions/{session_id}/role-avatar/{filename}",
    }, message="头像已保存")


@router.get("/sessions/{session_id}/role-avatar/{filename}")
def get_role_avatar(session_id: str, filename: str, db: Session = Depends(get_db)):
    session = db.get(ChatSessionPO, session_id)
    if not session or session.deleted_at is not None:
        return _error(404, "改编会话不存在")
    safe_name = os.path.basename(filename)
    avatar_path = os.path.abspath(os.path.join(
        getConfigPath(), "projects", str(session.project_id), "role-avatars", safe_name,
    ))
    expected_dir = os.path.abspath(os.path.join(getConfigPath(), "projects", str(session.project_id), "role-avatars"))
    if os.path.dirname(avatar_path) != expected_dir or not os.path.isfile(avatar_path):
        return _error(404, "头像不存在")
    return FileResponse(avatar_path)


@router.get("/sessions/{session_id}/audio-tasks", response_model=Res[dict])
def get_audio_tasks(session_id: str, db: Session = Depends(get_db)):
    try:
        return Res(data=AudioTaskService(db).summary(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/audio-tasks/generate", response_model=Res[dict])
async def generate_session_audio(
    session_id: str, request: Request, force: bool = Query(default=False), db: Session = Depends(get_db),
):
    session = db.get(ChatSessionPO, session_id)
    if not session or session.deleted_at is not None:
        return _error(404, "改编会话不存在")
    if session.current_stage != "completed" or not session.chapter_id:
        return _error(409, "剧本写入项目后才能生成配音")

    service = AudioTaskService(db)
    lines = db.execute(
        select(LinePO).where(LinePO.chapter_id == session.chapter_id).order_by(LinePO.line_order.asc())
    ).scalars().all()
    created: list[str] = []
    skipped = 0
    q = request.app.state.tts_queue
    for line in lines:
        if not line.should_speak or line.track in {"sfx", "bgm"} or line.line_type in {"sfx", "bgm"}:
            skipped += 1
            continue
        latest = service.latest_for_line(session_id, line.id)
        if latest and latest.status in {"queued", "processing"}:
            skipped += 1
            continue
        if not force and line.status == "done" and line.audio_path:
            skipped += 1
            continue
        if q.full():
            break
        dto = LineCreateDTO.model_validate({column.name: getattr(line, column.name) for column in LinePO.__table__.columns})
        created.append(service.enqueue(q, session.project_id, session.chapter_id, line, dto, session_id).id)

    _publish_audio_event(db, session, "tts_batch_queued", {
        "task_ids": created, "created": len(created), "skipped": skipped, "queue_size": q.qsize(),
    })
    return Res(data={"task_ids": created, "created": len(created), "skipped": skipped, "queue_size": q.qsize()}, message="配音任务已加入队列")


@router.post("/sessions/{session_id}/audio-tasks/{task_id}/retry", response_model=Res[dict])
async def retry_audio_task(session_id: str, task_id: str, request: Request, db: Session = Depends(get_db)):
    service = AudioTaskService(db)
    try:
        task = service.get_for_session(session_id, task_id)
        session = db.get(ChatSessionPO, session_id)
        if task.status != "failed" and task.review_status != "rejected":
            return _error(409, "只有失败或审核未通过的任务可以重试")
        line = db.get(LinePO, task.line_id)
        if not line:
            return _error(404, "关联台词不存在")
        dto = LineCreateDTO.model_validate({column.name: getattr(line, column.name) for column in LinePO.__table__.columns})
        task = service.enqueue(request.app.state.tts_queue, task.project_id, task.chapter_id, line, dto, session_id, task)
        _publish_audio_event(db, session, "tts_task_retried", {"task_id": task.id, "line_id": line.id, "attempt": task.attempt})
        return Res(data=service.serialize(task, line), message="任务已重新加入队列")
    except OverflowError as exc:
        return _error(429, str(exc))
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/audio-tasks/{task_id}/review", response_model=Res[dict])
def review_audio_task(session_id: str, task_id: str, dto: AudioReviewDTO, db: Session = Depends(get_db)):
    service = AudioTaskService(db)
    try:
        task = service.review(session_id, task_id, dto.approved, dto.note)
        line = db.get(LinePO, task.line_id)
        session = db.get(ChatSessionPO, session_id)
        _publish_audio_event(db, session, "tts_task_reviewed", {
            "task_id": task.id, "line_id": task.line_id, "review_status": task.review_status,
        })
        return Res(data=service.serialize(task, line), message="试听审核已保存")
    except ValueError as exc:
        return _error(409, str(exc))


@router.post("/sessions/{session_id}/audio-tasks/lines/{line_id}/regenerate", response_model=Res[dict])
async def regenerate_line_audio(
    session_id: str,
    line_id: int,
    dto: LineAudioRegenerateDTO,
    request: Request,
    db: Session = Depends(get_db),
):
    session = db.get(ChatSessionPO, session_id)
    line = db.get(LinePO, line_id)
    if not session or session.deleted_at is not None or not line:
        return _error(404, "会话或台词不存在")
    if session.current_stage != "completed" or line.chapter_id != session.chapter_id:
        return _error(409, "台词不属于当前已完成会话")
    if not line.should_speak or line.track in {"sfx", "bgm"}:
        return _error(409, "当前声音轨不能生成角色配音")
    line.production_note = dto.prompt.strip() or None
    line.active_audio_variant_id = None
    line.status = "pending"
    line.is_done = 0
    db.commit()
    service = AudioTaskService(db)
    latest = service.latest_for_line(session_id, line_id)
    line_dto = LineCreateDTO.model_validate({column.name: getattr(line, column.name) for column in LinePO.__table__.columns})
    try:
        task = service.enqueue(
            request.app.state.tts_queue,
            session.project_id,
            session.chapter_id,
            line,
            line_dto,
            session_id,
            latest,
        )
        return Res(data=service.serialize(task, line), message="已按新提示词重新生成")
    except OverflowError as exc:
        return _error(429, str(exc))


def _publish_audio_event(db: Session, session: ChatSessionPO, event_type: str, payload: dict) -> None:
    from app.workflows.drama.events import WorkflowEventPublisher
    WorkflowEventPublisher(db).publish(session, event_type, payload)


@router.get("/sessions/{session_id}/events", response_model=Res[list[dict]])
def replay_events(
    session_id: str, after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=CHAT_EVENT_REPLAY_LIMIT, ge=1, le=200),
    service: ChatSessionService = Depends(get_chat_service),
):
    try:
        return Res(data=service.events(session_id, after_sequence, limit), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/message", response_model=Res[dict], status_code=202)
async def send_message(
    session_id: str,
    dto: ChatMessageCreateDTO,
    tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        assistant = ProductionAssistantAgent(db)
        user_message = assistant.accept_message(session_id, dto.message, dto.client_request_id)
        queue = getattr(request.app.state, "tts_queue", None)
        queue_proxy = _ThreadsafeQueueProxy(queue, asyncio.get_running_loop()) if queue is not None else None
        tasks.add_task(_run_assistant, session_id, user_message.id, queue_proxy)
        return Res(data={
            "session_id": session_id,
            "user_message_id": user_message.id,
        }, code=202, message="制作助手正在处理")
    except WorkflowConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/confirm", response_model=Res[dict], status_code=202)
def confirm(session_id: str, dto: ChatConfirmDTO, tasks: BackgroundTasks, service: ChatSessionService = Depends(get_chat_service)):
    try:
        snapshot = service.get(session_id)
        expected_action_type = "roles" if dto.action.endswith("roles") else "script"
        if snapshot.get("active_confirm_type") != dto.confirm_type or expected_action_type != dto.confirm_type:
            advanced_stages = {
                "roles": {"generating_script", "reviewing_script", "awaiting_script_confirmation", "script_draft_ready", "committing", "completed"},
                "script": {"script_draft_ready", "committing", "completed"},
            }
            if snapshot.get("current_stage") in advanced_stages.get(dto.confirm_type, set()):
                return Res(data=snapshot, message="该确认已处理，无需重复提交")
            return _error(409, "确认内容与当前阶段不匹配")
        tasks.add_task(_run_action, session_id, dto.model_dump(exclude={"confirm_type"}))
        return Res(data=snapshot, code=202, message="操作已提交")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/resume", response_model=Res[dict], status_code=202)
def resume(session_id: str, tasks: BackgroundTasks, service: ChatSessionService = Depends(get_chat_service)):
    try:
        snapshot = service.get(session_id)
        if snapshot["current_stage"] == "failed":
            tasks.add_task(_run_action, session_id, {
                "action": "retry", "feedback": "", "payload": {}, "client_request_id": f"resume-{uuid4().hex}",
            })
            return Res(data=snapshot, code=202, message="正在重试当前步骤")
        return Res(data=snapshot, message="会话已恢复")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/sessions/{session_id}/commit", response_model=Res[dict])
def commit(session_id: str, dto: ChatCommitDTO, db: Session = Depends(get_db)):
    try:
        result = DramaCommitService(db).commit_session(session_id, dto.chapter_title, dto.replace_chapter_lines)
        from app.workflows.drama.events import WorkflowEventPublisher
        from app.models.po import ChatSessionPO
        session = db.get(ChatSessionPO, session_id)
        WorkflowEventPublisher(db).publish(session, "project_committed", result)
        WorkflowEventPublisher(db).publish(session, "workflow_completed", result)
        return Res(data=result, message="剧本已写入项目")
    except ValueError as exc:
        return _error(409, str(exc))


@router.post("/sessions/{session_id}/cancel", response_model=Res[dict])
def cancel(session_id: str, client_request_id: str = Query(...), service: ChatSessionService = Depends(get_chat_service)):
    try:
        return Res(data=service.cancel(session_id, client_request_id), message="会话已取消")
    except WorkflowConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(404, str(exc))


@router.delete("/sessions/{session_id}", response_model=Res[dict])
def delete_session(session_id: str, service: ChatSessionService = Depends(get_chat_service)):
    try:
        service.delete(session_id)
        return Res(data={"session_id": session_id}, message="会话记录已删除")
    except ValueError as exc:
        return _error(404, str(exc))

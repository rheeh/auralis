from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import SessionLocal, get_db
from app.dto.chat_dto import ArticleOutlineActionDTO, ReviewQuestionAnswerDTO
from app.services.article_workflow_service import ArticleWorkflowService
from app.services.drama_workflow_service import WorkflowConflictError
from app.services.knowledge_production_service import KnowledgeProductionService
from app.services.knowledge_study_service import KnowledgeStudyService


router = APIRouter(prefix="/chat/sessions", tags=["Knowledge Article Workflow"])


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": status_code, "message": message, "data": None})


def get_service(db: Session = Depends(get_db)) -> ArticleWorkflowService:
    return ArticleWorkflowService(db)


def _run_analysis(session_id: str) -> None:
    db = SessionLocal()
    try:
        ArticleWorkflowService(db).analyze(session_id)
    except Exception:
        pass
    finally:
        db.close()


def _run_revision(session_id: str, dto: dict) -> None:
    db = SessionLocal()
    try:
        ArticleWorkflowService(db).revise_outline(
            session_id, dto.get("feedback", ""), dto.get("payload") or {}, dto["client_request_id"],
        )
    except Exception:
        pass
    finally:
        db.close()


def _run_script_generation(session_id: str) -> None:
    db = SessionLocal()
    try:
        KnowledgeProductionService(db).generate_script(session_id)
    except Exception:
        pass
    finally:
        db.close()


def _run_script_revision(session_id: str, dto: dict) -> None:
    db = SessionLocal()
    try:
        KnowledgeProductionService(db).revise_script(session_id, dto.get("feedback", ""), dto["client_request_id"])
    except Exception:
        pass
    finally:
        db.close()


@router.post("/{session_id}/article/analyze", response_model=Res[dict], status_code=202)
def analyze_article(session_id: str, tasks: BackgroundTasks, service: ArticleWorkflowService = Depends(get_service)):
    try:
        snapshot = service.snapshot(session_id)
        if snapshot["current_stage"] not in {"source_ready", "failed", "awaiting_outline_confirmation"}:
            return _error(409, f"当前阶段 {snapshot['current_stage']} 不能分析文章")
        if snapshot["current_stage"] in {"source_ready", "failed"}:
            tasks.add_task(_run_analysis, session_id)
        return Res(data=snapshot, code=202, message="文章分析已开始")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/{session_id}/article/analysis", response_model=Res[dict])
def get_article_analysis(session_id: str, service: ArticleWorkflowService = Depends(get_service)):
    try:
        return Res(data=service.snapshot(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{session_id}/article/outline/confirm", response_model=Res[dict])
def confirm_article_outline(session_id: str, dto: ArticleOutlineActionDTO, service: ArticleWorkflowService = Depends(get_service)):
    try:
        return Res(data=service.confirm_outline(session_id, dto.payload, dto.client_request_id), message="知识大纲已确认")
    except WorkflowConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(400, str(exc))


@router.post("/{session_id}/article/outline/revise", response_model=Res[dict], status_code=202)
def revise_article_outline(
    session_id: str,
    dto: ArticleOutlineActionDTO,
    tasks: BackgroundTasks,
    service: ArticleWorkflowService = Depends(get_service),
):
    try:
        snapshot = service.snapshot(session_id)
        if snapshot["current_stage"] != "awaiting_outline_confirmation":
            return _error(409, "当前没有待修改的知识大纲")
        tasks.add_task(_run_revision, session_id, dto.model_dump())
        return Res(data=snapshot, code=202, message="知识大纲修改已提交")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{session_id}/article/script/generate", response_model=Res[dict], status_code=202)
def generate_knowledge_script(session_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        snapshot = KnowledgeProductionService(db).snapshot(session_id)
        if snapshot["current_stage"] not in {"outline_ready", "learning_plan_ready", "failed", "awaiting_script_confirmation"}:
            return _error(409, f"当前阶段 {snapshot['current_stage']} 不能生成知识脚本")
        if snapshot["current_stage"] != "awaiting_script_confirmation":
            tasks.add_task(_run_script_generation, session_id)
        return Res(data=snapshot, code=202, message="知识音频脚本生成已开始")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/{session_id}/article/review", response_model=Res[dict])
def get_knowledge_review(session_id: str, db: Session = Depends(get_db)):
    try:
        return Res(data=KnowledgeProductionService(db).snapshot(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{session_id}/article/script/revise", response_model=Res[dict], status_code=202)
def revise_knowledge_script(session_id: str, dto: ArticleOutlineActionDTO, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        snapshot = KnowledgeProductionService(db).snapshot(session_id)
        if snapshot["current_stage"] != "awaiting_script_confirmation":
            return _error(409, "当前没有待修改的知识音频脚本")
        if not dto.feedback.strip():
            return _error(400, "请提供知识脚本修改意见")
        tasks.add_task(_run_script_revision, session_id, dto.model_dump())
        return Res(data=snapshot, code=202, message="知识脚本修改已提交")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{session_id}/article/script/confirm", response_model=Res[dict])
def confirm_knowledge_script(session_id: str, dto: ArticleOutlineActionDTO, db: Session = Depends(get_db)):
    try:
        result = KnowledgeProductionService(db).confirm_script(session_id, dto.payload, dto.client_request_id)
        return Res(data=result, message="知识音频脚本已确认")
    except WorkflowConflictError as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(400, str(exc))


@router.get("/{session_id}/knowledge-points", response_model=Res[list[dict]])
def get_knowledge_points(session_id: str, db: Session = Depends(get_db)):
    try:
        return Res(data=KnowledgeStudyService(db).knowledge_points(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.get("/{session_id}/review-questions", response_model=Res[list[dict]])
def get_review_questions(session_id: str, db: Session = Depends(get_db)):
    try:
        return Res(data=KnowledgeStudyService(db).review_questions(session_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{session_id}/review-questions/{question_id}/answer", response_model=Res[dict])
def answer_review_question(session_id: str, question_id: str, dto: ReviewQuestionAnswerDTO, db: Session = Depends(get_db)):
    try:
        return Res(data=KnowledgeStudyService(db).answer_question(session_id, question_id, dto.answer), message="复习答案已保存")
    except ValueError as exc:
        return _error(404, str(exc))

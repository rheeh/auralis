from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.drama_adaptation_dto import (
    DramaAdaptationCommitRequestDTO,
    DramaAdaptationRequestDTO,
    DramaAdaptationResponseDTO,
)
from app.services.drama_adaptation_service import DramaAdaptationService

router = APIRouter(prefix="/drama-adaptation", tags=["Drama Adaptation"])


def get_drama_adaptation_service(db: Session = Depends(get_db)) -> DramaAdaptationService:
    return DramaAdaptationService(db)


@router.post(
    "/runs",
    response_model=Res[DramaAdaptationResponseDTO],
    summary="小说改编为广播剧工程",
    description="历史结构化工作流兼容接口；新制作统一使用 /chat/sessions 的逐步确认流程。",
    deprecated=True,
)
async def create_adaptation_run(
    dto: DramaAdaptationRequestDTO,
    service: DramaAdaptationService = Depends(get_drama_adaptation_service),
):
    try:
        result = service.adapt(dto)
        return Res(data=DramaAdaptationResponseDTO(**result), code=200, message=result["message"])
    except ValueError as exc:
        return Res(data=None, code=400, message=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"广播剧改编失败：{exc}") from exc


@router.get(
    "/runs",
    response_model=Res[list[dict]],
    summary="查询广播剧改编运行记录列表",
)
async def list_adaptation_runs(
    project_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: DramaAdaptationService = Depends(get_drama_adaptation_service),
):
    runs = service.list_runs(project_id=project_id, limit=limit)
    return Res(
        data=[
            {
                "run_id": run.id,
                "project_id": run.project_id,
                "chapter_id": run.chapter_id,
                "title": run.title,
                "status": run.status,
                "current_stage": run.current_stage,
                "scene_count": run.scene_count,
                "adaptation_density": run.adaptation_density,
                "error_message": run.error_message,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            }
            for run in runs
        ],
        code=200,
        message="查询成功",
    )


@router.get(
    "/runs/{run_id}",
    response_model=Res[DramaAdaptationResponseDTO],
    summary="查询广播剧改编运行记录",
)
async def get_adaptation_run(
    run_id: int,
    service: DramaAdaptationService = Depends(get_drama_adaptation_service),
):
    run = service.get_run(run_id)
    if not run:
        return Res(data=None, code=404, message="改编运行记录不存在")
    return Res(
        data=DramaAdaptationResponseDTO(
            run_id=run.id,
            project_id=run.project_id,
            chapter_id=run.chapter_id,
            status=run.status,
            current_stage=run.current_stage,
            script=run.final_json,
            message=run.error_message or "查询成功",
        ),
        code=200,
        message="查询成功",
    )


@router.post(
    "/commit",
    response_model=Res[DramaAdaptationResponseDTO],
    summary="将广播剧改编结果写入 Auralis 项目",
)
async def commit_adaptation_run(
    dto: DramaAdaptationCommitRequestDTO,
    service: DramaAdaptationService = Depends(get_drama_adaptation_service),
):
    try:
        chapter = service.commit_run(dto.run_id, dto.chapter_title, dto.replace_chapter_lines)
        run = service.get_run(dto.run_id)
        return Res(
            data=DramaAdaptationResponseDTO(
                run_id=run.id,
                project_id=run.project_id,
                chapter_id=chapter.id,
                status=run.status,
                current_stage=run.current_stage,
                script=run.final_json,
                message="已写入项目章节",
            ),
            code=200,
            message="已写入项目章节",
        )
    except ValueError as exc:
        return Res(data=None, code=400, message=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"写入广播剧工程失败：{exc}") from exc

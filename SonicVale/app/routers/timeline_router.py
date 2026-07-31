from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.timeline_dto import TimelineClipUpdateDTO
from app.services.timeline_render_service import TimelineRenderService
from app.services.timeline_service import TimelineService


router = APIRouter(prefix="/projects", tags=["Timeline"])


def get_timeline_service(db: Session = Depends(get_db)) -> TimelineService:
    return TimelineService(db)


def get_timeline_render_service(db: Session = Depends(get_db)) -> TimelineRenderService:
    return TimelineRenderService(db)


@router.get("/{project_id}/chapters/{chapter_id}/timeline", response_model=Res[dict], summary="读取章节多轨时间线")
def get_chapter_timeline(
    project_id: int,
    chapter_id: int,
    service: TimelineService = Depends(get_timeline_service),
):
    """只读返回数据库中的真实音频时长时间线，不再按文字长度估算。"""

    try:
        return Res(data=service.get_chapter_timeline(project_id, chapter_id), message="查询成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/chapters/{chapter_id}/timeline/build", response_model=Res[dict], summary="构建章节多轨时间线")
def build_chapter_timeline(
    project_id: int,
    chapter_id: int,
    force: bool = Query(False, description="是否丢弃当前自动生成片段并重新按音频时长构建"),
    overwrite_manual: bool = Query(False, description="是否允许自动构建覆盖未来用户编辑过的片段"),
    service: TimelineService = Depends(get_timeline_service),
):
    """登记当前音频资产并按真实文件时长生成四轨片段。"""

    try:
        return Res(
            data=service.build_chapter_timeline(
                project_id,
                chapter_id,
                force=force,
                overwrite_manual=overwrite_manual,
            ),
            message="构建成功",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{project_id}/chapters/{chapter_id}/timeline/clips/{clip_id}", response_model=Res[dict], summary="编辑时间线片段")
def update_timeline_clip(
    project_id: int,
    chapter_id: int,
    clip_id: int,
    dto: TimelineClipUpdateDTO,
    service: TimelineService = Depends(get_timeline_service),
):
    try:
        return Res(data=service.update_clip(project_id, chapter_id, clip_id, dto), message="片段已更新")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/chapters/{chapter_id}/timeline/render", response_model=Res[dict], summary="按时间线渲染章节成片")
def render_chapter_timeline(
    project_id: int,
    chapter_id: int,
    service: TimelineRenderService = Depends(get_timeline_render_service),
):
    try:
        data = service.render_chapter(project_id, chapter_id)
        data["audio_url"] = f"/projects/{project_id}/chapters/{chapter_id}/timeline/render/audio"
        return Res(data=data, message="时间线混音成片已生成")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{project_id}/chapters/{chapter_id}/timeline/render", response_model=Res[dict], summary="读取最新时间线成片")
def get_latest_timeline_render(
    project_id: int,
    chapter_id: int,
    service: TimelineRenderService = Depends(get_timeline_render_service),
):
    try:
        data = service.get_latest_render(project_id, chapter_id)
        data["audio_url"] = f"/projects/{project_id}/chapters/{chapter_id}/timeline/render/audio"
        return Res(data=data, message="查询成功")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{project_id}/chapters/{chapter_id}/timeline/render/audio", summary="试听或下载最新时间线成片")
def get_timeline_render_audio(
    project_id: int,
    chapter_id: int,
    service: TimelineRenderService = Depends(get_timeline_render_service),
):
    try:
        return FileResponse(service.latest_audio_path(project_id, chapter_id), media_type="audio/wav")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

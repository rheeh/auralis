from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.services.timeline_service import TimelineService


router = APIRouter(prefix="/projects", tags=["Timeline"])


def get_timeline_service(db: Session = Depends(get_db)) -> TimelineService:
    return TimelineService(db)


@router.get("/{project_id}/chapters/{chapter_id}/timeline", response_model=Res[dict], summary="读取章节多轨内容概览")
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


@router.post("/{project_id}/chapters/{chapter_id}/timeline/build", response_model=Res[dict], summary="构建章节多轨内容概览")
def build_chapter_timeline(
    project_id: int,
    chapter_id: int,
    force: bool = Query(False, description="是否丢弃当前自动生成片段并重新按音频时长构建"),
    service: TimelineService = Depends(get_timeline_service),
):
    """登记当前音频资产并按真实文件时长生成四轨片段。"""

    try:
        return Res(data=service.build_chapter_timeline(project_id, chapter_id, force=force), message="构建成功")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

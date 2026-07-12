from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.models.po import AudioTaskPO, LinePO
from app.services.audio_task_service import AudioTaskService

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.get("/status", response_model=Res[dict], summary="查询本地生成队列状态")
async def get_queue_status(request: Request, db: Session = Depends(get_db)):
    tts_queue = getattr(request.app.state, "tts_queue", None)
    workers = getattr(request.app.state, "tts_workers", [])
    counts = dict(db.execute(
        select(AudioTaskPO.status, func.count(AudioTaskPO.id)).group_by(AudioTaskPO.status)
    ).all())
    return Res(
        data={
            "tts_queue_size": tts_queue.qsize() if tts_queue else 0,
            "tts_workers": len(workers),
            "workers_running": sum(1 for worker in workers if not worker.done()),
            "audio_task_counts": counts,
        },
        code=200,
        message="查询成功",
    )


@router.get("/audio-tasks", response_model=Res[list[dict]], summary="查询最近音频任务")
def list_audio_tasks(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(
        select(AudioTaskPO, LinePO)
        .join(LinePO, LinePO.id == AudioTaskPO.line_id)
        .order_by(AudioTaskPO.updated_at.desc())
        .limit(limit)
    ).all()
    return Res(data=[AudioTaskService.serialize(task, line) for task, line in rows], message="查询成功")

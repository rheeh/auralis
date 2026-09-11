from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.speech_dto import ProjectSpeechSettings
from app.services.speech_direction_service import SpeechDirectionService
from app.services.tts_trace_service import TTSTraceService, redact


router = APIRouter(prefix="/projects", tags=["Speech direction"])


@router.get("/{project_id}/speech-settings", response_model=Res[dict])
def get_settings(project_id: int, db: Session = Depends(get_db)):
    try:
        return Res(data=SpeechDirectionService(db).settings(project_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/{project_id}/speech-settings", response_model=Res[dict])
def save_settings(project_id: int, dto: ProjectSpeechSettings, db: Session = Depends(get_db)):
    try:
        return Res(data=SpeechDirectionService(db).save_settings(project_id, dto))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{project_id}/lines/{line_id}/speech-preview", response_model=Res[dict])
def preview(project_id: int, line_id: int, db: Session = Depends(get_db)):
    try:
        prepared = SpeechDirectionService(db).preview(project_id, line_id)
        from app.models.po import TTSProviderPO
        provider = db.get(TTSProviderPO, prepared["provider_id"])
        return Res(data=redact(prepared, (provider.api_key or "",)))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{project_id}/tts-generations", response_model=Res[dict])
def generations(project_id: int, line_id: int | None = None,
                limit: int = Query(20, ge=1, le=50), before: str | None = None,
                db: Session = Depends(get_db)):
    try:
        # Historical line IDs remain queryable after deletion, scoped by project.
        SpeechDirectionService(db).project(project_id)
        return Res(data=TTSTraceService(db).list(project_id, line_id, limit, before))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.sound_library_dto import SoundLibraryImportDTO, SoundLibraryInsertDTO, SoundRecommendationDTO
from app.models.po import LinePO
from app.repositories.line_repository import LineRepository
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.services.line_service import LineService
from app.services.sound_library_service import MAX_AUDIO_BYTES, SoundLibraryService, SUPPORTED_EXTENSIONS
from app.services.sound_recommendation_service import SoundRecommendationService
from app.services.workflow_llm_service import WorkflowLLMError


router = APIRouter(prefix="/sound-library", tags=["Sound Library"])


@router.post("/recommendations", response_model=Res[dict])
def recommend_sounds(dto: SoundRecommendationDTO, db: Session = Depends(get_db)):
    try:
        return Res(data=SoundRecommendationService(db).recommend(dto), message="推荐已就绪，试听后选择")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowLLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def get_sound_library_service(db: Session = Depends(get_db)) -> SoundLibraryService:
    return SoundLibraryService(db)


def get_line_service(db: Session = Depends(get_db)) -> LineService:
    return LineService(
        LineRepository(db),
        RoleRepository(db),
        TTSProviderRepository(db),
        LLMProviderRepository(db),
    )


@router.get("/assets", response_model=Res[list[dict]])
def list_assets(
    source_type: str = Query("all", pattern="^(all|builtin|user)$"),
    category: str | None = None,
    keyword: str | None = None,
    service: SoundLibraryService = Depends(get_sound_library_service),
):
    try:
        return Res(data=service.list_assets(source_type, category, keyword), message="查询成功")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/import-path", response_model=Res[dict])
def import_asset_path(
    dto: SoundLibraryImportDTO,
    service: SoundLibraryService = Depends(get_sound_library_service),
):
    try:
        return Res(
            data=service.import_path(dto.source_path, dto.name, dto.category, dto.tags),
            message="素材已导入",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/upload", response_model=Res[dict])
def upload_asset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    category: str = Form("foley"),
    tags: str = Form(""),
    service: SoundLibraryService = Depends(get_sound_library_service),
):
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 wav/mp3/m4a/ogg/flac 音频素材")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as stream:
            temp_path = stream.name
            copied = 0
            while chunk := file.file.read(1024 * 1024):
                copied += len(chunk)
                if copied > MAX_AUDIO_BYTES:
                    raise ValueError("单个音频素材不能超过 200 MB")
                stream.write(chunk)
        result = service.import_path(
            temp_path,
            name or os.path.splitext(file.filename or "")[0],
            category,
            [item.strip() for item in tags.split(",") if item.strip()],
        )
        return Res(data=result, message="素材已上传")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if temp_path:
            os.unlink(temp_path) if os.path.exists(temp_path) else None
        file.file.close()


@router.get("/assets/{asset_id}/audio")
def get_asset_audio(asset_id: str, service: SoundLibraryService = Depends(get_sound_library_service)):
    try:
        path = service.resolve_path(asset_id)
        return FileResponse(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/bind/{line_id}", response_model=Res[dict])
def bind_asset(
    asset_id: str,
    line_id: int,
    db: Session = Depends(get_db),
    service: SoundLibraryService = Depends(get_sound_library_service),
    line_service: LineService = Depends(get_line_service),
):
    line = db.get(LinePO, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="台词不存在")
    if (line.track or line.line_type) not in {"sfx", "bgm"}:
        raise HTTPException(status_code=409, detail="素材库音频只能绑定到音效或 BGM 轨道")
    try:
        return Res(data=service.bind_asset(asset_id, line_id, line_service), message="素材已绑定")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/assets/{asset_id}", response_model=Res[bool])
def delete_asset(asset_id: str, service: SoundLibraryService = Depends(get_sound_library_service)):
    if asset_id.startswith("builtin_"):
        raise HTTPException(status_code=403, detail="内置素材不可删除")
    try:
        service.delete_user_asset(asset_id)
        return Res(data=True, message="素材已删除")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/insert", response_model=Res[dict])
def insert_asset(
    asset_id: str,
    dto: SoundLibraryInsertDTO,
    service: SoundLibraryService = Depends(get_sound_library_service),
):
    try:
        return Res(data=service.insert_asset(asset_id, dto), message="音效已加入章节")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

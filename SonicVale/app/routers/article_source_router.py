from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.response import Res
from app.db.database import get_db
from app.dto.chat_dto import ArticleSourceImportDTO, ArticleSourceNormalizeDTO, ArticleSourcePreviewDTO
from app.services.article_ingest_service import ArticleFetchError, ArticleIngestService


router = APIRouter(prefix="/chat/article-sources", tags=["Knowledge Article Sources"])


def _error(status_code: int, message: str, error_code: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": status_code, "message": message, "data": {"error_code": error_code} if error_code else None},
    )


def get_service(db: Session = Depends(get_db)) -> ArticleIngestService:
    return ArticleIngestService(db)


@router.post("/instant-workspace", response_model=Res[dict])
def ensure_instant_workspace(service: ArticleIngestService = Depends(get_service)):
    try:
        return Res(data=service.ensure_instant_workspace(), message="一次性知识音频制作空间已准备")
    except ValueError as exc:
        return _error(400, str(exc))


@router.post("/preview", response_model=Res[dict])
def preview_article(dto: ArticleSourcePreviewDTO, service: ArticleIngestService = Depends(get_service)):
    try:
        return Res(data=service.preview(dto), message="文章预览已准备")
    except ArticleFetchError as exc:
        return _error(422, str(exc), exc.code)
    except ValueError as exc:
        return _error(400, str(exc))

@router.post("/import", response_model=Res[dict])
def import_article(dto: ArticleSourceImportDTO, service: ArticleIngestService = Depends(get_service)):
    try:
        return Res(data=service.import_source(dto), message="文章正文已确认并保存")
    except ValueError as exc:
        return _error(400, str(exc))


@router.get("/{source_id}", response_model=Res[dict])
def get_article_source(source_id: int, service: ArticleIngestService = Depends(get_service)):
    try:
        return Res(data=service.get(source_id), message="查询成功")
    except ValueError as exc:
        return _error(404, str(exc))


@router.post("/{source_id}/normalize", response_model=Res[dict])
def normalize_article_source(
    source_id: int,
    dto: ArticleSourceNormalizeDTO,
    service: ArticleIngestService = Depends(get_service),
):
    try:
        return Res(data=service.normalize(source_id, dto.source_text), message="文章正文已重新清洗")
    except ValueError as exc:
        return _error(400, str(exc))

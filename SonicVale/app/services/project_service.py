from __future__ import annotations
import os
import re
import logging
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Sequence, delete, select, or_, update, inspect, Table, MetaData

from app.core.config import getConfigPath
from app.entity.project_entity import ProjectEntity
from app.models.po import (
    AdaptationDraftRevisionPO,
    AdaptationRunPO,
    AudioTaskPO,
    AudioAssetPO,
    ChapterPO,
    LinePO,
    RolePO,
    TimelineClipPO,
    TimelineTrackPO,
    ChatMessagePO,
    ChatSessionPO,
    ProjectPO,
    SourceDocumentPO,
    WorkflowEventPO,
)

from app.repositories.project_repository import ProjectRepository
from app.services.timeline_service import TimelineService


class ProjectService:

    def __init__(self, repository: ProjectRepository):
        """注入 repository"""
        self.repository = repository

    def create_project(self,  entity: ProjectEntity):
        """创建新项目
        - 检查同名项目是否存在
        - 如果存在，抛出异常或返回错误
        - 调用 repository.create 插入数据库
        """
        project = self.repository.get_by_name(entity.name)
        if project:
            return None, "项目已存在"

        if not entity.description:
            entity.description = ""
        if entity.is_precise_fill is None:
            entity.is_precise_fill = 0

        root_path = entity.project_root_path or os.path.join(getConfigPath(), "projects")
        root_path = os.path.abspath(os.path.expanduser(root_path))
        try:
            os.makedirs(root_path, exist_ok=True)
        except OSError as exc:
            logging.exception("项目根路径创建失败: %s", root_path)
            return None, f"项目根路径不可用: {exc}"
        entity.project_root_path = root_path

        # 手动将entity转化为po
        po = ProjectPO(**entity.__dict__)
        res = self.repository.create(po)

        # res(po) --> entity
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        entity = ProjectEntity(**data)

        # 将po转化为entity
        return entity, "创建成功"


    def get_project(self, project_id: int) -> ProjectEntity | None:
        """根据 ID 查询项目"""
        po = self.repository.get_by_id(project_id)
        if not po:
            return None
        data = {k: v for k, v in po.__dict__.items() if not k.startswith("_")}
        res = ProjectEntity(**data)
        return res

    def get_all_projects(self) -> Sequence[ProjectEntity]:
        """获取所有项目列表"""
        pos = self.repository.get_all()
        # pos -> entities

        entities = [
            ProjectEntity(**{k: v for k, v in po.__dict__.items() if not k.startswith("_")})
            for po in pos
        ]
        return entities

    def update_project(self, project_id: int, data:dict) -> bool:
        """更新项目
        - 可以只更新部分字段
        - 检查同名冲突
        """
        project = self.repository.get_by_id(project_id)
        if not project:
            return False
        name = data.get("name", project.name)
        existing = self.repository.get_by_name(name)
        if existing and existing.id != project_id:
            return False
        if "project_root_path" in data and data["project_root_path"]:
            data["project_root_path"] = os.path.abspath(os.path.expanduser(data["project_root_path"]))
            os.makedirs(data["project_root_path"], exist_ok=True)
        self.repository.update(project_id, data)
        return True

    def delete_project(self, project_id: int) -> bool:
        """Delete the complete dependency graph atomically, then remove files."""
        db = self.repository.db
        project = self.repository.get_by_id(project_id)
        if not project:
            return False
        if db.scalar(select(AudioTaskPO.id).where(AudioTaskPO.project_id == project_id, AudioTaskPO.status.in_(["running", "processing"])).limit(1)):
            raise ValueError("项目仍在生成音频，请等待当前任务结束后再删除")
        root = Path(project.project_root_path or Path(getConfigPath()) / "projects").expanduser().resolve()
        folder = root / str(project_id)
        if folder.is_symlink():
            raise ValueError("项目目录是符号链接，请先检查项目存储位置")
        quarantine = root / f".deleting-{project_id}-{uuid4().hex}"
        moved = False
        session_ids = list(db.execute(
            select(ChatSessionPO.id).where(ChatSessionPO.project_id == project_id)
        ).scalars())
        run_ids = list(db.execute(
            select(AdaptationRunPO.id).where(AdaptationRunPO.project_id == project_id)
        ).scalars())

        chapter_ids = select(ChapterPO.id).where(ChapterPO.project_id == project_id)
        line_ids = select(LinePO.id).where(LinePO.chapter_id.in_(chapter_ids))
        asset_ids = select(AudioAssetPO.id).where(AudioAssetPO.project_id == project_id)
        try:
            self._delete_legacy_knowledge_data(db, project_id, session_ids)
            db.execute(delete(AudioTaskPO).where(or_(AudioTaskPO.project_id == project_id, AudioTaskPO.line_id.in_(line_ids), AudioTaskPO.session_id.in_(session_ids))))
            db.execute(delete(WorkflowEventPO).where(or_(WorkflowEventPO.project_id == project_id, WorkflowEventPO.session_id.in_(session_ids))))
            db.execute(delete(AdaptationDraftRevisionPO).where(or_(AdaptationDraftRevisionPO.session_id.in_(session_ids), AdaptationDraftRevisionPO.run_id.in_(run_ids))))
            db.execute(delete(ChatMessagePO).where(ChatMessagePO.session_id.in_(session_ids)))
            db.execute(delete(ChatSessionPO).where(ChatSessionPO.id.in_(session_ids)))
            db.execute(delete(TimelineClipPO).where(TimelineClipPO.project_id == project_id))
            # Derived audio assets reference source takes; detach before bulk deletion.
            db.execute(update(AudioAssetPO).where(AudioAssetPO.id.in_(asset_ids)).values(source_asset_id=None))
            db.execute(delete(AudioAssetPO).where(AudioAssetPO.project_id == project_id))
            db.execute(delete(TimelineTrackPO).where(TimelineTrackPO.project_id == project_id))
            db.execute(delete(LinePO).where(LinePO.chapter_id.in_(chapter_ids)))
            db.execute(delete(ChapterPO).where(ChapterPO.project_id == project_id))
            db.execute(delete(RolePO).where(RolePO.project_id == project_id))
            db.execute(delete(SourceDocumentPO).where(SourceDocumentPO.project_id == project_id))
            db.execute(delete(AdaptationRunPO).where(AdaptationRunPO.project_id == project_id))
            db.execute(delete(ProjectPO).where(ProjectPO.id == project_id))
            db.flush()
            if folder.exists():
                folder.rename(quarantine)
                moved = True
            db.commit()
        except Exception:
            db.rollback()
            if moved:
                quarantine.rename(folder)
            raise
        if moved:
            try:
                shutil.rmtree(quarantine)
            except OSError:
                logging.warning("项目已删除，待清理的文件副本保留在 %s", quarantine)
        return True

    @staticmethod
    def _delete_legacy_knowledge_data(db, project_id, session_ids):
        # Removed knowledge-audio features left these tables in upgraded databases.
        # Reflect only the known legacy tables, without recreating them on fresh installs.
        connection = db.connection()
        inspector = inspect(connection)
        for name in ("knowledge_review_answers", "article_sources"):
            if not inspector.has_table(name):
                continue
            table = Table(name, MetaData(), autoload_with=connection)
            conditions = []
            if "project_id" in table.c:
                conditions.append(table.c.project_id == project_id)
            if "session_id" in table.c:
                conditions.append(table.c.session_id.in_(session_ids))
            if conditions:
                db.execute(delete(table).where(or_(*conditions)))


    def search_projects(self, keyword: str) -> Sequence[ProjectEntity]:
        """模糊搜索项目"""

    # 解析content，按照章节
    def parse_content(self, content):
        """解析内容，按照章节"""
        # 正则匹配常见章节格式（支持中英文数字）
        chapter_pattern = re.compile(
            r'(第[\d一二三四五六七八九十百千]+[章回节部卷].*?)(?=\n|$)'
        )
        # 找到所有章节标题位置
        matches = list(chapter_pattern.finditer(content))
        chapters = []
        # 如果没找到章节，直接返回整个文本
        if not matches:
            return chapters

        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            chapter_name = match.group(1).strip()
            chapter_content = content[start:end].strip()
            chapters.append({
                "chapter_name": chapter_name,
                "content": chapter_content
            })
        # 排序
        # chapters.sort(key=lambda x: x["chapter_name"])
        # 不需要排序了，因为是顺序解析得到的
        return  chapters

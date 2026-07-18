from __future__ import annotations
import os
import re
import logging

from sqlalchemy import Sequence, delete, select

from app.core.config import getConfigPath
from app.entity.project_entity import ProjectEntity
from app.models.po import (
    ArticleSourcePO,
    AdaptationDraftRevisionPO,
    AdaptationRunPO,
    AudioTaskPO,
    ChatMessagePO,
    ChatSessionPO,
    KnowledgeReviewAnswerPO,
    ProjectPO,
    SourceDocumentPO,
    WorkflowEventPO,
)

from app.repositories.project_repository import ProjectRepository


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
        """删除项目
        - 可以添加业务校验，例如项目下有章节是否允许删除
        - 后续需要级联删除所有章节内容
        """
        db = self.repository.db
        session_ids = list(db.execute(
            select(ChatSessionPO.id).where(ChatSessionPO.project_id == project_id)
        ).scalars())
        run_ids = list(db.execute(
            select(AdaptationRunPO.id).where(AdaptationRunPO.project_id == project_id)
        ).scalars())

        # 工作流表没有完整的数据库级外键级联，删除项目时必须按依赖顺序清理。
        db.execute(delete(AudioTaskPO).where(AudioTaskPO.project_id == project_id))
        db.execute(delete(WorkflowEventPO).where(WorkflowEventPO.project_id == project_id))
        db.execute(delete(ArticleSourcePO).where(ArticleSourcePO.project_id == project_id))
        if session_ids:
            db.execute(delete(KnowledgeReviewAnswerPO).where(KnowledgeReviewAnswerPO.session_id.in_(session_ids)))
            db.execute(delete(AdaptationDraftRevisionPO).where(AdaptationDraftRevisionPO.session_id.in_(session_ids)))
            db.execute(delete(ChatMessagePO).where(ChatMessagePO.session_id.in_(session_ids)))
            db.execute(delete(ChatSessionPO).where(ChatSessionPO.id.in_(session_ids)))
        if run_ids:
            db.execute(delete(AdaptationDraftRevisionPO).where(AdaptationDraftRevisionPO.run_id.in_(run_ids)))
        db.execute(delete(SourceDocumentPO).where(SourceDocumentPO.project_id == project_id))
        db.execute(delete(AdaptationRunPO).where(AdaptationRunPO.project_id == project_id))
        db.commit()

        res = self.repository.delete(project_id)
        return res


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

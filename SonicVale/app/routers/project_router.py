from __future__ import annotations

import os
import shutil
import logging
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from typing import List

import numpy as np
import soundfile as sf
from sqlalchemy.orm import Session

from app.core.config import getConfigPath
from app.core.response import Res
from app.db.database import get_db
from app.dto.project_dto import ProjectCreateDTO, ProjectResponseDTO, ProjectImportDTO
from app.entity.chapter_entity import ChapterEntity
from app.entity.project_entity import ProjectEntity
from app.models.po import ChapterPO
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.line_repository import LineRepository
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.repositories.voice_repository import VoiceRepository
from app.services.chapter_service import ChapterService
from app.services.project_service import ProjectService
from app.repositories.project_repository import ProjectRepository
from app.services.role_service import RoleService

# 初始化 router
router = APIRouter(prefix="/projects", tags=["Projects"])
PLACEHOLDER_MATERIAL_MARKER = "[AURALIS_PLACEHOLDER_MATERIAL]"

# 依赖注入（实际项目可用 DI 容器）

def get_service(db: Session = Depends(get_db)) -> ProjectService:
    repository = ProjectRepository(db)  # ✅ 传入 db
    return ProjectService(repository)

def get_chapter_service(db: Session = Depends(get_db)) -> ChapterService:
    repository = ChapterRepository(db)  # ✅ 传入 db
    return ChapterService(repository)

def get_role_service(db: Session = Depends(get_db)) -> RoleService:
    repository = RoleRepository(db)  # ✅ 传入 db
    return RoleService(repository)


@router.post("/", response_model=Res[ProjectResponseDTO],
             summary="创建项目",
             description="根据项目信息创建项目，项目名称不可重复")
def create_project(dto: ProjectCreateDTO, service: ProjectService = Depends(get_service)):
    """
    创建项目
    - dto: 前端 POST JSON 传入参数
    - service: Service 层注入
    """
    try:
        # DTO → Entity
        entity = ProjectEntity(**dto.__dict__)

        # 调用 Service 创建项目（返回 True/False）
        entityRes,message = service.create_project(entity)

        # 返回统一 Response
        if entityRes is not None:
            # 创建成功，可以返回 DTO 或者部分字段
            res = ProjectResponseDTO(**entityRes.__dict__)
            return Res(data=res, code=200, message="创建成功")
        else:
            return Res(data=None, code=400, message=message)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# 按id查找
@router.get("/{project_id}", response_model=Res[ProjectResponseDTO],
            summary="查询项目",
            description="根据项目ID查询项目信息")
def get_project(project_id: int, service: ProjectService = Depends(get_service)):
    entity = service.get_project(project_id)
    if entity:
        res = ProjectResponseDTO(**entity.__dict__)
        return Res(data=res, code=200, message="查询成功")
    else:
        return Res(data=None, code=404, message="项目不存在")

@router.get("/{project_id}/readiness", response_model=Res[dict],
            summary="检查项目制作就绪状态",
            description="检查广播剧项目从改编、声线、素材到导出的制作缺口")
def get_project_readiness(project_id: int, db: Session = Depends(get_db)):
    project_repository = ProjectRepository(db)
    chapter_repository = ChapterRepository(db)
    line_repository = LineRepository(db)
    role_repository = RoleRepository(db)
    voice_repository = VoiceRepository(db)
    llm_repository = LLMProviderRepository(db)
    tts_repository = TTSProviderRepository(db)

    project = project_repository.get_by_id(project_id)
    if not project:
        return Res(data=None, code=404, message="项目不存在")

    chapters = list(chapter_repository.get_all(project_id))
    roles = list(role_repository.get_all(project_id))
    role_map = {role.id: role for role in roles}
    lines = []
    for chapter in chapters:
        lines.extend(list(line_repository.get_all(chapter.id)))

    voice_ids = {role.default_voice_id for role in roles if role.default_voice_id}
    voice_ids.update(line.voice_id for line in lines if line.voice_id)
    voices = {voice_id: voice_repository.get_by_id(voice_id) for voice_id in voice_ids}

    speakable_lines = [line for line in lines if _is_speakable_line(line)]
    material_lines = [line for line in lines if not _is_speakable_line(line)]
    missing_voice_roles = []
    missing_voice_role_ids = set()
    for line in speakable_lines:
        role = role_map.get(line.role_id)
        line_voice = voices.get(line.voice_id) if line.voice_id else None
        role_voice = voices.get(role.default_voice_id) if role and role.default_voice_id else None
        if not line_voice and not role_voice:
            key = role.id if role else f"line-{line.id}"
            if key in missing_voice_role_ids:
                continue
            missing_voice_role_ids.add(key)
            missing_voice_roles.append({
                "role_id": role.id if role else None,
                "role_name": role.name if role else "未绑定角色",
                "line_id": line.id,
                "line_order": line.line_order,
            })

    missing_material_lines = [
        _line_ref(line)
        for line in material_lines
        if not _audio_ready(line.audio_path)
    ]
    placeholder_material_lines = [
        _line_ref(line)
        for line in material_lines
        if _audio_ready(line.audio_path) and _is_material_placeholder(line)
    ]
    missing_speakable_audio_lines = [
        _line_ref(line)
        for line in speakable_lines
        if not _audio_ready(line.audio_path) or line.status != "done" or line.is_done != 1
    ]

    llm = llm_repository.get_by_id(project.llm_provider_id) if project.llm_provider_id else None
    tts = tts_repository.get_by_id(project.tts_provider_id) if project.tts_provider_id else None
    issues = []
    if not project.llm_provider_id or not project.llm_model or not llm:
        issues.append(_issue("warning", "未配置可用 LLM", "工作台无法把小说自动改编为广播剧台本", "去配置中心或项目设置补 LLM"))
    if not project.tts_provider_id or not tts:
        issues.append(_issue("warning", "未配置可用 TTS", "人物声和旁白无法批量生成音频", "去配置中心或项目设置补 TTS"))
    if not chapters:
        issues.append(_issue("info", "还没有章节", "可以从工作台粘贴小说生成台本，也可以创建空白章节", "进入工作台开始改编"))
    if chapters and not lines:
        issues.append(_issue("info", "章节里还没有台词", "需要导入或生成广播剧台本后才能制作音频", "生成或导入台词"))
    if missing_voice_roles:
        issues.append(_issue("danger", "存在未绑定音色的角色", f"{len(missing_voice_roles)} 个角色/台词缺少可生成声线", "进入角色页或配音工程绑定音色"))
    if missing_material_lines:
        issues.append(_issue("warning", "音效/BGM 素材未绑定", f"{len(missing_material_lines)} 条素材轨还没有音频文件", "进入配音工程绑定素材"))
    if placeholder_material_lines:
        issues.append(_issue("info", "存在制作占位素材", f"{len(placeholder_material_lines)} 条音效/BGM 是临时占位音频", "正式成片前在素材库替换为真实素材"))
    if missing_speakable_audio_lines:
        issues.append(_issue("warning", "人物/旁白音频未完成", f"{len(missing_speakable_audio_lines)} 条人物/旁白台词还未生成完成", "进入配音工程批量生成"))

    ready_for_adaptation = bool(project.llm_provider_id and project.llm_model and llm)
    ready_for_generation = bool(project.tts_provider_id and tts and speakable_lines and not missing_voice_roles)
    ready_for_export = bool(lines) and not missing_material_lines and not missing_speakable_audio_lines
    ready_for_final_export = ready_for_export and not placeholder_material_lines
    score_parts = [
        1 if ready_for_adaptation else 0,
        1 if chapters else 0,
        1 if lines else 0,
        1 if ready_for_generation else 0,
        1 if ready_for_export else 0,
    ]
    readiness_score = int(sum(score_parts) / len(score_parts) * 100)

    return Res(
        data={
            "project_id": project_id,
            "readiness_score": readiness_score,
            "ready_for_adaptation": ready_for_adaptation,
            "ready_for_generation": ready_for_generation,
            "ready_for_export": ready_for_export,
            "ready_for_final_export": ready_for_final_export,
            "counts": {
                "chapters": len(chapters),
                "roles": len(roles),
                "lines": len(lines),
                "speakable_lines": len(speakable_lines),
                "material_lines": len(material_lines),
                "missing_voice_roles": len(missing_voice_roles),
                "missing_material_lines": len(missing_material_lines),
                "placeholder_material_lines": len(placeholder_material_lines),
                "missing_speakable_audio_lines": len(missing_speakable_audio_lines),
            },
            "issues": issues,
            "missing_voice_roles": missing_voice_roles[:50],
            "missing_material_lines": missing_material_lines[:80],
            "placeholder_material_lines": placeholder_material_lines[:80],
            "missing_speakable_audio_lines": missing_speakable_audio_lines[:80],
        },
        code=200,
        message="查询成功",
    )

@router.post("/{project_id}/readiness/repair", response_model=Res[dict],
             summary="自动修复项目制作状态",
             description="同步已有音频文件的完成状态，并可为音效/BGM 缺失项生成低音量制作占位音频")
def repair_project_readiness(
    project_id: int,
    sync_audio_status: bool = True,
    create_material_placeholders: bool = False,
    db: Session = Depends(get_db),
):
    project_repository = ProjectRepository(db)
    chapter_repository = ChapterRepository(db)
    line_repository = LineRepository(db)

    project = project_repository.get_by_id(project_id)
    if not project:
        return Res(data=None, code=404, message="项目不存在")

    chapters = list(chapter_repository.get_all(project_id))
    lines = []
    for chapter in chapters:
        lines.extend(list(line_repository.get_all(chapter.id)))

    synced_audio = 0
    created_material_placeholders = 0
    skipped = 0
    errors = []

    for line in lines:
        try:
            if sync_audio_status and _audio_ready(line.audio_path):
                if line.status != "done" or line.is_done != 1:
                    line_repository.update(line.id, {"status": "done", "is_done": 1})
                    synced_audio += 1
                continue

            if create_material_placeholders and not _is_speakable_line(line):
                target_path = _material_placeholder_path(project, line)
                if not _audio_ready(target_path):
                    _create_material_placeholder_audio(line, target_path)
                line_repository.update(line.id, {
                    "audio_path": target_path,
                    "status": "done",
                    "is_done": 1,
                    "subtitle_path": None,
                    "production_note": _with_placeholder_note(line.production_note),
                })
                created_material_placeholders += 1
                continue

            skipped += 1
        except Exception as exc:
            logging.exception("制作状态自动修复失败: line_id=%s", line.id)
            errors.append({"line_id": line.id, "message": str(exc)})

    return Res(
        data={
            "project_id": project_id,
            "synced_audio": synced_audio,
            "created_material_placeholders": created_material_placeholders,
            "skipped": skipped,
            "errors": errors[:20],
        },
        code=200 if not errors else 207,
        message="修复完成" if not errors else "部分修复完成",
    )

@router.get("/", response_model=Res[List[ProjectResponseDTO]],
            summary="查询所有项目",
            description="查询所有项目信息")
def get_all_projects(service: ProjectService = Depends(get_service)):
    entities = service.get_all_projects()
    dtos = [ProjectResponseDTO(**e.__dict__) for e in entities]
    return Res(data=dtos, code=200, message="查询成功")


# ------------------- 修改项目 -------------------
@router.put("/{project_id}", response_model=Res[ProjectCreateDTO],
            summary="修改项目",
            description="根据项目ID修改项目信息")
def update_project(project_id: int, dto: ProjectCreateDTO, service: ProjectService = Depends(get_service)):

    # 先根据id进行查找
    project = service.get_project(project_id)
    if not project:
        return Res(data=None, code=400, message="项目不存在")

    success = service.update_project(project_id,dto.dict())
    if success:
        return Res(data=dto, code=200, message="更新成功")
    else:
        return Res(data=None, code=400, message="更新失败")


# ------------------- 删除项目 -------------------
@router.delete("/{project_id}", response_model=Res,
               summary="删除项目",
               description="根据项目ID删除项目,并且级联删除项目下所有章节以及内容")
def delete_project(project_id: int, service: ProjectService = Depends(get_service), chapter_service: ChapterService = Depends(get_chapter_service),role_service: RoleService = Depends(get_role_service)):

    # 级联删除项目所有相关内容，比如项目下所有章节以及内容
    entities = chapter_service.get_all_chapters(project_id)
    for entity in entities:
        chapter_service.delete_chapter(entity.id)
    #     删除project目录
    project = service.get_project(project_id)
    if not project:
        return Res(data=None, code=404, message="项目不存在")

    project_path = os.path.join(project.project_root_path, str(project_id))
    if os.path.exists(project_path):
        shutil.rmtree(project_path)  # 删除整个文件夹及其所有内容
        logging.info("已删除目录及内容: %s", project_path)
    else:
        logging.info("目录不存在: %s", project_path)

    # 还要删除角色库中projet下的所有角色
    roles = role_service.get_all_roles(project_id)
    for role in roles:
        role_service.delete_role(role.id)
    success = service.delete_project(project_id)
    if success:
        return Res(data=None, code=200, message="删除成功")
    else:
        return Res(data=None, code=400, message="删除失败或项目不存在")

# 直接导入整本小说内容，然后解析，创建章节
@router.post("/{project_id}/import")
def import_project(project_id: int, dto: ProjectImportDTO,service: ProjectService = Depends(get_service),
                   chapter_service: ChapterService = Depends(get_chapter_service)):

    content = dto.content
    # 删除该项目下的所有章节
    # chapters = chapter_service.get_all_chapters(project_id)
    # for chapter in chapters:
    #     chapter_service.delete_chapter(chapter.id)
    # 解析content
    chapter_contents = service.parse_content(content)
    if len(chapter_contents) == 0:
        return Res(code=400, message="导入失败")

    # 批量创建章节
    for chapter_content in chapter_contents:
        name = chapter_content["chapter_name"]
        content = chapter_content["content"]
        logging.info("批量创建章节 %s", name)
        chapter_service.create_chapter(ChapterEntity(project_id=project_id, title=name, text_content=content))
    return Res(code=200, message="导入成功")


def _is_speakable_line(line) -> bool:
    line_type = (line.line_type or "").lower()
    track = (line.track or "").lower()
    return line.should_speak != 0 and line_type not in {"sfx", "bgm"} and track not in {"sfx", "bgm"}


def _audio_ready(path: str | None) -> bool:
    if not path:
        return False
    if str(path).startswith(("http://", "https://")):
        return True
    return os.path.exists(os.path.abspath(os.path.expanduser(str(path))))


def _line_ref(line) -> dict:
    return {
        "line_id": line.id,
        "chapter_id": line.chapter_id,
        "line_order": line.line_order,
        "track": line.track,
        "line_type": line.line_type,
        "text": line.text_content,
        "sound_prompt": line.sound_prompt,
        "audio_path": line.audio_path,
        "status": line.status,
        "production_note": line.production_note,
        "is_placeholder_material": _is_material_placeholder(line),
    }


def _issue(level: str, title: str, detail: str, action: str) -> dict:
    return {
        "level": level,
        "title": title,
        "detail": detail,
        "action": action,
    }


def _material_placeholder_path(project, line) -> str:
    if line.audio_path:
        return os.path.abspath(os.path.expanduser(line.audio_path))
    root = project.project_root_path or os.path.join(getConfigPath(), "projects")
    return os.path.join(
        os.path.abspath(os.path.expanduser(root)),
        str(project.id),
        str(line.chapter_id),
        "audio",
        f"id_{line.id}_material_placeholder.wav",
    )


def _is_material_placeholder(line) -> bool:
    note = getattr(line, "production_note", None) or ""
    path = getattr(line, "audio_path", None) or ""
    return PLACEHOLDER_MATERIAL_MARKER in note or "_material_placeholder" in os.path.basename(str(path))


def _with_placeholder_note(note: str | None) -> str:
    note = (note or "").strip()
    if PLACEHOLDER_MATERIAL_MARKER in note:
        return note
    suffix = "制作占位音频，正式成片前请替换真实音效/BGM。"
    return f"{note}\n{PLACEHOLDER_MATERIAL_MARKER} {suffix}".strip()


def _create_material_placeholder_audio(line, target_path: str) -> str:
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    sr = 44100
    track = (line.track or line.line_type or "sfx").lower()
    text = f"{line.text_content or ''} {line.sound_prompt or ''}"
    seed = int(hashlib.md5(f"{line.id}:{text}".encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)

    if track == "bgm":
        duration = min(14.0, max(8.0, len(text) / 18.0))
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        base = 55 + seed % 45
        signal = (
            0.055 * np.sin(2 * np.pi * base * t)
            + 0.026 * np.sin(2 * np.pi * (base * 1.5) * t)
            + 0.010 * rng.normal(0, 1, t.shape)
        )
        envelope = np.minimum(1.0, np.linspace(0, 1, t.size) * 4)
        envelope *= np.minimum(1.0, np.linspace(1, 0, t.size) * 4)
        signal *= envelope
    else:
        duration = min(6.0, max(1.6, len(text) / 20.0))
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        noise = rng.normal(0, 0.045, t.shape)
        tone = 0.025 * np.sin(2 * np.pi * (180 + seed % 420) * t)
        envelope = np.exp(-np.linspace(0, 4.2, t.size))
        attack = np.minimum(1.0, np.linspace(0, 1, t.size) * 16)
        signal = (noise + tone) * envelope * attack

    stereo = np.column_stack([signal, signal * 0.92])
    sf.write(target_path, stereo.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return target_path

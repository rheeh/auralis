# app/main.py
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from app.core.config import getConfigPath
from app.core.prompts import get_prompt_str
from app.core.tts_runtime import tts_worker
from app.core.ws_manager import manager
from app.db.database import Base, engine, SessionLocal, get_db
from app.db.migrations import apply_schema_migrations
from app.entity.emotion_entity import EmotionEntity
from app.entity.strength_entity import StrengthEntity
from app.core.tts_guidance import EMOTION_NAMES, STRENGTH_NAMES
from app.models.po import *
from app.repositories.llm_provider_repository import LLMProviderRepository
from app.repositories.tts_provider_repository import TTSProviderRepository
from app.routers import project_router, chapter_router, role_router, voice_router, llm_provider_router, \
    tts_provider_router, line_router, emotion_router, strength_router, multi_emotion_voice_router, prompt_router, \
    drama_adaptation_router, queue_router, chat_router
from app.routers import sound_library_router, timeline_router
from app.routers.chapter_router import get_strength_service, get_prompt_service, get_project_service
from app.routers.emotion_router import get_emotion_service
from app.routers.llm_provider_router import get_llm_service
from app.services.llm_provider_service import LLMProviderService

from app.services.tts_provider_service import TTSProviderService

import os
import sys

root_path = os.getcwd()
sys.path.append(root_path)

# =========================
# 日志配置（同时输出到控制台和文件）
# =========================
log_file_path = os.path.join(getConfigPath(), "app.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler(log_file_path, encoding='utf-8')  # 文件输出
    ]
)
logging.info(f"日志文件路径: {log_file_path}")

# =========================
# FastAPI 实例
# =========================
app = FastAPI(
    title="Auralis - AI Radio Drama Studio",
    description="面向个人创作的 AI 广播剧制作系统，支持小说改编、多角色台本、混合 TTS、素材轨和音频导出。",
    version="0.4.0",
)
# 跨域
# 允许的前端地址
origins = [
    "http://localhost:5173",  # Vue 开发服务器
    "http://127.0.0.1:5173"   # 有些浏览器可能会用这个
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # 允许的源
    allow_credentials=True,
    allow_methods=["*"],          # 允许所有方法（GET, POST, DELETE...）
    allow_headers=["*"],          # 允许所有请求头
)



# =========================
# 数据库初始化（创建表）
# =========================

# 启动时创建表
# @app.on_event("startup")
# def startup():
#     Base.metadata.create_all(bind=engine)

WORKERS = 1
QUEUE_CAPACITY = 0

def get_tts_service(db: Session = Depends(get_db)) -> TTSProviderService:
    return TTSProviderService(TTSProviderRepository(db))

@app.on_event("startup")
async def startup_event():
    # 1) 建表
    try:
        Base.metadata.create_all(bind=engine)
        apply_schema_migrations(engine)
    except Exception as e:
        logging.exception("❌ 数据库建表失败: %s", e)
        raise RuntimeError("Auralis 数据库迁移失败，已阻止应用继续启动") from e

    # 2) 初始化共享运行时
    try:
        manager.bind_loop(asyncio.get_running_loop())
        app.state.tts_queue = asyncio.Queue(maxsize=QUEUE_CAPACITY)
        app.state.tts_executor = ThreadPoolExecutor(max_workers=WORKERS)
    except Exception as e:
        logging.exception("❌ 初始化队列/线程池失败: %s", e)

    # 3) 启动后台 worker
    try:
        app.state.tts_workers = [
            asyncio.create_task(tts_worker(app)) for _ in range(WORKERS)
        ]
    except Exception as e:
        logging.exception("❌ 启动 worker 失败: %s", e)

    # 4) 初始化默认数据
    db = SessionLocal()
    try:
        try:
            tts_service = get_tts_service(db)
            tts_service.create_default_tts_provider()
        except Exception as e:
            logging.warning("⚠️ 默认 TTS provider 初始化失败: %s", e)

        try:
            emotion_service = get_emotion_service(db)
            for name in EMOTION_NAMES:
                try:
                    emotion_service.create_emotion(EmotionEntity(name=name))
                except Exception as e:
                    logging.debug("情绪 %s 已存在或创建失败: %s", name, e)
        except Exception as e:
            logging.warning("⚠️ 情绪初始化失败: %s", e)

        try:
            strength_service = get_strength_service(db)
            for name in STRENGTH_NAMES:
                try:
                    strength_service.create_strength(StrengthEntity(name=name))
                except Exception as e:
                    logging.debug("强度 %s 已存在或创建失败: %s", name, e)
        except Exception as e:
            logging.warning("⚠️ 强度初始化失败: %s", e)

        try:
            calm = db.query(EmotionPO).filter(EmotionPO.name == "平静").first()
            medium = db.query(StrengthPO).filter(StrengthPO.name == "中等").first()
            emotion_count = db.query(LinePO).filter(LinePO.should_speak == 1, LinePO.emotion_id.is_(None)).update(
                {LinePO.emotion_id: calm.id}, synchronize_session=False
            ) if calm else 0
            strength_count = db.query(LinePO).filter(LinePO.should_speak == 1, LinePO.strength_id.is_(None)).update(
                {LinePO.strength_id: medium.id}, synchronize_session=False
            ) if medium else 0
            stale_active_count = 0
            for line in db.query(LinePO).filter(LinePO.active_audio_variant_id.is_not(None)).all():
                active = next(
                    (item for item in (line.audio_variants or []) if item.get("id") == line.active_audio_variant_id),
                    None,
                )
                if not active or not os.path.isfile(os.path.abspath(os.path.expanduser(active.get("audio_path") or ""))):
                    line.active_audio_variant_id = None
                    stale_active_count += 1
            stale_generated_count = 0
            for line in db.query(LinePO).filter(LinePO.active_audio_version_id.is_not(None)).all():
                active = next(
                    (item for item in (line.audio_versions or []) if item.get("id") == line.active_audio_version_id),
                    None,
                )
                if not active or not os.path.isfile(os.path.abspath(os.path.expanduser(active.get("audio_path") or ""))):
                    line.active_audio_version_id = None
                    stale_generated_count += 1
            db.commit()
            if emotion_count or strength_count or stale_active_count or stale_generated_count:
                logging.info(
                    "已修复旧台词数据：情绪 %s 条，强度 %s 条，失效处理版本 %s 条，失效生成版本 %s 条",
                    emotion_count, strength_count, stale_active_count, stale_generated_count,
                )
        except Exception as e:
            db.rollback()
            logging.warning("⚠️ 旧台词情绪/强度补齐失败: %s", e)

    #     创建默认提示词
        try:
            prompt_service = get_prompt_service(db)
            if not prompt_service.get_all_prompts():
                logging.info("创建默认提示词")
                prompt_service.create_default_prompt()
            else:
                default_prompt =  prompt_service.get_prompt_by_name("默认拆分台词提示词")
                if not default_prompt:
                    prompt_service.create_default_prompt()
                else:
                    #修改默认提示词
                    default_prompt_content = get_prompt_str()
                    default_prompt.content = default_prompt_content
                    prompt_service.update_prompt(default_prompt.id, default_prompt.__dict__)

        except Exception as e:
            logging.warning("⚠️ 默认提示词创建失败: %s", e)
    # 兼容之前版本，已有的项目的project_root_path 为 getConfigPath()
        try:
            project_service = get_project_service(db)
            for project in project_service.get_all_projects():
                if not project.project_root_path:
                    project.project_root_path = getConfigPath()
                    project_service.update_project(project.id, project.__dict__)
                    logging.info("项目 %s 默认项目路径已修改为 %s", project.name, project.project_root_path)

        #             todo:修改所有的保存路径，然后前端请求添加保存路径（利用electron读取文件夹路径）
        except Exception as e:
            logging.warning("⚠️ 项目默认项目路径初始化失败: %s", e)

    except Exception as e:
        logging.exception("❌ 默认数据初始化异常: %s", e)
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown_event():
    # 优雅退出
    for t in getattr(app.state, "tts_workers", []):
        t.cancel()
    ex = getattr(app.state, "tts_executor", None)
    if ex:
        ex.shutdown(wait=False, cancel_futures=True)
# =========================
# 注册路由
# =========================
app.include_router(project_router.router)
app.include_router(chapter_router.router)
app.include_router(role_router.router)
app.include_router(voice_router.router)
app.include_router(llm_provider_router.router)
app.include_router(tts_provider_router.router)
app.include_router(line_router.router)
app.include_router(emotion_router.router)
app.include_router(strength_router.router)
app.include_router(multi_emotion_voice_router.router)
app.include_router(prompt_router.router)
app.include_router(drama_adaptation_router.router)
app.include_router(queue_router.router)
app.include_router(chat_router.router)
app.include_router(timeline_router.router)
app.include_router(sound_library_router.router)
# =========================
# 健康检查接口
# =========================
@app.get("/")
def read_root():
    return {"msg": "Auralis backend is running."}

# =========================
# 小测试接口：插入并查询 ProjectPO
# =========================
@app.get("/test-db")
def test_db():
    session: Session = SessionLocal()
    try:
        # 使用时间戳生成唯一名称，避免 UNIQUE 冲突
        name = f"测试项目_{int(datetime.now().timestamp())}"

        test_project = ProjectPO(name=name, description="测试用项目")
        session.add(test_project)
        session.commit()
        session.refresh(test_project)

        return {
            "msg": "插入成功",
            "id": test_project.id,
            "name": test_project.name,
            "created_at": test_project.created_at,
            "updated_at": test_project.updated_at
        }

    except Exception as e:
        session.rollback()
        return {"error": str(e)}

    finally:
        session.close()


import json
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    project_id_raw = ws.query_params.get("project_id")
    project_id = int(project_id_raw) if project_id_raw and project_id_raw.isdigit() else None
    await manager.connect(ws, project_id=project_id)
    logging.info("WebSocket 客户端已连接")
    try:
        while True:
            msg_text = await ws.receive_text()
            try:
                data = json.loads(msg_text)
            except json.JSONDecodeError:
                data = {}

            # 👇 心跳处理：收到 ping 立即回复 pong
            if data.get("type") == "ping":
                logging.debug("receive ping")
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

            # 这里可以扩展处理订阅/其他消息

    except WebSocketDisconnect:
        logging.info("WebSocket 客户端主动断开")
        manager.disconnect(ws)
    except Exception as exc:
        logging.warning("WebSocket 连接异常: %s", exc)
        manager.disconnect(ws)


@app.websocket("/ws/projects/{project_id}/sessions/{session_id}")
async def workflow_ws_endpoint(ws: WebSocket, project_id: int, session_id: str):
    db = SessionLocal()
    try:
        session = db.get(ChatSessionPO, session_id)
        if not session or session.project_id != project_id or session.deleted_at is not None:
            await ws.close(code=4404)
            return
    finally:
        db.close()

    await manager.connect_session(ws, project_id, session_id)
    logging.info("工作流 WebSocket 已连接: project=%s session=%s", project_id, session_id)
    try:
        while True:
            msg_text = await ws.receive_text()
            try:
                data = json.loads(msg_text)
            except json.JSONDecodeError:
                data = {}
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong", "session_id": session_id})
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logging.warning("工作流 WebSocket 连接异常: %s", exc)
        manager.disconnect(ws)



if __name__ == "__main__":

    # uvicorn.run(app, host="127.0.0.1", port=8200)
    # 使用自定义 logger，避免 uvicorn 自动配置失败
    # logging.basicConfig(level=logging.INFO)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8200, log_config=None)

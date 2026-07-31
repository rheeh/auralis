
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, Enum, ForeignKey, DateTime, JSON, Index, UniqueConstraint
from datetime import datetime, timezone

from app.db.database import Base


# ------------------------------
# 1. 项目表 projects
# ------------------------------
class ProjectPO(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True,index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    llm_provider_id = Column(Integer, nullable=True)  # LLM提供商
    llm_model = Column(String(255), nullable=True)  # 指定模型
    tts_provider_id = Column(Integer, nullable=True)  # TTS提供商
    prompt_id = Column(Integer, nullable=True) # 关联的prompt
    # 是否开启精准填充
    is_precise_fill = Column(Integer, default=0, nullable=False)
    # 项目根地址
    project_root_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# ------------------------------
# 2. 项目的全局角色表 roles
# ------------------------------
class RolePO(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True,index=True)
    project_id = Column(Integer,  nullable=False)
    name = Column(String(100), nullable=False)
    default_voice_id = Column(Integer, ForeignKey("voices.id"), nullable=True)
    role_importance = Column(String(50), default="supporting", nullable=False)
    tts_route = Column(String(50), default="auto", nullable=False)
    edge_voice = Column(String(100), nullable=True)
    avatar_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# ------------------------------
# 3. 音色表 voices
# ------------------------------
class VoicePO(Base):
    __tablename__ = "voices"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    tts_provider_id = Column(Integer, nullable=True)
    name = Column(String(100), nullable=False)
    reference_path = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    # 是否包含多情绪
    is_multi_emotion = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)

# 多情绪表
class MultiEmotionVoicePO(Base):
    __tablename__ = "multi_emotion"
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    voice_id = Column(Integer, nullable=False)
    emotion_id = Column(Integer, nullable=False)
    strength_id = Column(Integer, nullable=True)
    reference_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)

# ------------------------------
# 4. 章节表 chapters
# ------------------------------
class ChapterPO(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True,index=True)
    project_id = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    order_index = Column(Integer, nullable=True)
    text_content = Column(Text, nullable=True)  # SQLite 没有 LongText，用 Text 替代
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)



# ------------------------------
# 5. 台词表 lines
# ------------------------------
# 情绪枚举表
class EmotionPO(Base):
    __tablename__ = "emotions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now())

# 情绪强弱枚举表
class StrengthPO(Base):
    __tablename__ = "strengths"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now())


class LinePO(Base):
    __tablename__ = "lines"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 外键
    chapter_id = Column(Integer, nullable=False, index=True)
    role_id = Column(Integer, nullable=True)
    voice_id = Column(Integer,  nullable=True)

    # 核心信息
    line_order = Column(Integer, nullable=True, index=True)
    text_content = Column(Text, nullable=True)
    line_type = Column(String(50), default="dialogue", nullable=False)
    track = Column(String(50), default="voice", nullable=False)
    should_speak = Column(Integer, default=1, nullable=False)
    scene_title = Column(String(255), nullable=True)
    sound_prompt = Column(Text, nullable=True)
    voice_profile = Column(Text, nullable=True)
    production_note = Column(Text, nullable=True)
    audio_events = Column(JSON, nullable=True)
    audio_versions = Column(JSON, nullable=True)
    active_audio_version_id = Column(String(64), nullable=True)
    audio_variants = Column(JSON, nullable=True)
    active_audio_variant_id = Column(String(64), nullable=True)
    # 情绪 和 强弱
    emotion_id = Column(Integer, nullable=True)
    strength_id = Column(Integer, nullable=True)

    # 9.1 新增


    # 输出资源
    audio_path = Column(String(500), nullable=True)
    subtitle_path = Column(String(500), nullable=True)

    # 间隔停留时间（秒）
    # wait_time = Column(Integer, default=0, nullable=True)

    # 状态
    status = Column(
        Enum("pending", "processing", "done", "failed", name="line_status"),
        default="pending",
        nullable=False
    )
    # 是否完成
    is_done = Column(Integer, default=0, nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (
        Index("idx_chapter_order", "chapter_id", "line_order"),
    )


class AdaptationRunPO(Base):
    __tablename__ = "adaptation_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    title = Column(String(255), nullable=False)
    source_kind = Column(String(50), default="novel", nullable=False)
    source_text = Column(Text, nullable=True)
    instruction = Column(Text, nullable=True)
    scene_count = Column(Integer, default=4, nullable=False)
    adaptation_density = Column(String(50), default="balanced", nullable=False)
    status = Column(
        Enum("pending", "running", "script_ready", "committed", "failed", name="adaptation_status"),
        default="pending",
        nullable=False,
    )
    current_stage = Column(String(100), default="created", nullable=False)
    error_message = Column(Text, nullable=True)
    parsed_json = Column(JSON, nullable=True)
    draft_json = Column(JSON, nullable=True)
    review_json = Column(JSON, nullable=True)
    final_json = Column(JSON, nullable=True)
    session_id = Column(String(64), nullable=True, index=True)
    is_conversational = Column(Boolean, default=False, nullable=False)
    source_revision = Column(Integer, default=1, nullable=False)
    draft_revision = Column(Integer, default=1, nullable=False)
    committed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ChatSessionPO(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(64), primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    adaptation_run_id = Column(Integer, ForeignKey("adaptation_runs.id"), nullable=True, index=True)
    status = Column(String(32), default="active", nullable=False, index=True)
    current_stage = Column(String(64), default="created", nullable=False)
    active_confirm_type = Column(String(32), nullable=True)
    title = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    instruction = Column(Text, nullable=True)
    pending_confirm_json = Column(JSON, nullable=True)
    last_error_code = Column(String(80), nullable=True)
    last_error_message = Column(Text, nullable=True)
    last_event_sequence = Column(Integer, default=0, nullable=False)
    running_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_chat_session_project_updated", "project_id", "updated_at"),
        Index("idx_chat_session_project_status", "project_id", "status"),
        Index("idx_chat_session_chapter_status", "chapter_id", "status"),
    )


class SourceDocumentPO(Base):
    __tablename__ = "source_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ChatMessagePO(Base):
    __tablename__ = "chat_messages"

    id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    message_type = Column(String(32), default="text", nullable=False)
    content = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=True)
    client_request_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "client_request_id", name="uq_chat_message_request"),
        Index("idx_chat_message_session_created", "session_id", "created_at"),
    )


class AdaptationDraftRevisionPO(Base):
    __tablename__ = "adaptation_draft_revisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("adaptation_runs.id"), nullable=False, index=True)
    draft_type = Column(String(32), nullable=False)
    revision = Column(Integer, nullable=False)
    payload_json = Column(JSON, nullable=False)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "draft_type", "revision", name="uq_draft_revision"),
    )


class WorkflowEventPO(Base):
    __tablename__ = "workflow_events"

    id = Column(String(64), primary_key=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False)
    stage = Column(String(64), nullable=False)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_workflow_event_sequence"),
        Index("idx_workflow_event_session_created", "session_id", "created_at"),
    )


class AudioTaskPO(Base):
    __tablename__ = "audio_tasks"

    id = Column(String(64), primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=False, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=False, index=True)
    status = Column(String(32), default="queued", nullable=False, index=True)
    attempt = Column(Integer, default=1, nullable=False)
    error_code = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)
    audio_path = Column(String(500), nullable=True)
    review_status = Column(String(32), default="pending", nullable=False)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_audio_task_session_status", "session_id", "status"),
        Index("idx_audio_task_chapter_status", "chapter_id", "status"),
    )


class AudioAssetPO(Base):
    """统一登记可进入广播剧工程的音频文件。"""

    __tablename__ = "audio_assets"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=True, index=True)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=True, index=True)
    asset_type = Column(String(32), nullable=False, index=True)
    path = Column(String(1000), nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    sample_rate = Column(Integer, nullable=True)
    channels = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    checksum = Column(String(64), nullable=True, index=True)
    source_asset_id = Column(Integer, ForeignKey("audio_assets.id"), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_audio_asset_project_path"),
        Index("idx_audio_asset_project_type", "project_id", "asset_type"),
    )


class TimelineTrackPO(Base):
    """章节下固定的四类广播剧轨道。"""

    __tablename__ = "timeline_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=False, index=True)
    track_type = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("chapter_id", "track_type", name="uq_timeline_track_chapter_type"),
        Index("idx_timeline_track_project_chapter", "project_id", "chapter_id"),
    )


class TimelineClipPO(Base):
    """时间线中的实际音频片段；第一版只由服务自动生成，暂不允许 UI 拖动。"""

    __tablename__ = "timeline_clips"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    chapter_id = Column(Integer, nullable=False, index=True)
    track_id = Column(Integer, ForeignKey("timeline_tracks.id"), nullable=False, index=True)
    line_id = Column(Integer, ForeignKey("lines.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("audio_assets.id"), nullable=False, index=True)
    track_type = Column(String(32), nullable=False, index=True)
    start_ms = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    volume_db = Column(Float, nullable=False, default=0.0)
    fade_in_ms = Column(Integer, nullable=False, default=0)
    fade_out_ms = Column(Integer, nullable=False, default=0)
    is_muted = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_timeline_clip_chapter_start", "chapter_id", "start_ms"),
        Index("idx_timeline_clip_track_start", "track_id", "start_ms"),
    )

# -------------------------
# LLMProviderPO
# -------------------------
class LLMProviderPO(Base):
    __tablename__ = "llm_provider"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)           # 提供商名称
    api_base_url = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=True)                      # 可加密存储
    model_list = Column(JSON, nullable=True)                           # 支持的模型列表
    status = Column(Integer, default=1, nullable=False)               # 启用/禁用

    # ✅ 自定义参数（默认包含 response_format、temperature、top_p）
    custom_params = Column(
        Text,
        nullable=False,
        default=lambda: {
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "top_p": 0.9

        }
    )
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)


# -------------------------
# TTSProviderPO
# -------------------------
class TTSProviderPO(Base):
    __tablename__ = "tts_provider"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    api_base_url = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=True)
    provider_type = Column(String(50), default="cloud", nullable=False)
    model = Column(String(255), nullable=True)
    custom_params = Column(Text, nullable=True)
    # voice_list = Column(JSON, nullable=True)
    status = Column(Integer, default=1, nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)


class PromptPO(Base):
    __tablename__ = "prompts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    task = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),nullable=False)


# -------------------------
# ProjectSettings
# -------------------------
# class ProjectSettings(Base):
#     __tablename__ = "project_settings"
#
#     id = Column(Integer, primary_key=True, index=True, autoincrement=True)
#     project_id = Column(Integer, nullable=False)                  # 所属项目
#     llm_provider_id = Column(Integer, nullable=True)              # LLM提供商
#     llm_model = Column(String(255), nullable=True)                   # 指定模型
#     tts_provider_id = Column(Integer, nullable=True)              # TTS提供商
#
#     # 时间戳
#     created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
#     updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc),
#                         nullable=False)

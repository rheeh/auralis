import os
import shutil
import sys
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


LANGGRAPH_ENABLED = _env_bool("LANGGRAPH_ENABLED", True)
LANGGRAPH_CHAT_UI_ENABLED = _env_bool("LANGGRAPH_CHAT_UI_ENABLED", True)
LANGGRAPH_TTS_REVIEW_ENABLED = _env_bool("LANGGRAPH_TTS_REVIEW_ENABLED", True)
DRAMA_GRAPH_MAX_ITERATIONS = int(os.environ.get("DRAMA_GRAPH_MAX_ITERATIONS", "8"))
DRAMA_GRAPH_MAX_SOURCE_CHARS = int(os.environ.get("DRAMA_GRAPH_MAX_SOURCE_CHARS", "120000"))
DRAMA_GRAPH_MAX_DRAFT_CHARS = int(os.environ.get("DRAMA_GRAPH_MAX_DRAFT_CHARS", "180000"))
CHAT_SESSION_EXPIRE_DAYS = int(os.environ.get("CHAT_SESSION_EXPIRE_DAYS", "30"))
CHAT_EVENT_REPLAY_LIMIT = int(os.environ.get("CHAT_EVENT_REPLAY_LIMIT", "100"))


def validate_langgraph_runtime() -> None:
    if LANGGRAPH_ENABLED and sys.version_info < (3, 10):
        raise RuntimeError(
            "对话式改编需要 Python 3.10 或更高版本；请使用 scripts/dev.sh 创建 Python 3.12 环境。"
        )
# 得到默认配置文件
def getConfigPath():
    override_dir = os.environ.get("AURALIS_CONFIG_DIR")
    if override_dir:
        os.makedirs(override_dir, exist_ok=True)
        return override_dir

    # 用户目录下的 Auralis 工作目录
    user_dir = os.path.join(os.path.expanduser("~"), "Auralis")

    # 如果目录不存在，创建它
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)

    # 返回 config.json 路径（目录已保证存在）
    return user_dir


def getLangGraphCheckpointPath() -> str:
    configured = os.environ.get("LANGGRAPH_CHECKPOINT_DB")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path(getConfigPath()) / path
    else:
        path = Path(getConfigPath()) / "auralis-checkpoints.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)

def getFfmpegPath():
    BASE_DIR = getattr(sys, "_MEIPASS", Path(os.path.abspath(".")))
    FFMPEG_PATH = os.path.join(BASE_DIR, "core", "ffmpeg", "ffmpeg.exe")
    if os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return shutil.which("ffmpeg") or FFMPEG_PATH

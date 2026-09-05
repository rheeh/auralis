"""Audio metadata with compressed codecs isolated from the server process."""
import json
import shutil
import subprocess
from pathlib import Path

import soundfile as sf


def probe_audio(path: Path) -> tuple[int, int | None, int | None]:
    # Concurrent MP3 probing can crash libsndfile's MPEG initialization on
    # macOS. Probe compressed formats in a child process, isolating codecs.
    if path.suffix.lower() in {".wav", ".flac"}:
        try:
            info = sf.info(str(path))
            duration_ms = round((info.frames / info.samplerate) * 1000) if info.samplerate else 0
            return duration_ms, int(info.samplerate or 0) or None, int(info.channels or 0) or None
        except (RuntimeError, ValueError):
            pass
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError(f"无法解析音频文件: {path.name}，请安装 FFmpeg")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "format=duration:stream=sample_rate,channels", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=15,
        )
        data = json.loads(result.stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = float(data.get("format", {}).get("duration") or 0)
        return round(duration * 1000), int(stream.get("sample_rate") or 0) or None, int(stream.get("channels") or 0) or None
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise ValueError(f"无法解析音频文件: {path.name}") from exc

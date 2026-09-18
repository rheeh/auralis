"""Local FFmpeg transformations; plain paths/numbers in, files out."""
import os
import sys
import subprocess
import tempfile
import numpy as np
import soundfile as sf
from app.core.config import getFfmpegPath

def _convert_audio_to_wav(source_path: str, target_path: str, sr: int = 44100, ch: int = 2) -> str:
    if not os.path.exists(source_path):
        raise FileNotFoundError(source_path)
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    cmd = [
        getFfmpegPath(),
        "-y",
        "-i",
        source_path,
        "-vn",
        "-ar",
        str(sr),
        "-ac",
        str(ch),
        "-c:a",
        "pcm_s16le",
        target_path,
    ]
    subprocess.run(
        cmd,
        check=True, timeout=300,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return target_path

def process_audio_ffmpeg(
        audio_path: str,
        speed: float = 1.0,
        volume: float = 1.0,
        start_ms: int | None = None,
        end_ms: int | None = None,
        out_path: str | None = None,
        keep_format: bool = True,  # 是否保持原文件采样率/声道
        default_sr: int = 44100,
        default_ch: int = 2
):
    """
    使用 ffmpeg 对音频进行变速 (0.5~2.0)、音量调整、可选裁剪。
    输出 WAV PCM16。
    如果 keep_format=True，则保持输入文件的 sr/ch 不变。
    """
    ffmpeg_path = getFfmpegPath()
    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    # 获取原始参数
    info = sf.info(audio_path)
    target_sr = info.samplerate if keep_format else default_sr
    target_ch = info.channels if keep_format else default_ch

    # 参数规整
    speed = float(np.clip(speed or 1.0, 0.5, 2.0))
    volume = 1.0 if volume is None else max(0.0, float(volume))

    # 输出路径
    target_path = out_path or audio_path
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav",
                                     dir=os.path.dirname(target_path) or ".") as tmp:
        tmp_path = tmp.name

    # 构建 ffmpeg 命令
    filter_chain = [f"atempo={speed}"]
    if abs(volume - 1.0) > 1e-6:
        filter_chain.append(f"volume={volume}")

    cmd = [ffmpeg_path, "-y"]
    if start_ms is not None:
        cmd.extend(["-ss", str(start_ms / 1000)])
    cmd.extend(["-i", audio_path])
    if end_ms is not None:
        cmd.extend(["-to", str(end_ms / 1000)])
    cmd.extend([
        "-af", ",".join(filter_chain),
        "-ar", str(target_sr),
        "-ac", str(target_ch),
        "-c:a", "pcm_s16le",
        tmp_path
    ])

    subprocess.run(cmd, check=True, timeout=300,
                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

    # 软限幅：避免 clipping
    data, sr = sf.read(tmp_path, dtype="float32", always_2d=True)
    peak = float(np.max(np.abs(data)))
    if peak > 1.0:
        data = data / peak
        sf.write(tmp_path, data, sr, format="WAV", subtype="PCM_16")

    os.replace(tmp_path, target_path)
    return target_path

def process_audio_ffmpeg_cut(
        audio_path: str,
        speed: float = 1.0,
        volume: float = 1.0,
        start_ms: int | None = None,
        end_ms: int | None = None,
        silence_sec: float = 0.0,  # 末尾静音时长，单位秒
        out_path: str | None = None,
        keep_format: bool = True,  # 是否保持原文件采样率/声道
        default_sr: int = 44100,
        default_ch: int = 2
):
    """
    使用 ffmpeg 对音频进行变速 (0.5~2.0)、音量调整。
    删除 [start_ms, end_ms] 区间，并拼接前后音频。
    输出 WAV PCM16。
    可在末尾附加 silence_sec 秒静音。
    """
    ffmpeg_path = getFfmpegPath()
    if not os.path.exists(audio_path):
        raise FileNotFoundError(audio_path)

    # 获取原始参数
    info = sf.info(audio_path)
    target_sr = info.samplerate if keep_format else default_sr
    target_ch = info.channels if keep_format else default_ch

    # 参数规整
    speed = float(np.clip(speed or 1.0, 0.5, 2.0))
    volume = 1.0 if volume is None else max(0.0, float(volume))

    # 输出路径
    target_path = out_path or audio_path
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav",
                                     dir=os.path.dirname(target_path) or ".") as tmp:
        tmp_path = tmp.name

    # 构建 ffmpeg 命令
    if start_ms is None or end_ms is None or end_ms <= start_ms:
        # 无剪切
        if silence_sec > 0:
            # 添加静音
            cmd = [
                ffmpeg_path, "-y",
                "-i", audio_path,
                "-f", "lavfi", "-t", str(silence_sec),
                "-i", f"anullsrc=channel_layout={'stereo' if target_ch == 2 else 'mono'}:sample_rate={target_sr}",
                "-filter_complex",
                f"[0:a]atempo={speed},volume={volume}[main];"
                f"[main][1:a]concat=n=2:v=0:a=1[out]",
                "-map", "[out]",
                "-ar", str(target_sr),
                "-ac", str(target_ch),
                "-c:a", "pcm_s16le",
                tmp_path
            ]
        elif silence_sec < 0:
            # 裁掉末尾 abs(silence_sec)
            cut_dur = info.duration + silence_sec
            if cut_dur <= 0:
                cut_dur = 0  # 整段裁掉

            cmd = [
                ffmpeg_path, "-y",
                "-i", audio_path,
                "-filter_complex",
                f"[0:a]atempo={speed},volume={volume},atrim=0:{cut_dur}[out]",
                "-map", "[out]",
                "-ar", str(target_sr),
                "-ac", str(target_ch),
                "-c:a", "pcm_s16le",
                tmp_path
            ]
        else:
            # 不处理末尾
            cmd = [
                ffmpeg_path, "-y", "-i", audio_path,
                "-af", f"atempo={speed},volume={volume}",
                "-ar", str(target_sr),
                "-ac", str(target_ch),
                "-c:a", "pcm_s16le",
                tmp_path
            ]


    else:

        # 剪切

        start_sec = start_ms / 1000

        end_sec = end_ms / 1000

        if silence_sec > 0:

            # 拼接 + 添加静音

            cmd = [

                ffmpeg_path, "-y",

                "-i", audio_path,

                "-f", "lavfi", "-t", str(silence_sec),

                "-i", f"anullsrc=channel_layout={'stereo' if target_ch == 2 else 'mono'}:sample_rate={target_sr}",

                "-filter_complex",

                f"[0:a]atrim=0:{start_sec},asetpts=PTS-STARTPTS[first];"

                f"[0:a]atrim={end_sec},asetpts=PTS-STARTPTS[second];"

                f"[first][second]concat=n=2:v=0:a=1,atempo={speed},volume={volume}[main];"

                f"[main][1:a]concat=n=2:v=0:a=1[out]",

                "-map", "[out]",

                "-ar", str(target_sr),

                "-ac", str(target_ch),

                "-c:a", "pcm_s16le",

                tmp_path

            ]

        elif silence_sec < 0:

            # 拼接后再裁掉末尾

            cut_dur = info.duration + silence_sec
            if cut_dur <= 0:
                cut_dur = 0  # 整段裁掉

            cmd = [

                ffmpeg_path, "-y", "-i", audio_path,

                "-filter_complex",

                f"[0:a]atrim=0:{start_sec},asetpts=PTS-STARTPTS[first];"

                f"[0:a]atrim={end_sec},asetpts=PTS-STARTPTS[second];"

                f"[first][second]concat=n=2:v=0:a=1,atempo={speed},volume={volume},atrim=0:{cut_dur}[out]",

                "-map", "[out]",

                "-ar", str(target_sr),

                "-ac", str(target_ch),

                "-c:a", "pcm_s16le",

                tmp_path

            ]

        else:

            # 拼接但不处理末尾

            cmd = [

                ffmpeg_path, "-y", "-i", audio_path,

                "-filter_complex",

                f"[0:a]atrim=0:{start_sec},asetpts=PTS-STARTPTS[first];"

                f"[0:a]atrim={end_sec},asetpts=PTS-STARTPTS[second];"

                f"[first][second]concat=n=2:v=0:a=1,atempo={speed},volume={volume}[out]",

                "-map", "[out]",

                "-ar", str(target_sr),

                "-ac", str(target_ch),

                "-c:a", "pcm_s16le",

                tmp_path

            ]

    # 执行 ffmpeg
    subprocess.run(
        cmd, check=True, timeout=300,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    # 软限幅：避免 clipping
    data, sr = sf.read(tmp_path, dtype="float32", always_2d=True)
    peak = float(np.max(np.abs(data)))
    if peak > 1.0:
        data = data / peak
        sf.write(tmp_path, data, sr, format="WAV", subtype="PCM_16")

    os.replace(tmp_path, target_path)
    return target_path

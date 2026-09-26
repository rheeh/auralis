from __future__ import annotations

import re
from typing import Final


BASE_EMOTIONS: Final[tuple[str, ...]] = (
    "高兴", "生气", "伤心", "害怕", "厌恶", "低落", "惊喜", "平静",
)

EMOTION_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "积极与亲和": ("高兴", "开心", "兴奋", "欣慰", "温柔"),
    "愤怒与对抗": ("生气", "愤怒", "恼火", "不耐烦", "悲愤"),
    "悲伤与低落": ("伤心", "悲伤", "难过", "委屈", "低落"),
    "恐惧与紧张": ("害怕", "恐惧", "紧张", "惊慌", "焦急"),
    "厌恶与讽刺": ("厌恶", "嫌弃", "嘲讽"),
    "惊讶与疑惑": ("惊喜", "惊讶", "震惊", "疑惑"),
    "平稳与意志": ("平静", "克制", "冷静", "严肃", "坚定"),
}

EMOTION_NAMES: Final[tuple[str, ...]] = tuple(
    name for names in EMOTION_GROUPS.values() for name in names
)
STRENGTH_NAMES: Final[tuple[str, ...]] = ("微弱", "稍弱", "中等", "较强", "强烈")

EMOTION_COMPONENTS: Final[dict[str, dict[str, float]]] = {
    "高兴": {"高兴": 1.0},
    "开心": {"高兴": 1.0},
    "兴奋": {"高兴": 0.8, "惊喜": 0.5},
    "欣慰": {"高兴": 0.65, "平静": 0.55},
    "温柔": {"高兴": 0.25, "平静": 0.9},
    "生气": {"生气": 1.0},
    "愤怒": {"生气": 1.0},
    "恼火": {"生气": 0.8, "厌恶": 0.25},
    "不耐烦": {"生气": 0.55, "厌恶": 0.4},
    "悲愤": {"伤心": 1.0, "生气": 1.0},
    "伤心": {"伤心": 1.0},
    "悲伤": {"伤心": 1.0},
    "难过": {"伤心": 0.8, "低落": 0.35},
    "委屈": {"伤心": 0.8, "低落": 0.55},
    "低落": {"低落": 1.0},
    "害怕": {"害怕": 1.0},
    "恐惧": {"害怕": 1.0},
    "紧张": {"害怕": 0.7, "惊喜": 0.2},
    "惊慌": {"害怕": 0.9, "惊喜": 0.45},
    "焦急": {"害怕": 0.55, "生气": 0.25},
    "厌恶": {"厌恶": 1.0},
    "嫌弃": {"厌恶": 0.9},
    "嘲讽": {"高兴": 0.5, "厌恶": 1.0},
    "惊喜": {"惊喜": 1.0},
    "惊讶": {"惊喜": 0.9},
    "震惊": {"惊喜": 1.0, "害怕": 0.25},
    "疑惑": {"惊喜": 0.45, "平静": 0.55},
    "平静": {"平静": 1.0},
    "克制": {"平静": 0.9, "低落": 0.15},
    "冷静": {"平静": 1.0},
    "严肃": {"平静": 0.75, "生气": 0.2},
    "坚定": {"平静": 0.7, "生气": 0.2, "高兴": 0.15},
}

VECTOR_STRENGTH_SCALE: Final[dict[str, float]] = {
    "微弱": 0.2,
    "稍弱": 0.4,
    "中等": 0.6,
    "较强": 0.8,
    "强烈": 1.0,
}

EDGE_STRENGTH_SCALE: Final[dict[str, float]] = {
    "微弱": 0.1,
    "稍弱": 0.2,
    "中等": 0.35,
    "较强": 0.5,
    "强烈": 0.7,
}

EDGE_BASE_PROSODY: Final[dict[str, tuple[float, float]]] = {
    # rate percentage, pitch Hz; loudness is controlled separately.
    "高兴": (12, 10),
    "生气": (14, 6),
    "伤心": (-18, -10),
    "害怕": (12, 12),
    "厌恶": (-8, -8),
    "低落": (-22, -12),
    "惊喜": (18, 15),
    "平静": (0, 0),
}

# Product defaults for restrained dialogue, not vendor-calibrated intensity values.
DELIVERY_BY_STRENGTH: Final[dict[str, str]] = {
    "微弱": "按日常交谈回应，按完整短语连贯说出，语气自然",
    "稍弱": "像与对方日常交谈，按完整短语连贯表达，语气随意思自然变化",
    "中等": "以连贯交谈传达本句意图，情绪随语意自然流动",
    "较强": "按剧情要求表达关键转折，保持语流连贯和角色原有声线",
    "强烈": "按本句要求充分表达情感，保持语意连贯和角色原有声线",
}


def affirmative_guidance(note: str) -> str:
    """Conservative keyword input: skip negated clauses instead of reversing them.

    This is not a natural-language parser. Ambiguous clauses stay unmapped; native
    instruction models still receive the original, unmodified direction.
    """
    clauses = re.split(r"[，,。；;！!？?\n]|(?:但是|而是|但)", note)
    negative = re.compile(r"不要|不能|不可|不得|不必|无需|避免|别|不|勿|莫|无|未|禁止|切忌|忌|正常|照常|保持原")
    return "，".join(clause for clause in clauses if not negative.search(clause))


def emotion_text_to_vector(emotion: str, strength: str) -> list[float]:
    """Convert the selected emotion and emotional intensity into the legacy 8D vector."""
    scale = VECTOR_STRENGTH_SCALE.get(strength, VECTOR_STRENGTH_SCALE["中等"])
    vector = [0.0] * len(BASE_EMOTIONS)
    for base_name, weight in EMOTION_COMPONENTS.get(emotion, {}).items():
        vector[BASE_EMOTIONS.index(base_name)] = round(scale * weight, 4)
    return vector


def build_voice_instruction(
    emotion: str | None,
    strength: str | None,
    production_note: str | None,
    *,
    mode: str = "native",
    compact: bool = False,
) -> str:
    """Compile authoring labels into delivery cues for the resolved model/voice."""
    note = (production_note or "").strip()
    if mode == "none":
        return ""
    if mode in {"mapped", "structured"}:
        # Keep metadata separate from acting notes for deterministic adapters.
        return "。".join(part for part in (
            f"情绪：{emotion}" if emotion else "",
            f"情绪强度：{strength or '微弱'}",
            f"声音指导：{note}" if note else "",
        ) if part)

    selected_strength = strength if strength in DELIVERY_BY_STRENGTH else "微弱"
    strong = selected_strength in {"较强", "强烈"}
    if compact:
        # CosyVoice native instructions have a 100 weighted-character budget.
        # Put the delivery constraint first, so it survives provider truncation.
        delivery = "按要求表达，语意连贯" if strong else "日常交谈，按短语连贯表达"
        return "。".join(part for part in (delivery, note or (f"语气{emotion}" if strong and emotion else "")) if part)

    parts: list[str] = [DELIVERY_BY_STRENGTH[selected_strength]]
    # A categorical emotion word can trigger a full performance even when paired
    # with “微弱”. For subtle delivery, use the specific note without that label.
    if strong and emotion:
        parts.append(f"本句语气{emotion}")
    if note:
        parts.append(f"本句具体要求：{note}")
    parts.append("具体要求优先；只朗读台词正文，额外发声仅在具体要求明确提出时执行")
    return "。".join(parts)


def edge_prosody(
    emotion: str | None,
    strength: str | None,
    production_note: str | None,
) -> dict[str, str]:
    """Approximate expressive guidance with the only controls Edge exposes."""
    note = affirmative_guidance(production_note or "")
    selected_emotion = emotion if emotion in EMOTION_COMPONENTS else _emotion_from_note(note)
    components = EMOTION_COMPONENTS.get(selected_emotion or "", {"平静": 1.0})
    total_weight = sum(components.values()) or 1.0
    rate = sum(EDGE_BASE_PROSODY[name][0] * weight for name, weight in components.items()) / total_weight
    pitch = sum(EDGE_BASE_PROSODY[name][1] * weight for name, weight in components.items()) / total_weight
    # Emotional intensity is not loudness. Only explicit delivery controls volume.
    volume = 0

    selected_strength = strength if strength in EDGE_STRENGTH_SCALE else _strength_from_note(note)
    scale = EDGE_STRENGTH_SCALE.get(selected_strength or "", EDGE_STRENGTH_SCALE["微弱"])
    rate *= scale
    pitch *= scale
    if any(word in note for word in ("极慢", "非常慢", "特别慢")):
        rate = -35
    elif any(word in note for word in ("稍慢", "偏慢")):
        rate = min(rate, -6)
    elif any(word in note for word in ("放慢", "慢速", "语速慢")):
        rate = min(rate, -12)
    if any(word in note for word in ("极快", "非常快", "特别快")):
        rate = 35
    elif any(word in note for word in ("稍快", "偏快")):
        rate = max(rate, 6)
    elif any(word in note for word in ("加快", "快速", "急促", "语速快")):
        rate = max(rate, 12)

    if any(word in note for word in ("压低", "低沉", "低音")):
        pitch = min(pitch, -4)
    if any(word in note for word in ("提高音调", "高昂", "明亮", "高音")):
        pitch = max(pitch, 4)

    if "耳语" in note:
        volume = min(volume, -25)
    elif any(word in note for word in ("轻声", "小声", "降低音量")):
        volume = min(volume, -10)
    if any(word in note for word in ("大声", "提高音量", "响亮")):
        volume = max(volume, 15)

    return {
        "rate": _signed(round(_clamp(rate, -40, 40)), "%"),
        "pitch": _signed(round(_clamp(pitch, -25, 25)), "Hz"),
        "volume": _signed(round(_clamp(volume, -35, 25)), "%"),
    }


def _emotion_from_note(note: str) -> str | None:
    return next((name for name in EMOTION_NAMES if name in note), None)


def _strength_from_note(note: str) -> str | None:
    return next((name for name in STRENGTH_NAMES if name in note), None)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _signed(value: int, unit: str) -> str:
    return f"{value:+d}{unit}"

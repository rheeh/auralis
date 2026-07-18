from __future__ import annotations

from copy import deepcopy
from typing import Any


KNOWLEDGE_ROLE_VOICES: dict[str, dict[str, str]] = {
    "知夏": {
        "edge_voice": "zh-CN-XiaoyiNeural",
        "voice_profile": "年轻女声，清亮、真诚、好奇，避免播音腔",
        "production_note": "年轻女声，像真实想到问题后自然开口；关键词略加重，句尾不要机械下沉。",
    },
    "闻舟": {
        "edge_voice": "zh-CN-YunyangNeural",
        "voice_profile": "成熟男声，沉稳、有耐心、与女声形成明显反差",
        "production_note": "成熟男声，先回应对方再解释；结论清楚有力，避免新闻播报腔。",
    },
}


def enrich_dialogue_performance(script: dict[str, Any]) -> dict[str, Any]:
    """Fill stable gender voices and varied delivery metadata without changing spoken text."""
    enriched = deepcopy(script)
    if enriched.get("adaptation_mode") != "dialogue_lesson":
        return enriched

    roles = {str(item.get("name") or ""): item for item in enriched.get("roles", [])}
    enriched["roles"] = [
        {
            **roles.get(name, {}),
            "name": name,
            "gender": "female" if name == "知夏" else "male",
            "edge_voice": settings["edge_voice"],
            "voice_profile": settings["voice_profile"],
        }
        for name, settings in KNOWLEDGE_ROLE_VOICES.items()
    ]

    speaker_turns = {name: 0 for name in KNOWLEDGE_ROLE_VOICES}
    for segment in enriched.get("segments", []):
        for line in segment.get("lines", []):
            if line.get("should_speak", True) is False or line.get("type") != "dialogue":
                continue
            speaker = str(line.get("speaker") or "")
            if speaker not in KNOWLEDGE_ROLE_VOICES:
                continue
            speaker_turns[speaker] += 1
            emotion, strength = _delivery_for_line(speaker, str(line.get("text") or ""), speaker_turns[speaker])
            line["emotion"] = line.get("emotion") or emotion
            line["strength"] = line.get("strength") or strength
            line["voice_profile"] = line.get("voice_profile") or KNOWLEDGE_ROLE_VOICES[speaker]["voice_profile"]
            line["production_note"] = line.get("production_note") or KNOWLEDGE_ROLE_VOICES[speaker]["production_note"]
    return enriched


def _delivery_for_line(speaker: str, text: str, turn: int) -> tuple[str, str]:
    if speaker == "知夏":
        if "？" in text or "?" in text:
            return "疑惑", "中等"
        if any(token in text for token in ("啊", "原来", "太", "竟然", "对！", "没错")):
            return "惊喜", "较强"
        if any(token in text for token in ("所以", "也就是说", "总结", "串起来", "明白了")):
            return "坚定", "中等"
        return ("兴奋", "中等") if turn % 2 else ("温柔", "稍弱")

    if any(token in text for token in ("对", "没错", "精准", "很好", "正是")):
        return "欣慰", "中等"
    if any(token in text for token in ("不是", "不能", "误区", "风险", "关键", "问题")):
        return "严肃", "中等"
    return ("冷静", "中等") if turn % 2 else ("温柔", "稍弱")

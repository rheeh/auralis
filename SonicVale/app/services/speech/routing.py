"""Pure voice and route policy shared by preparation and compatibility calls."""
from app.core.tts_engine import EdgeTTSEngine

def resolve_tts_route(role=None, line_type: str | None = None, track: str | None = None, emotion_name: str | None = None) -> str:
    if track in {"sfx", "bgm"} or line_type in {"sfx", "bgm"}:
        return "skip"

    route = (getattr(role, "tts_route", None) or "auto").lower()
    if route in {"edge", "cloud"}:
        return route

    importance = (getattr(role, "role_importance", None) or "supporting").lower()
    role_name = (getattr(role, "name", None) or "").strip()
    neutral_emotions = {"", "平静", "自然", "解说", "旁白"}

    if role_name == "旁白" or line_type == "narration":
        return "edge"
    if importance in {"lead", "key"}:
        return "cloud"
    if emotion_name and emotion_name not in neutral_emotions:
        return "cloud"
    return "edge"

def resolve_edge_voice(role=None, voice=None) -> str:
    role_edge_voice = (getattr(role, "edge_voice", None) or "").strip()
    if role_edge_voice:
        return role_edge_voice

    from app.core.voice_binding import resolve_voice_key
    return resolve_voice_key(voice,'edge') or EdgeTTSEngine.DEFAULT_VOICE

def resolve_cosyvoice_voice(voice=None) -> str | None:
    from app.core.voice_binding import resolve_voice_key
    # An explicit edge key is not a cloud binding.
    explicit=getattr(voice,'provider_voice_id',None)
    if explicit and str(explicit).startswith(('zh-','en-','ja-')) and str(explicit).endswith('Neural'):
        return None
    return resolve_voice_key(voice,'cloud')

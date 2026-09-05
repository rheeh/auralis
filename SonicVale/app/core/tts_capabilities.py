"""Pure model/voice capability resolution shared by request adapters and the UI API."""

def cosyvoice_instruction_mode(model, params, voice_name=None):
    """Resolve capabilities per voice; most v3 system voices have no Instruct."""
    configured = str(params.get("instruction_mode") or "auto").strip().lower()
    if configured in {"mapped", "none"}:
        return configured
    if params.get("supports_instruction") is False:
        return "mapped"
    model = (model or "").lower()
    if model.startswith(("cosyvoice-v1", "cosyvoice-v2")):
        return "mapped"
    if model.startswith(("cosyvoice-v3.5-plus", "cosyvoice-v3.5-flash")):
        return "native"
    if model.startswith(("cosyvoice-v3-flash", "cosyvoice-v3-plus")):
        voice = voice_name or params.get("voice") or "longanyang"
        if voice in {"longanyang", "longanhuan", "longhuhu_v3"}:
            return "structured"
        if voice.startswith("cosyvoice-") and model.startswith("cosyvoice-v3-flash"):
            return "native"
        # longanhuan_v3 accepts dialect instructions only, not free acting notes.
        # Other documented v3 system voices support prosody but not Instruct.
        return "mapped"
    if configured in {"native", "structured"}:
        return configured
    return "native" if params.get("supports_instruction") is True else "none"


def http_instruction_field(model, params):
    """Return the provider-specific instruction path for non-CosyVoice HTTP adapters."""
    configured = params.get("instruction_field")
    if configured is False or params.get("supports_instruction") is False:
        return None
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    model = (model or "").lower()
    if (model or "").lower() in {"qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash"}:
        return "input.instruction"
    if "qwen" in model and "instruct" in model:
        return "input.instructions"
    if model.startswith("gpt-4o") and "tts" in model:
        return "instructions"
    return None
